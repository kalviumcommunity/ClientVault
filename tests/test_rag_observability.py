"""
Tests for query caching, structured request logging, usage/cost tracking
and the usage report (src/rag_observability.py, src/usage_report.py,
src/rag_api.py).
"""

import asyncio
import json
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

from src import rag_api, rag_stream
from src.rag_observability import (
    QueryCache, cache_hit_usage, cache_key, estimate_usage, read_records,
)
from src.token_cost_estimator import calculate_cost, count_tokens
from src.usage_report import format_report, summarize_usage

NEXUS_Q = {"question": "What is the escalation path for a P1 database outage?", "client_id": "NEXUS-002"}


def parse_sse(body):
    return [json.loads(line[6:]) for line in body.split("\n") if line.startswith("data: ")]


class TestQueryCache(unittest.TestCase):
    def test_key_ignores_case_and_whitespace_but_not_settings(self):
        base = {"client_id": "NEXUS-002", "k": 5, "threshold": 0.6, "generation": {"mode": "offline"}}
        a = cache_key("/query", "What is  the SLA?", base)
        self.assertEqual(a, cache_key("/query", "  what is the sla?", base))
        self.assertNotEqual(a, cache_key("/query", "What is the SLA?", {**base, "client_id": "ACME-001"}))
        self.assertNotEqual(a, cache_key("/query", "What is the SLA?", {**base, "k": 3}))
        self.assertNotEqual(a, cache_key("/query/stream", "What is the SLA?", base))

    def test_ttl_expiry(self):
        now = [1000.0]
        cache = QueryCache(ttl_seconds=60, clock=lambda: now[0])
        cache.set("k", {"v": 1})
        now[0] += 59
        self.assertEqual(cache.get("k"), {"v": 1})
        now[0] += 2
        self.assertIsNone(cache.get("k"))
        self.assertEqual(len(cache), 0)

    def test_lru_eviction(self):
        cache = QueryCache(max_entries=2)
        cache.set("a", {}); cache.set("b", {})
        cache.get("a")              # a is now most recent
        cache.set("c", {})          # evicts b
        self.assertIsNotNone(cache.get("a"))
        self.assertIsNone(cache.get("b"))
        self.assertIsNotNone(cache.get("c"))

    def test_disabled_cache_stores_nothing(self):
        cache = QueryCache(enabled=False)
        cache.set("a", {"v": 1})
        self.assertIsNone(cache.get("a"))


class TestUsage(unittest.TestCase):
    def test_offline_estimate_is_not_billed(self):
        u = estimate_usage(model="gpt-4o-mini", prompt_text="context " * 50, answer_text="answer text",
                           question="q?", llm_called=False, embeddings_called=False)
        self.assertEqual(u["token_source"], "tiktoken-estimate")
        self.assertEqual(u["input_tokens"], count_tokens("context " * 50))
        self.assertEqual(u["billed_cost_usd"], 0.0)
        expected = (calculate_cost(u["input_tokens"], u["output_tokens"], "gpt-4o-mini")["total_cost_usd"]
                    + calculate_cost(u["embedding_tokens"], 0, "text-embedding-3-small")["total_cost_usd"])
        self.assertAlmostEqual(u["estimated_cost_usd"], expected, places=8)

    def test_model_reported_usage_wins_and_is_billed(self):
        u = estimate_usage(model="gpt-4o-mini", prompt_text="ignored", answer_text="ignored", question="q",
                           llm_called=True, embeddings_called=True,
                           model_usage={"prompt_tokens": 1000, "completion_tokens": 200})
        self.assertEqual((u["token_source"], u["input_tokens"], u["output_tokens"]), ("model", 1000, 200))
        self.assertAlmostEqual(u["billed_cost_usd"], u["estimated_cost_usd"], places=8)
        self.assertGreater(u["billed_cost_usd"], 0.000269)  # 1000*0.15/1M + 200*0.6/1M = 0.00027

    def test_cache_hit_spends_nothing_and_records_saving(self):
        hit = cache_hit_usage({"model": "gpt-4o-mini", "estimated_cost_usd": 0.0004, "billed_cost_usd": 0.0})
        self.assertEqual((hit["input_tokens"], hit["estimated_cost_usd"], hit["token_source"]), (0, 0.0, "cache"))
        self.assertEqual(hit["saved_estimated_cost_usd"], 0.0004)


