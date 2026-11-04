"""Optional offline adapter checks against actual official SDK request classes.

These tests never construct a merchant client, read keys, or call a gateway.
Install requirements-real.txt to run them instead of skipping.
"""
import json
import unittest

from briefmint.payments import AlipayProvider, PaymentError, b64encode


class ClientDouble:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def execute(self, request):
        self.requests.append(request)
        return json.dumps(self.responses.pop(0))


class OfficialSdkContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from alipay.aop.api.request.AlipayAipayAgentPaymentVerifyRequest import AlipayAipayAgentPaymentVerifyRequest
            from alipay.aop.api.domain.AlipayAipayAgentPaymentVerifyModel import AlipayAipayAgentPaymentVerifyModel
            from alipay.aop.api.request.AlipayAipayAgentFulfillmentConfirmRequest import AlipayAipayAgentFulfillmentConfirmRequest
            from alipay.aop.api.domain.AlipayAipayAgentFulfillmentConfirmModel import AlipayAipayAgentFulfillmentConfirmModel
        except ImportError:
            raise unittest.SkipTest('optional official SDK is not installed; no live payment tests are implied')

    def provider(self, responses):
        provider = object.__new__(AlipayProvider)
        provider.mode = 'alipay-sandbox'
        provider.client = ClientDouble(responses)
        return provider

    def test_verify_uses_official_request_model_and_preserves_verified_bindings(self):
        trade = '20260324008281172041220000012182'
        expected = {'code': '10000', 'active': True, 'trade_no': trade, 'out_trade_no': 'order_1',
                    'amount': '2.99', 'resource_id': '/b/order_1'}
        for response in [expected, {'alipay_aipay_agent_payment_verify_response': expected}]:
            provider = self.provider([response])
            proof = b64encode({'protocol': {'payment_proof': 'a' * 64, 'trade_no': trade},
                               'method': {'client_session': 'sample-session'}})
            verified = provider.verify(proof)
            request = provider.client.requests[0]
            self.assertEqual(request.get_params()['method'], 'alipay.aipay.agent.payment.verify')
            params = request.biz_model.to_alipay_dict()
            self.assertEqual(params['payment_proof'], 'a' * 64)
            self.assertEqual(params['trade_no'], trade)
            self.assertEqual(params['client_session'], 'sample-session')
            self.assertEqual(verified['amount'], '2.99')
            self.assertEqual(verified['resource_id'], '/b/order_1')

    def test_success_code_alone_does_not_make_a_payment_active_or_fix_a_trade_mismatch(self):
        trade = '20260324008281172041220000012182'
        proof = b64encode({'protocol': {'payment_proof': 'a' * 64, 'trade_no': trade}})
        for response in [{'code': '10000', 'active': False, 'trade_no': trade},
                         {'code': '10000', 'active': 'true', 'trade_no': trade},
                         {'code': '10000', 'active': True, 'trade_no': '0' * 32},
                         {'code': '40004', 'active': True, 'trade_no': trade}]:
            with self.assertRaises(PaymentError):
                self.provider([response]).verify(proof)

    def test_confirmation_matches_the_official_method_and_returned_trade(self):
        trade = '20260324008281172041220000012182'
        provider = self.provider([{'code': '10000', 'trade_no': trade}, {'code': '10000', 'trade_no': '0' * 32}])
        self.assertTrue(provider.confirm(trade))
        self.assertFalse(provider.confirm(trade))
        request = provider.client.requests[0]
        self.assertEqual(request.get_params()['method'], 'alipay.aipay.agent.fulfillment.confirm')
        self.assertEqual(request.biz_model.to_alipay_dict(), {'trade_no': trade})
