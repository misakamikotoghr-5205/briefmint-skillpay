"""Mock receipts are isolated from the documented Alipay A402 adapter."""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


class PaymentError(ValueError):
    pass


class ConfigurationError(RuntimeError):
    pass


def b64encode(data):
    return base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode()).rstrip(b'=').decode()


def b64decode(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 16384 or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', value):
        raise PaymentError('invalid payment proof encoding')
    try:
        parsed = json.loads(base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True))
        if not isinstance(parsed, dict):
            raise ValueError()
        return parsed
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PaymentError('invalid payment proof') from exc


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,9}(?:\.\d{1,2})?', value):
        raise PaymentError('invalid payment amount')
    return f'{Decimal(value):.2f}'


class MockProvider:
    mode = 'mock'
    needed_header = 'X-BriefMint-Mock-Payment-Needed'
    proof_header = 'X-BriefMint-Mock-Payment-Proof'
    validation_header = 'X-BriefMint-Mock-Payment-Validation'

    def __init__(self, secret):
        self.secret = secret.encode() if isinstance(secret, str) else secret
        if len(self.secret) < 32:
            raise ConfigurationError('mock signing secret must contain at least 32 bytes')

    def _sign(self, payload):
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        return hmac.new(self.secret, canonical, hashlib.sha256).hexdigest()

    def challenge(self, order):
        return b64encode({'mode': 'mock', 'realMoney': False, 'out_trade_no': order['id'],
                          'amount': order['amount'], 'currency': 'CNY', 'resource_id': order['resource_id'],
                          'pay_before': order['pay_before'], 'notice': 'Local simulation only. No Alipay payment can be made with this challenge.'})

    def mock_pay(self, order):
        claims = {'mode': 'mock', 'active': True, 'out_trade_no': order['id'],
                  'trade_no': 'mock_' + hashlib.sha256(order['id'].encode()).hexdigest()[:24],
                  'amount': order['amount'], 'currency': 'CNY', 'resource_id': order['resource_id']}
        return b64encode({'claims': claims, 'signature': self._sign(claims)})

    def verify(self, proof):
        value = b64decode(proof)
        claims, signature = value.get('claims'), value.get('signature')
        if not isinstance(claims, dict) or not isinstance(signature, str) or claims.get('mode') != 'mock':
            raise PaymentError('not a BriefMint mock proof')
        if not hmac.compare_digest(signature, self._sign(claims)):
            raise PaymentError('mock proof signature rejected')
        return claims

    def confirm(self, trade_no):
        if not isinstance(trade_no, str) or not trade_no.startswith('mock_'):
            raise PaymentError('not a mock trade')
        return True