class TestApiCachingAndLogging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(rag_api.app)
        cls._log, cls._delay = rag_api.REQUEST_LOG, rag_api.STREAM_TOKEN_DELAY_MS
        rag_api.STREAM_TOKEN_DELAY_MS = 0

    @classmethod
    def tearDownClass(cls):
        rag_api.REQUEST_LOG, rag_api.STREAM_TOKEN_DELAY_MS = cls._log, cls._delay

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self._tmp.name) / "requests.jsonl"
        rag_api.REQUEST_LOG = rag_api.RequestLogger(self.log_path)
        rag_api.CACHE.clear()

    def tearDown(self):
        self._tmp.cleanup()

    def records(self):
        return read_records(self.log_path)

    def test_repeated_query_served_from_cache(self):
        with patch.object(rag_api, "guarded_generate", wraps=rag_api.guarded_generate) as spy:
            first = self.client.post("/query", json=NEXUS_Q)
            second = self.client.post("/query", json={**NEXUS_Q, "question": "  what is the ESCALATION path for a P1 database outage? "})
        self.assertEqual(spy.call_count, 1)  # pipeline ran once
        self.assertEqual((first.headers["X-Cache"], second.headers["X-Cache"]), ("MISS", "HIT"))
        a, b = first.json(), second.json()
        self.assertEqual((a["cache_hit"], b["cache_hit"]), (False, True))
        self.assertEqual(a["answer"], b["answer"])
        self.assertEqual(a["sources"], b["sources"])
        self.assertNotEqual(a["request_id"], b["request_id"])
        self.assertEqual(b["usage"]["token_source"], "cache")

    def test_different_client_is_a_cache_miss(self):
        self.client.post("/query", json=NEXUS_Q)
        r = self.client.post("/query", json={**NEXUS_Q, "client_id": "ACME-001"})
        self.assertEqual(r.headers["X-Cache"], "MISS")

    def test_repeated_stream_replays_from_cache(self):
        with patch.object(rag_api, "stream_rag_events", wraps=rag_api.stream_rag_events) as spy:
            first = parse_sse(self.client.post("/query/stream", json=NEXUS_Q).text)
            r2 = self.client.post("/query/stream", json=NEXUS_Q)
            second = parse_sse(r2.text)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(r2.headers["X-Cache"], "HIT")
        text = lambda evs: "".join(e["text"] for e in evs if e["type"] == "token")
        self.assertEqual(text(first), text(second))
        self.assertEqual(first[0]["sources"], second[0]["sources"])
        self.assertEqual((first[-1]["cache_hit"], second[-1]["cache_hit"]), (False, True))
        self.assertGreater(first[-1]["usage"]["estimated_cost_usd"], 0)
        self.assertEqual(second[-1]["usage"]["saved_estimated_cost_usd"], first[-1]["usage"]["estimated_cost_usd"])

    def test_cached_refusal_replays_as_refusal(self):
        q = {"question": "What is the best pizza topping in Naples?", "client_id": "NEXUS-002"}
        self.client.post("/query/stream", json=q)
        second = parse_sse(self.client.post("/query/stream", json=q).text)
        self.assertEqual([e["type"] for e in second], ["refusal", "done"])
        self.assertTrue(second[-1]["cache_hit"])
        miss, hit = self.records()
        self.assertEqual(hit["source_count"], miss["source_count"])  # candidates logged on hits too

    def test_failures_are_not_cached(self):
        def broken(text, delay):
            yield "Partial "
            raise RuntimeError("model connection reset")
        with patch.object(rag_stream, "paced_tokens", broken):
            failed = parse_sse(self.client.post("/query/stream", json=NEXUS_Q).text)
        self.assertEqual(failed[-1]["type"], "error")
        retry = self.client.post("/query/stream", json=NEXUS_Q)
        self.assertEqual(retry.headers["X-Cache"], "MISS")
        self.assertEqual(parse_sse(retry.text)[-1]["status"], "answered")

    def test_each_request_is_logged_with_sources_and_usage(self):
        self.client.post("/query/stream", json=NEXUS_Q)
        self.client.post("/query/stream", json=NEXUS_Q)
        miss, hit = self.records()
        for rec in (miss, hit):
            for field in ("timestamp", "request_id", "endpoint", "question", "client_id", "status",
                          "cache_hit", "answer_preview", "sources", "usage", "latency_ms"):
                self.assertIn(field, rec)
            self.assertLessEqual(len(rec["answer_preview"]), 180)
            self.assertTrue(rec["sources"])
            self.assertNotIn("text", rec["sources"][0])  # metadata only, no chunk text
        self.assertEqual((miss["status"], miss["cache_hit"], hit["cache_hit"]), ("answered", False, True))
        self.assertEqual(miss["usage"]["token_source"], "tiktoken-estimate")
        self.assertGreater(miss["usage"]["input_tokens"], 0)
        self.assertIn("first_event_ms", miss)

    def test_errors_and_rejections_are_logged(self):
        with patch.object(rag_api, "guarded_generate", side_effect=RuntimeError("db down")):
            self.assertEqual(self.client.post("/query", json={"question": "anything"}).status_code, 500)
        self.assertEqual(self.client.post("/query", json={"question": "  "}).status_code, 422)
        error, rejected = self.records()
        self.assertEqual((error["status"], error["error"]), ("error", "RuntimeError: db down"))
        self.assertEqual((rejected["status"], rejected["endpoint"]), ("rejected", "/query"))
        self.assertIn("non-empty", rejected["error"])

    def test_client_disconnect_mid_stream_is_logged_once_and_not_cached(self):
        response = rag_api.query_stream_endpoint(rag_api.QueryRequest(**NEXUS_Q))

        async def read_two_then_disconnect():
            it = response.body_iterator
            await it.__anext__()   # citations
            await it.__anext__()   # first token
            await it.aclose()      # what Starlette does when the client goes away

        asyncio.run(read_two_then_disconnect())
        (rec,) = self.records()
        self.assertEqual(rec["status"], "client_disconnected")
        self.assertEqual(rec["source_count"], 5)
        self.assertTrue(rec["answer_preview"])  # the partial answer that was sent
        retry = self.client.post("/query/stream", json=NEXUS_Q)
        self.assertEqual(retry.headers["X-Cache"], "MISS")

    def test_usage_endpoint_summarises_without_question_text(self):
        self.client.post("/query", json=NEXUS_Q)
        self.client.post("/query", json=NEXUS_Q)
        summary = self.client.get("/usage").json()
        self.assertEqual(summary["total_requests"], 2)
        self.assertEqual((summary["cache"]["hits"], summary["cache"]["hit_rate"]), (1, 0.5))
        self.assertNotIn("top_questions", summary)
        self.assertNotIn(NEXUS_Q["question"], json.dumps(summary))


