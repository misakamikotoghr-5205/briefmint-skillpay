from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from briefmint.__main__ import create_service, main
from briefmint.generator import generate_brief
from briefmint.http_api import make_server
from briefmint.preflight import review_request

COMPLETE = {"title": "Refill launch", "audience": "Shop owner", "objective": "Explain the refill process",
            "deliverables": ["An A4 poster"], "constraints": ["Owner review"],
            "facts": [{"text": "Clean containers are accepted.", "source": "Owner policy"}]}


class PreflightTests(unittest.TestCase):
    def test_complete_request_is_reviewable_without_claiming_verified_facts_or_generating_content(self):
        review = review_request(COMPLETE)
        self.assertEqual(review["assessment"], "ready-for-owner-review")
        self.assertEqual(review["warningCount"], 0)
        self.assertFalse(review["briefGenerated"])
        self.assertFalse(review["orderCreated"])
        self.assertFalse(review["paymentInitiated"])
        self.assertNotIn("brief", review)
        self.assertEqual(review["requestSha256"], generate_brief(COMPLETE)["generator"]["inputSha256"])
        self.assertIn("does not verify facts", review["disclosure"])

    def test_missing_material_yields_field_specific_questions_without_silently_forbidding_purchase(self):
        minimal = {key: COMPLETE[key] for key in ("title", "audience", "objective")}
        review = review_request(minimal)
        self.assertEqual(review["assessment"], "review-needed")
        self.assertTrue(review["canCreateOrder"])
        self.assertGreaterEqual(review["warningCount"], 3)
        self.assertTrue(any("budget" in question for question in review["questions"]))
        self.assertTrue(any(check["code"] == "DELIVERABLES" and check["fields"] == ["deliverables"] for check in review["checks"]))

    def test_duplicate_fact_and_bad_source_labels_do_not_count_as_independent_evidence(self):
        request = COMPLETE | {"facts": [
            {"text": "Clean containers are accepted.", "source": "TBD"},
            {"text": "  clean   containers are accepted.  ", "source": "https://"},
            {"text": "Another statement", "source": "https://user:password@example.com/policy"},
        ]}
        review = review_request(request)
        self.assertEqual(review["counts"]["uniqueStatements"], 2)
        self.assertEqual(review["counts"]["duplicateGroups"], 1)
        self.assertEqual(review["counts"]["attributionGaps"], 3)
        serialized = json.dumps(review)
        self.assertNotIn("password", serialized)
        self.assertNotIn("Clean containers are accepted.", serialized)

    def test_same_statement_with_different_sources_is_flagged_for_review_not_called_a_contradiction(self):
        request = COMPLETE | {"facts": COMPLETE["facts"] + [{"text": COMPLETE["facts"][0]["text"], "source": "Interview notes"}]}
        review = review_request(request)
        self.assertEqual(review["counts"]["attributionGaps"], 0)
        self.assertEqual(review["counts"]["duplicateGroups"], 1)
        self.assertIn("does not verify facts, detect semantic contradictions", review["disclosure"])

    def test_invalid_request_blocks_order_readiness_but_still_returns_actionable_review(self):
        for request in (None, [], {}, COMPLETE | {"amount": "0.01"}):
            review = review_request(request)
            self.assertFalse(review["inputValid"])
            self.assertFalse(review["canCreateOrder"])
            self.assertEqual(review["blockingCount"], 1)
            self.assertTrue(review["questions"])

    def test_cli_preflight_never_initializes_a_payment_provider_or_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            request = Path(temp) / "request.json"
            request.write_text(json.dumps(COMPLETE))
            ledger = Path(temp) / "must-not-exist.sqlite3"
            with patch.dict(os.environ, {"BRIEFMINT_PAYMENT_MODE": "alipay-production"}), \
                    patch("briefmint.__main__.create_service", side_effect=AssertionError("must not initialize payments")), \
                    redirect_stdout(io.StringIO()) as output:
                status = main(["--db", str(ledger), "preflight", "--input", str(request), "--strict"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "preflight")
            self.assertFalse(ledger.exists())
            request.write_text(json.dumps({key: COMPLETE[key] for key in ("title", "audience", "objective")}))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["preflight", "--input", str(request), "--strict"]), 2)

    def test_http_preflight_creates_no_order_and_calls_neither_generation_nor_payment(self):
        with tempfile.TemporaryDirectory() as temp:
            service = create_service(Path(temp) / "api.sqlite3", {})
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                body = json.dumps({"request": COMPLETE}).encode()
                request = Request(f"http://127.0.0.1:{server.server_port}/v1/preflight", data=body,
                                  headers={"Content-Type": "application/json"})
                with patch.object(service.provider, "verify", side_effect=AssertionError("no payment")), \
                        patch("briefmint.store.generate_brief", side_effect=AssertionError("no paid generation")):
                    with urlopen(request) as response:
                        self.assertEqual(response.status, 200)
                        self.assertFalse(json.loads(response.read())["orderCreated"])
                with service.store.transaction() as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
