"""Small local JSON API. Put a production HTTP/TLS gateway in front of it."""
import hmac
import ipaddress
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .generator import InputError
from .payments import PaymentError
from .store import StoreError, Unauthorized, Conflict


def make_server(address, service, *, api_key='', enable_mock_payments=False):
    if service.provider.mode != 'mock' and len(api_key) < 32:
        raise ValueError('Alipay HTTP modes require BRIEFMINT_API_KEY with at least 32 characters')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'BriefMint/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_args):
            # Never write URLs, buyer inputs, tokens, proofs, or SDK errors to logs.
            pass

        def send_json(self, status, body, headers=None):
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def body(self):
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                raise InputError('exactly one Content-Length is required')
            if self.headers.get_content_type() != 'application/json':
                raise InputError('Content-Type must be application/json')
            try:
                length = int(self.headers['Content-Length'])
            except (ValueError, TypeError):
                raise InputError('invalid Content-Length') from None
            if not 1 <= length <= 65536:
                raise InputError('JSON body must contain 1–65,536 bytes')
            try:
                value = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError):
                raise InputError('invalid JSON body') from None
            if not isinstance(value, dict):
                raise InputError('JSON body must be an object')
            return value

        def order_token(self):
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Bearer '):
                raise Unauthorized('an order access token is required')
            return auth.removeprefix('Bearer ')

        def dispatch(self):
            path = urlsplit(self.path).path
            if self.command == 'GET' and path == '/health':
                return self.send_json(200, {'status': 'ok', 'mode': service.provider.mode,
                                            'generator': 'deterministic-template', 'llmUsed': False})
            if api_key and not hmac.compare_digest(self.headers.get('X-BriefMint-API-Key', ''), api_key):
                raise Unauthorized('API key is missing or invalid')
            if self.command == 'GET' and path == '/v1/catalog':
                return self.send_json(200, {'mode': service.provider.mode, 'offers': [
                    {'id': 'project-brief', 'name': 'BriefMint project brief', 'amount': '2.99', 'currency': 'CNY'}]})
            if self.command == 'POST' and path == '/v1/orders':
                data = self.body()
                if set(data) != {'request'}:
                    raise InputError('order body must contain only request; pricing is server-owned')
                order, created = service.create(data['request'], self.headers.get('Idempotency-Key'))
                return self.send_json(201 if created else 200, {'order': order, 'created': created})
            if self.command == 'POST' and path == '/v1/mock-payments':
                if not enable_mock_payments or service.provider.mode != 'mock' or not ipaddress.ip_address(self.client_address[0]).is_loopback:
                    return self.send_json(404, {'code': 'NOT_FOUND'})
                data = self.body()
                if set(data) != {'orderId'}:
                    raise InputError('mock payment body must contain only orderId')
                return self.send_json(200, service.mock_pay(data['orderId'], self.order_token()))
            resource_match = re.fullmatch(r'/b/(bm_[A-Za-z0-9_-]{22})', path)
            if self.command == 'GET' and resource_match:
                return self.send_json(*service.deliver(resource_match.group(1), self.order_token(), self.headers.get(service.provider.proof_header)))
            match = re.fullmatch(r'/v1/orders/(bm_[A-Za-z0-9_-]{22})(?:/(audit|cancel))?', path)
            if match:
                order_id, operation = match.groups()
                token = self.order_token()
                if self.command == 'GET' and operation == 'audit':
                    return self.send_json(200, {'events': service.store.audit(order_id, token)})
                if self.command == 'GET' and operation is None:
                    return self.send_json(200, {'order': service.store.public(service.store.get(order_id, token))})
                if self.command == 'POST' and operation == 'cancel':
                    if self.body() != {}:
                        raise InputError('cancel expects an empty JSON object')
                    return self.send_json(200, {'order': service.store.public(service.store.cancel(order_id, token))})
            return self.send_json(404, {'code': 'NOT_FOUND'})

        def handle_request(self):
            try:
                self.dispatch()
            except Unauthorized as exc:
                self.send_json(401, {'code': 'UNAUTHORIZED', 'message': str(exc)})
            except Conflict as exc:
                self.send_json(409, {'code': 'CONFLICT', 'message': str(exc)})
            except (StoreError, InputError, PaymentError) as exc:
                self.send_json(400, {'code': 'INVALID_REQUEST', 'message': str(exc)})
            except Exception:
                self.send_json(503, {'code': 'SERVICE_UNAVAILABLE', 'message': 'No resource was delivered. Retry safely with the same order and proof.'})

        do_GET = handle_request
        do_POST = handle_request

    return ThreadingHTTPServer(address, Handler)