class AlipayProvider:
    """Official A402 verify/confirm API; not a private SkillPay API.

    SDK construction is lazy: the default mock requires only the Python stdlib.
    No live gateway is contacted during construction or tests.
    """
    needed_header = 'Payment-Needed'
    proof_header = 'Payment-Proof'
    validation_header = 'Payment-Validation'

    def __init__(self, environ=None):
        env = os.environ if environ is None else environ
        self.mode = env.get('BRIEFMINT_PAYMENT_MODE', 'mock')
        if self.mode not in ('alipay-sandbox', 'alipay-production'):
            raise ConfigurationError('Alipay provider requires an explicit alipay-sandbox or alipay-production mode')
        fields = {'app_id': 'ALIPAY_APP_ID', 'seller_id': 'ALIPAY_SELLER_ID',
                  'seller_name': 'ALIPAY_SELLER_NAME', 'service_id': 'ALIPAY_SERVICE_ID',
                  'private_key_file': 'ALIPAY_PRIVATE_KEY_FILE', 'public_key_file': 'ALIPAY_PUBLIC_KEY_FILE'}
        self.config = {key: env.get(name, '').strip() for key, name in fields.items()}
        missing = [fields[key] for key, value in self.config.items() if not value]
        if missing:
            raise ConfigurationError('missing real-payment configuration: ' + ', '.join(missing))
        if not re.fullmatch(r'2088\d{12}', self.config['seller_id']) or not re.fullmatch(r'\d{16,32}', self.config['app_id']):
            raise ConfigurationError('invalid merchant or application identifier')
        if self.mode == 'alipay-production' and self.config['service_id'] == 'api_mock_service_id':
            raise ConfigurationError('sandbox service ID is forbidden in production')
        if self.mode == 'alipay-sandbox' and self.config['service_id'] != 'api_mock_service_id':
            raise ConfigurationError('sandbox mode requires the documented api_mock_service_id')
        self.gateway = ('https://openapi-sandbox.dl.alipaydev.com/gateway.do' if self.mode == 'alipay-sandbox'
                        else 'https://openapi.alipay.com/gateway.do')
        # Read only explicitly configured files. Never print their contents.
        try:
            self.private_key = Path(self.config['private_key_file']).read_text().strip()
            self.public_key = Path(self.config['public_key_file']).read_text().strip()
        except OSError as exc:
            raise ConfigurationError('configured merchant key files are unavailable') from exc
        if not self.private_key or not self.public_key:
            raise ConfigurationError('configured key files are empty')
        try:
            from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
            from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
            from Crypto.PublicKey import RSA
            from Crypto.Signature import pkcs1_15
            from Crypto.Hash import SHA256
            self.RSA, self.pkcs1_15, self.SHA256 = RSA, pkcs1_15, SHA256
            # The documented key format is raw PKCS#1 Base64; do not rewrite it.
            self.signing_key = RSA.import_key(base64.b64decode(self.private_key, validate=True))
            config = AlipayClientConfig()
            config.server_url, config.app_id = self.gateway, self.config['app_id']
            config.app_private_key, config.alipay_public_key = self.private_key, self.public_key
            config.sign_type, config.charset, config.timeout = 'RSA2', 'utf-8', 10
            config.skip_sign = False
            self.client = DefaultAlipayClient(alipay_client_config=config)
        except (ImportError, ValueError, TypeError) as exc:
            raise ConfigurationError('install requirements-real.txt and supply valid documented merchant keys') from exc

    def challenge(self, order):
        params = {'amount': order['amount'], 'currency': 'CNY', 'goods_name': 'BriefMint project brief',
                  'out_trade_no': order['id'], 'pay_before': datetime.fromtimestamp(order['pay_before'], timezone.utc).isoformat(),
                  'resource_id': order['resource_id'], 'seller_id': self.config['seller_id'], 'service_id': self.config['service_id']}
        signed_text = '&'.join(f'{key}={params[key]}' for key in sorted(params))
        signature = self.pkcs1_15.new(self.signing_key).sign(self.SHA256.new(signed_text.encode()))
        return b64encode({'protocol': {key: params[key] for key in ('out_trade_no', 'amount', 'currency', 'resource_id', 'pay_before')} | {
            'seller_signature': base64.b64encode(signature).decode(), 'seller_sign_type': 'RSA2', 'seller_unique_id': self.config['seller_id']},
            'method': {'seller_name': self.config['seller_name'], 'seller_id': self.config['seller_id'],
                       'seller_app_id': self.config['app_id'], 'goods_name': params['goods_name'],
                       'seller_unique_id_key': 'seller_id', 'service_id': self.config['service_id']}})

    def verify(self, proof):
        value = b64decode(proof)
        protocol, method = value.get('protocol'), value.get('method', {})
        if not isinstance(protocol, dict) or not isinstance(method, dict) or 'claims' in value:
            raise PaymentError('not an Alipay A402 proof')
        token, trade_no = protocol.get('payment_proof'), protocol.get('trade_no')
        if not isinstance(token, str) or not 1 <= len(token) <= 64 or not token.strip() or not isinstance(trade_no, str) or not re.fullmatch(r'\d{32}', trade_no):
            raise PaymentError('Alipay proof requires a payment_proof and a 32-digit trade_no')
        client_session = method.get('client_session')
        if client_session is not None and (not isinstance(client_session, str) or len(client_session) > 1024):
            raise PaymentError('invalid Alipay client_session')
        from alipay.aop.api.request.AlipayAipayAgentPaymentVerifyRequest import AlipayAipayAgentPaymentVerifyRequest
        from alipay.aop.api.domain.AlipayAipayAgentPaymentVerifyModel import AlipayAipayAgentPaymentVerifyModel
        model = AlipayAipayAgentPaymentVerifyModel()
        model.payment_proof, model.trade_no = token, trade_no
        if method.get('client_session'):
            model.client_session = method['client_session']
        request = AlipayAipayAgentPaymentVerifyRequest()
        request.biz_model = model
        try:
            data = json.loads(self.client.execute(request))
            data = data.get('alipay_aipay_agent_payment_verify_response', data)
        except Exception as exc:
            raise PaymentError('Alipay payment verification unavailable') from exc
        if data.get('code') != '10000' or data.get('active') is not True or data.get('trade_no') != trade_no:
            raise PaymentError('Alipay payment proof rejected')
        # Deliberately stricter than the optional sandbox missing-field fallback:
        # all verified bindings, including amount, are required in every mode.
        return {'active': data['active'], 'trade_no': trade_no, 'out_trade_no': data.get('out_trade_no'),
                'amount': data.get('amount'), 'resource_id': data.get('resource_id'), 'currency': 'CNY'}

    def confirm(self, trade_no):
        from alipay.aop.api.request.AlipayAipayAgentFulfillmentConfirmRequest import AlipayAipayAgentFulfillmentConfirmRequest
        from alipay.aop.api.domain.AlipayAipayAgentFulfillmentConfirmModel import AlipayAipayAgentFulfillmentConfirmModel
        model = AlipayAipayAgentFulfillmentConfirmModel()
        model.trade_no = trade_no
        request = AlipayAipayAgentFulfillmentConfirmRequest()
        request.biz_model = model
        try:
            data = json.loads(self.client.execute(request))
            response = data.get('alipay_aipay_agent_fulfillment_confirm_response', data)
            return response.get('code') == '10000' and response.get('trade_no') == trade_no
        except Exception:
            return False