class TestUsageReport(unittest.TestCase):
    RECORDS = [
        {"timestamp": "2026-10-27T09:00:00.000Z", "request_id": "a", "endpoint": "/query/stream", "status": "answered",
         "question": "Q1", "cache_hit": False, "latency_ms": 3000.0,
         "usage": {"token_source": "tiktoken-estimate", "input_tokens": 900, "output_tokens": 150, "embedding_tokens": 12,
                   "estimated_cost_usd": 0.000225, "billed_cost_usd": 0.0}},
        {"timestamp": "2026-10-28T10:00:00.000Z", "request_id": "b", "endpoint": "/query/stream", "status": "answered",
         "question": "Q1", "cache_hit": True, "latency_ms": 10.0,
         "usage": {"token_source": "cache", "input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0,
                   "estimated_cost_usd": 0.0, "billed_cost_usd": 0.0, "saved_estimated_cost_usd": 0.000225}},
        {"timestamp": "2026-10-28T10:05:00.000Z", "request_id": "c", "endpoint": "/query", "status": "rejected",
         "cache_hit": None, "error": "question must be a non-empty string"},
    ]

    def test_summary_totals(self):
        s = summarize_usage(self.RECORDS, include_questions=True)
        self.assertEqual(s["total_requests"], 3)
        self.assertEqual(s["cache"], {"lookups": 2, "hits": 1, "misses": 1, "hit_rate": 0.5,
                                      "saved_estimated_cost_usd": 0.000225})
        self.assertEqual(s["tokens"]["input"], 900)
        self.assertEqual(s["cost"]["estimated_cost_usd"], 0.000225)
        self.assertEqual((s["latency_ms"]["avg_cache_hit"], s["latency_ms"]["avg_cache_miss"]), (10.0, 3000.0))
        self.assertEqual(s["errors"]["count"], 1)
        self.assertEqual(s["top_questions"][0], {"question": "Q1", "requests": 2})

    def test_usage_over_time_buckets(self):
        days = summarize_usage(self.RECORDS)["over_time"]
        self.assertEqual([(d["period"], d["requests"], d["cache_hits"]) for d in days],
                         [("2026-10-27", 1, 0), ("2026-10-28", 2, 1)])
        hours = summarize_usage(self.RECORDS, bucket="hour")["over_time"]
        self.assertEqual([h["period"] for h in hours], ["2026-10-27T09", "2026-10-28T10"])

    def test_text_report_and_empty_log(self):
        self.assertIn("hit rate 50.0%", format_report(summarize_usage(self.RECORDS)))
        self.assertEqual(summarize_usage([])["total_requests"], 0)


if __name__ == "__main__":
    unittest.main()
