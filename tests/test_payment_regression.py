"""Independent HTTP regressions for payment recovery and private-state boundaries."""

import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from briefmint.http_api import make_server
from briefmint.payments import MockProvider, b64decode, b64encode
from briefmint.service import Service
from briefmint.store import Store


REQUEST = {"title": "Independent payment review", "audience": "Project owner", "objective": "Produce a reviewable, sourced brief"}


class PaymentRecoveryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temporary.name) / "private-ledger.sqlite3")
        self.provider = MockProvider(self.store.mock_secret())
        self.service = Service(self.store, self.provider)
        self.order, _ = self.service.create(REQUEST, "independent_recovery_001")
        self.proof = self.service.mock_pay(self.order["id"], self.order["accessToken"])["proof"]
        self.server = make_server(("127.0.0.1", 0), self.service, api_key="independent-test-api")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def get(self, path, proof=None, token=None):
        headers = {"X-BriefMint-API-Key": "independent-test-api", "Authorization": "Bearer " + (self.order["accessToken"] if token is None else token)}
        if proof is not None:
            headers[self.provider.proof_header] = proof
        request = urllib.request.Request(self.base + path, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read()), dict(response.headers)

    def assert_private_values_absent(self, response):
        serialized = json.dumps(response)
        for private in (self.order["accessToken"], self.proof, self.store.mock_secret(), "provider-private-error-body"):
            self.assertNotIn(private, serialized)
        body = response[1]
        self.assertNotIn("result_json", serialized)
        if isinstance(body, dict) and "order" in body:
            self.assertNotIn("accessToken", body["order"])

    def test_confirmation_exception_exposes_no_private_data_and_original_proof_recovers(self):
        def failing_confirmation(_trade):
            raise RuntimeError("provider-private-error-body " + self.order["accessToken"] + " " + self.proof)

        unpaid = self.get(self.order["resourceId"])
        self.assertEqual(unpaid[0], 402)
        challenge = b64decode(unpaid[2][self.provider.needed_header])
        self.assertNotIn("accessToken", challenge)
        self.assertNotIn(self.order["accessToken"], json.dumps(challenge))
        self.provider.confirm = failing_confirmation
        failed = self.get(self.order["resourceId"], self.proof)
        self.assertEqual(failed[0], 503)
        self.assertNotIn("brief", failed[1])
        status = self.get("/v1/orders/" + self.order["id"])
        self.assertEqual(status[1]["order"]["status"], "PENDING_CONFIRM")
        audit = self.get("/v1/orders/" + self.order["id"] + "/audit")
        unauthorized = self.get("/v1/orders/" + self.order["id"], token="wrong-access-token")
        self.assertEqual(unauthorized[0], 401)
        for response in (unpaid, failed, status, audit, unauthorized):
            self.assert_private_values_absent(response)
        self.provider.confirm = lambda _trade: True
        recovered = self.get(self.order["resourceId"], self.proof)
        self.assertEqual(recovered[0], 200)
        self.assertTrue(recovered[1]["fulfillmentConfirmed"])
        self.assertEqual(self.store.get(self.order["id"], self.order["accessToken"])["generation_count"], 1)

    def test_bound_order_never_issues_a_second_payment_challenge_and_rejects_replacement(self):
        self.provider.confirm = lambda _trade: False
        first = self.get(self.order["resourceId"], self.proof)
        self.assertEqual(first[0], 502)
        before = self.store.get(self.order["id"], self.order["accessToken"])
        claims = b64decode(self.proof)["claims"] | {"trade_no": "mock_alternative_payment"}
        replacement = b64encode({"claims": claims, "signature": self.provider._sign(claims)})
        for candidate in (None, replacement, "malformed-proof"):
            response = self.get(self.order["resourceId"], candidate)
            self.assertEqual(response[0], 409)
            self.assertNotIn(self.provider.needed_header, response[2])
            self.assertNotIn("brief", response[1])
        after = self.store.get(self.order["id"], self.order["accessToken"])
        self.assertEqual(after["proof_hash"], before["proof_hash"])
        self.assertEqual(after["trade_no"], before["trade_no"])
        self.assertEqual(after["generation_count"], 1)
        self.provider.confirm = lambda _trade: True
        self.assertEqual(self.get(self.order["resourceId"], self.proof)[0], 200)
        for candidate in (None, replacement):
            fulfilled = self.get(self.order["resourceId"], candidate)
            self.assertEqual(fulfilled[0], 409)
            self.assertNotIn(self.provider.needed_header, fulfilled[2])
            self.assertNotIn("brief", fulfilled[1])
        self.assertEqual(self.get(self.order["resourceId"], self.proof)[0], 200)


if __name__ == "__main__":
    unittest.main()
