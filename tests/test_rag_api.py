"""
Tests for the RAG API (src/rag_api.py) — the contract the chat UI depends on.

Runs the real guardrail pipeline in deterministic offline mode (no API key
needed). Only the server-error case patches the pipeline.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("RAG_API_FORCE_MOCK", "true")

from fastapi.testclient import TestClient

from src import rag_api
from src.hallucination_guardrails import REFUSAL_MESSAGE

SOURCE_FIELDS = {"marker", "chunk_id", "document_id", "section", "page", "score", "text"}


class TestRagApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(rag_api.app)
        cls._log = rag_api.REQUEST_LOG
        cls._tmp = tempfile.TemporaryDirectory()
        rag_api.REQUEST_LOG = rag_api.RequestLogger(Path(cls._tmp.name) / "requests.jsonl")

    @classmethod
    def tearDownClass(cls):
        rag_api.REQUEST_LOG = cls._log
        cls._tmp.cleanup()

    def setUp(self):
        rag_api.CACHE.clear()

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "healthy")

    def test_grounded_answer_returns_sources(self):
        r = self.client.post("/query", json={
            "question": "What is the escalation path for a P1 database outage?",
            "client_id": "NEXUS-002",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "answered")
        self.assertIsNone(body["refusal_reason"])
        self.assertTrue(body["answer"])
        self.assertGreater(len(body["sources"]), 0)
        self.assertEqual(body["total_sources"], len(body["sources"]))
        for s in body["sources"]:
            self.assertEqual(set(s), SOURCE_FIELDS)
            # Citation markers in the answer map to returned sources
            self.assertIn(s["marker"], body["answer"])

    def test_account_isolation(self):
        r = self.client.post("/query", json={
            "question": "What is the escalation path for a P1 database outage?",
            "client_id": "NEXUS-002",
        })
        for s in r.json()["sources"]:
            self.assertTrue(s["document_id"].startswith("nexus"), s["document_id"])

    def test_out_of_domain_question_is_refused(self):
        r = self.client.post("/query", json={
            "question": "What is the best pizza topping in Naples?",
            "client_id": "ACME-001",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "refused")
        self.assertEqual(body["answer"], REFUSAL_MESSAGE)
        self.assertTrue(body["refusal_reason"])
        for s in body["sources"]:
            self.assertLess(s["score"], body["threshold_used"])

    def test_blank_question_rejected(self):
        r = self.client.post("/query", json={"question": "   "})
        self.assertEqual(r.status_code, 422)
        self.assertIsInstance(r.json()["detail"], list)

    def test_missing_question_rejected(self):
        r = self.client.post("/query", json={"client_id": "ACME-001"})
        self.assertEqual(r.status_code, 422)

    def test_overlong_question_rejected(self):
        r = self.client.post("/query", json={"question": "x" * (rag_api.MAX_QUESTION_LENGTH + 1)})
        self.assertEqual(r.status_code, 422)

    def test_pipeline_failure_returns_safe_500(self):
        with patch.object(rag_api, "guarded_generate", side_effect=RuntimeError("boom secret")):
            r = self.client.post("/query", json={"question": "anything"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json()["detail"], "Internal server error")
        self.assertNotIn("secret", r.text)

    def test_cors_allows_configured_origin_only(self):
        allowed = rag_api.CORS_ORIGINS[0]
        r = self.client.options("/query", headers={
            "Origin": allowed,
            "Access-Control-Request-Method": "POST",
        })
        self.assertEqual(r.headers.get("access-control-allow-origin"), allowed)

        r = self.client.options("/query", headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        })
        self.assertIsNone(r.headers.get("access-control-allow-origin"))


if __name__ == "__main__":
    unittest.main()
