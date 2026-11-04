import copy
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from briefmint.__main__ import create_service
from briefmint.generator import generate_brief, InputError
from briefmint.http_api import make_server
from briefmint.payments import MockProvider, AlipayProvider, PaymentError, ConfigurationError, b64encode, b64decode
from briefmint.service import Service
from briefmint.store import Store, Conflict, Unauthorized


REQUEST = {'title': 'Refill launch', 'audience': 'Owner and designer', 'objective': 'Explain the refill process',
           'deliverables': ['A4 poster'], 'constraints': ['No unsupported environmental claims'],
           'facts': [{'text': 'Customers can bring clean containers.', 'source': 'Example owner policy'}]}


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'ledger.sqlite3')
        self.now = [1800000000.0]
        self.store = Store(self.path, clock=lambda: self.now[0])
        self.provider = MockProvider(self.store.mock_secret())
        self.service = Service(self.store, self.provider)
        self.order, _ = self.service.create(REQUEST, 'example_idempotency_001')
        self.id, self.token = self.order['id'], self.order['accessToken']

    def tearDown(self):
        self.tmp.cleanup()

    def receipt(self):
        return self.service.mock_pay(self.id, self.token)['proof']

    def test_unpaid_orders_cannot_read_a_brief_or_result_through_status(self):
        status, body, headers = self.service.deliver(self.id, self.token)
        self.assertEqual(status, 402)
        self.assertNotIn('brief', body)
        self.assertNotIn('Payment-Needed', headers)
        self.assertIn(self.provider.needed_header, headers)
        challenge = b64decode(headers[self.provider.needed_header])
        self.assertIs(challenge['realMoney'], False)
        self.assertEqual(challenge['amount'], '2.99')
        self.assertNotIn('result_json', self.store.public(self.store.get(self.id, self.token)))

    def test_signed_mock_receipt_unlocks_only_after_confirmation_and_replays_same_result(self):
        proof = self.receipt()
        first = self.service.deliver(self.id, self.token, proof)
        second = self.service.deliver(self.id, self.token, proof)
        self.assertEqual(first[0], 200)
        self.assertEqual(first[1]['brief'], second[1]['brief'])
        self.assertTrue(second[1]['replayed'])
        self.assertIs(first[1]['realMoney'], False)
        stored = self.store.get(self.id, self.token)
        self.assertEqual(stored['generation_count'], 1)
        self.assertEqual(stored['status'], 'FULFILLED')
        self.assertEqual([item['event'] for item in self.store.audit(self.id, self.token)],
                         ['ORDER_CREATED', 'PAYMENT_VERIFIED', 'BRIEF_PREPARED', 'FULFILLMENT_CONFIRMED'])

    def test_tampered_mock_proof_is_rejected(self):
        value = b64decode(self.receipt())
        value['claims']['amount'] = '0.01'
        status, body, _ = self.service.deliver(self.id, self.token, b64encode(value))
        self.assertEqual(status, 402)
        self.assertNotIn('brief', body)
        self.assertEqual(self.store.get(self.id, self.token)['generation_count'], 0)

    def test_valid_signature_does_not_override_wrong_amount_currency_order_resource_or_active(self):
        original = b64decode(self.receipt())['claims']
        for key, wrong in [('amount', '0.01'), ('amount', None), ('amount', '2.990'),
                           ('currency', 'USD'), ('out_trade_no', 'another-order'),
                           ('resource_id', '/another-resource'), ('active', 'true')]:
            claims = original | {key: wrong}
            proof = b64encode({'claims': claims, 'signature': self.provider._sign(claims)})
            status, body, _ = self.service.deliver(self.id, self.token, proof)
            self.assertEqual(status, 402, (key, wrong))
            self.assertNotIn('brief', body)
        self.assertEqual(self.store.get(self.id, self.token)['generation_count'], 0)

    def test_trade_cannot_fulfill_two_orders_even_with_a_validly_signed_rebound_proof(self):
        proof = self.receipt()
        self.assertEqual(self.service.deliver(self.id, self.token, proof)[0], 200)
        other, _ = self.service.create(REQUEST, 'example_idempotency_002')
        claims = b64decode(proof)['claims'] | {'out_trade_no': other['id'], 'resource_id': other['resourceId']}
        forged = b64encode({'claims': claims, 'signature': self.provider._sign(claims)})
        response = self.service.deliver(other['id'], other['accessToken'], forged)
        self.assertEqual(response[0], 402)
        self.assertEqual(self.store.get(other['id'], other['accessToken'])['generation_count'], 0)

    def test_failed_confirmation_is_persisted_and_retry_after_deadline_never_regenerates(self):
        proof = self.receipt()
        self.provider.confirm = lambda _: False
        status, body, _ = self.service.deliver(self.id, self.token, proof)
        self.assertEqual(status, 502)
        self.assertNotIn('brief', body)
        self.assertEqual(self.store.get(self.id, self.token)['status'], 'PENDING_CONFIRM')
        self.now[0] += 7200
        reloaded_store = Store(self.path, clock=lambda: self.now[0])
        reloaded = Service(reloaded_store, MockProvider(reloaded_store.mock_secret()))
        status, body, _ = reloaded.deliver(self.id, self.token, proof)
        self.assertEqual(status, 200)
        self.assertTrue(body['fulfillmentConfirmed'])
        self.assertEqual(reloaded_store.get(self.id, self.token)['generation_count'], 1)

    def test_expired_or_cancelled_unpaid_order_does_not_generate(self):
        proof = self.receipt()
        self.now[0] += 1800
        self.assertEqual(self.service.deliver(self.id, self.token, proof)[0], 410)
        self.assertEqual(self.store.get(self.id, self.token)['generation_count'], 0)
        self.now[0] -= 1800
        self.store.cancel(self.id, self.token)
        self.assertEqual(self.service.deliver(self.id, self.token, proof)[0], 410)

    def test_idempotency_is_persistent_and_conflicting_inputs_are_rejected(self):
        reloaded = Service(Store(self.path), MockProvider(self.store.mock_secret()))
        same, created = reloaded.create(REQUEST, 'example_idempotency_001')
        self.assertFalse(created)
        self.assertEqual(same['id'], self.id)
        self.assertEqual(same['accessToken'], self.token)
        with self.assertRaises(Conflict):
            self.service.create(REQUEST | {'title': 'Different'}, 'example_idempotency_001')
        with self.assertRaises(Conflict):
            self.store.create(REQUEST, 'example_idempotency_001', 'alipay-sandbox')

    def test_concurrent_retries_generate_exactly_once(self):
        proof = self.receipt()
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.service.deliver(self.id, self.token, proof), range(8)))
        self.assertTrue(all(result[0] == 200 for result in results))
        self.assertTrue(all(result[1]['brief'] == results[0][1]['brief'] for result in results))
        self.assertEqual(self.store.get(self.id, self.token)['generation_count'], 1)
        self.assertEqual(sum(event['event'] == 'FULFILLMENT_CONFIRMED' for event in self.store.audit(self.id, self.token)), 1)

    def test_order_authorization_and_audit_redaction(self):
        with self.assertRaises(Unauthorized):
            self.service.deliver(self.id, 'wrong-token', self.receipt())
        proof = self.receipt()
        self.service.deliver(self.id, self.token, proof)
        serialized = json.dumps(self.store.audit(self.id, self.token))
        self.assertNotIn(proof, serialized)
        self.assertNotIn(self.token, serialized)
        self.assertNotIn(self.store.mock_secret(), serialized)

    def test_payment_mode_separation_and_real_mode_fail_closed(self):
        with self.assertRaises(ConfigurationError):
            create_service(self.path, {'BRIEFMINT_PAYMENT_MODE': 'alipay-production'})
        with self.assertRaises(ConfigurationError):
            create_service(self.path, {'BRIEFMINT_PAYMENT_MODE': 'typo-real'})
        real = object.__new__(AlipayProvider)
        with self.assertRaises(PaymentError):
            real.verify(self.receipt())


