"""Tests for the RAG API (src/rag_api.py)."""
import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from src.rag_api import app

client = TestClient(app)


class TestHealth(unittest.TestCase):
    def test_health_endpoint(self):
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")


class TestQueryValidation(unittest.TestCase):
    def test_empty_question(self):
        resp = client.post("/query", json={"question": ""})
        self.assertEqual(resp.status_code, 422)

    def test_missing_question(self):
        resp = client.post("/query", json={})
        self.assertEqual(resp.status_code, 422)

    def test_blank_question(self):
        resp = client.post("/query", json={"question": "   "})
        self.assertEqual(resp.status_code, 422)

    def test_oversized_question(self):
        resp = client.post("/query", json={"question": "x" * 2000})
        self.assertEqual(resp.status_code, 422)

    def test_valid_question(self):
        resp = client.post("/query", json={"question": "What is the Sev-1 SLA?"})
        self.assertEqual(resp.status_code, 200)


class TestQueryResponse(unittest.TestCase):
    def test_answer_field_present(self):
        resp = client.post("/query", json={"question": "What is the Sev-1 SLA?"})
        data = resp.json()
        self.assertIn("answer", data)
        self.assertIn("status", data)
        self.assertIn("sources", data)

    def test_answer_not_empty(self):
        resp = client.post("/query", json={"question": "What is the Sev-1 SLA?"})
        data = resp.json()
        self.assertGreater(len(data["answer"]), 0)

    def test_sources_serialized(self):
        resp = client.post("/query", json={
            "question": "Sev-1 response time?", "client_id": "NEXUS-002"
        })
        data = resp.json()
        for src in data["sources"]:
            self.assertIn("marker", src)
            self.assertIn("chunk_id", src)
            self.assertIn("document_id", src)
            self.assertIn("score", src)

    def test_status_is_valid(self):
        resp = client.post("/query", json={"question": "Sev-1 response time?"})
        data = resp.json()
        self.assertIn(data["status"], ("answered", "refused", "error"))

    def test_with_client_id(self):
        resp = client.post("/query", json={
            "question": "What is the Sev-1 SLA?",
            "client_id": "NEXUS-002",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "answered")

    def test_refusal_status(self):
        resp = client.post("/query", json={
            "question": "What is the travel reimbursement policy?",
            "client_id": "NONEXISTENT",
            "k": 3,
        })
        data = resp.json()
        # May be answered or refused depending on retrieval
        self.assertIn(data["status"], ("answered", "refused"))


class TestPipelineErrorHandling(unittest.TestCase):
    def test_k_out_of_range(self):
        resp = client.post("/query", json={"question": "test", "k": 0})
        self.assertEqual(resp.status_code, 422)

    def test_k_too_large(self):
        resp = client.post("/query", json={"question": "test", "k": 100})
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
