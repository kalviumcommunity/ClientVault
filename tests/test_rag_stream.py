"""
Tests for POST /query/stream (src/rag_api.py + src/rag_stream.py).

Runs the real guardrail pipeline in deterministic offline mode. Only the
failure and live-LLM cases patch collaborators.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("RAG_API_FORCE_MOCK", "true")

from fastapi.testclient import TestClient

from src import rag_api, rag_stream
from src.hallucination_guardrails import REFUSAL_MESSAGE, guarded_generate

ANSWERABLE = {"question": "What is the escalation path for a P1 database outage?", "client_id": "NEXUS-002"}
OUT_OF_DOMAIN = {"question": "What is the best pizza topping in Naples?", "client_id": "NEXUS-002"}


def parse_sse(body: str):
    events = []
    for block in body.split("\n\n"):
        data = [line[len("data: "):] for line in block.split("\n") if line.startswith("data: ")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events


class TestQueryStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(rag_api.app)
        cls._delay = rag_api.STREAM_TOKEN_DELAY_MS
        rag_api.STREAM_TOKEN_DELAY_MS = 0

    @classmethod
    def tearDownClass(cls):
        rag_api.STREAM_TOKEN_DELAY_MS = cls._delay

    def stream(self, payload):
        r = self.client.post("/query/stream", json=payload)
        return r, parse_sse(r.text)

    def test_answer_streams_citations_then_tokens_then_done(self):
        r, events = self.stream(ANSWERABLE)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("text/event-stream"))
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "citations")
        self.assertEqual(types[-1], "done")
        self.assertGreater(types.count("token"), 1)  # progressive, not one blob
        self.assertEqual(set(types[1:-1]), {"token"})
        self.assertEqual(events[-1], {"type": "done", "status": "answered", "mode": "offline"})

    def test_streamed_text_matches_non_streaming_answer(self):
        _, events = self.stream(ANSWERABLE)
        streamed = "".join(e["text"] for e in events if e["type"] == "token")
        full = self.client.post("/query", json=ANSWERABLE).json()["answer"]
        self.assertEqual(streamed, full)

    def test_citations_carry_source_text_and_markers(self):
        _, events = self.stream(ANSWERABLE)
        sources = events[0]["sources"]
        self.assertGreater(len(sources), 0)
        answer = "".join(e["text"] for e in events if e["type"] == "token")
        for s in sources:
            self.assertTrue(s["text"].strip())
            self.assertTrue(s["chunk_id"])
            self.assertIn(s["marker"], answer)
            self.assertTrue(s["document_id"].startswith("nexus"))  # account isolation

    def test_out_of_domain_streams_refusal(self):
        _, events = self.stream(OUT_OF_DOMAIN)
        self.assertEqual([e["type"] for e in events], ["refusal", "done"])
        refusal = events[0]
        self.assertEqual(refusal["message"], REFUSAL_MESSAGE)
        self.assertTrue(refusal["reason"])
        for c in refusal["candidates"]:
            self.assertLess(c["score"], refusal["threshold"])
        self.assertEqual(events[1], {"type": "done", "status": "refused"})

    def test_blank_question_is_rejected_before_streaming(self):
        r = self.client.post("/query/stream", json={"question": "  "})
        self.assertEqual(r.status_code, 422)

    def test_failure_mid_stream_emits_error_without_done(self):
        def broken(text, delay):
            yield "Partial "
            raise RuntimeError("model connection reset")

        with patch.object(rag_stream, "paced_tokens", broken):
            _, events = self.stream(ANSWERABLE)
        types = [e["type"] for e in events]
        self.assertEqual(types, ["citations", "token", "error"])
        self.assertEqual(events[-1]["message"], rag_api.STREAM_ERROR_MESSAGE)
        self.assertNotIn("reset", json.dumps(events))  # internal detail not leaked

    def test_failure_before_retrieval_emits_error(self):
        with patch.object(rag_stream, "guarded_generate", side_effect=RuntimeError("db down")):
            _, events = self.stream(ANSWERABLE)
        self.assertEqual([e["type"] for e in events], ["error"])


class TestLiveTokenStreaming(unittest.TestCase):
    """Live mode forwards model deltas as they arrive (fake OpenAI stream)."""

    def test_live_mode_forwards_model_deltas(self):
        deltas = ["The P1 ", "escalation ", None, "path is [1]."]
        chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=d))]) for d in deltas]
        chunks.append(SimpleNamespace(choices=[]))
        calls = {}

        def create(**kwargs):
            calls.update(kwargs)
            return iter(chunks)

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        config = {"base_url": "https://api.example.test/v1", "api_key": "sk-test", "model": "gpt-test", "is_local_endpoint": False}

        # Offline retrieval (no embedding API), live generation path.
        offline_guard = lambda **kw: guarded_generate(**{**kw, "force_mock": True})
        with patch.object(rag_stream, "guarded_generate", offline_guard), \
             patch.object(rag_stream, "load_llm_config", return_value=config), \
             patch.object(rag_stream, "create_client", return_value=fake_client):
            events = list(rag_stream.stream_rag_events(force_mock=False, **{"question": ANSWERABLE["question"], "client_id": "NEXUS-002"}))

        self.assertEqual(events[0]["type"], "citations")
        self.assertEqual([e["text"] for e in events if e["type"] == "token"], ["The P1 ", "escalation ", "path is [1]."])
        self.assertEqual(events[-1], {"type": "done", "status": "answered", "mode": "live"})
        self.assertTrue(calls["stream"])
        self.assertIn("nexus", calls["messages"][1]["content"].lower())


if __name__ == "__main__":
    unittest.main()