class GeneratorTests(unittest.TestCase):
    def test_brief_is_deterministic_and_preserves_provenance_without_external_claims(self):
        before = copy.deepcopy(REQUEST)
        first, second = generate_brief(REQUEST), generate_brief(REQUEST)
        self.assertEqual(first, second)
        self.assertEqual(REQUEST, before)
        self.assertEqual(first['evidenceLedger'][0]['source'], 'Example owner policy')
        self.assertIs(first['generator']['llmUsed'], False)
        self.assertEqual(len(first['advisors']), 3)
        self.assertIn('Owner approves: A4 poster', first['acceptanceCriteria'])

    def test_missing_optional_material_becomes_open_decisions_and_invalid_input_fails(self):
        brief = generate_brief({key: REQUEST[key] for key in ('title', 'audience', 'objective')})
        self.assertTrue(any('budget' in question for question in brief['openQuestions']))
        self.assertEqual(brief['evidenceLedger'], [])
        for invalid in [None, [], {}, REQUEST | {'amount': '0.01'}, REQUEST | {'facts': ['unstructured']}, REQUEST | {'title': ' '}]:
            with self.assertRaises(InputError):
                generate_brief(invalid)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = create_service(Path(self.tmp.name) / 'http.sqlite3', {})
        self.server = make_server(('127.0.0.1', 0), self.service, api_key='test-api-key', enable_mock_payments=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        request = urllib.request.Request(self.base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type': 'application/json', 'X-BriefMint-API-Key': 'test-api-key'} | (headers or {}))
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read()), dict(response.headers)

    def test_http_create_unpaid_mock_payment_deliver_and_audit(self):
        status, body, _ = self.request('/v1/orders', {'request': REQUEST}, {'Idempotency-Key': 'http_idempotency_001'})
        self.assertEqual(status, 201)
        order = body['order']
        auth = {'Authorization': 'Bearer ' + order['accessToken']}
        status, unpaid, headers = self.request(order['resourceId'], headers=auth)
        self.assertEqual(status, 402)
        self.assertNotIn('brief', unpaid)
        self.assertIn('X-BriefMint-Mock-Payment-Needed', headers)
        _, receipt, _ = self.request('/v1/mock-payments', {'orderId': order['id']}, auth)
        status, delivered, _ = self.request(order['resourceId'], headers=auth | {receipt['proofHeader']: receipt['proof']})
        self.assertEqual(status, 200)
        self.assertIn('markdown', delivered['brief'])
        status, audit, _ = self.request('/v1/orders/' + order['id'] + '/audit', headers=auth)
        self.assertEqual(status, 200)
        self.assertEqual(len(audit['events']), 4)

    def test_http_rejects_client_price_injection_and_missing_authorization(self):
        status, _, _ = self.request('/v1/orders', {'request': REQUEST, 'amount': '0.01'}, {'Idempotency-Key': 'http_idempotency_002'})
        self.assertEqual(status, 400)
        status, _, _ = self.request('/v1/catalog', headers={'X-BriefMint-API-Key': 'wrong'})
        self.assertEqual(status, 401)


if __name__ == '__main__':
    unittest.main()
