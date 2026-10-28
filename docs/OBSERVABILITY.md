# Caching, Logging & Usage Monitoring

> **Branch:** `feat/caching-observability` · **Captured:** 2026-10-28 against live `uvicorn src.rag_api:app`
> in offline mode (`RAG_API_FORCE_MOCK=true`, no `OPENAI_API_KEY`, `RAG_API_STREAM_DELAY_MS=40`).

| What | Where |
|---|---|
| Cache, usage/cost, JSONL logger | [`src/rag_observability.py`](../src/rag_observability.py) |
| Endpoint wiring (`/query`, `/query/stream`, `GET /usage`, 422 logging) | [`src/rag_api.py`](../src/rag_api.py) |
| Usage report (CLI + summary used by `/usage`) | [`src/usage_report.py`](../src/usage_report.py) |
| Tests (19) | [`tests/test_rag_observability.py`](../tests/test_rag_observability.py) |
| Sample request log (32 real requests) | [`evidence/sample_rag_requests.jsonl`](evidence/sample_rag_requests.jsonl) |
| Usage report from that log | [`evidence/usage_report.txt`](evidence/usage_report.txt), [`evidence/usage_report.json`](evidence/usage_report.json) |
| Session transcript (X-Cache, latency per request) | [`evidence/cache_session.txt`](evidence/cache_session.txt) |
| UI showing a cache hit | [`screenshots/12-ui-served-from-cache.jpg`](screenshots/12-ui-served-from-cache.jpg) |

---

## 1. Query cache

An in-memory **TTL + LRU** cache (`QueryCache`, thread-safe) in front of both RAG endpoints.

**Key** = SHA-256 of `{endpoint, normalised question, client_id, k, threshold, generation}` where the question
is lower-cased with whitespace collapsed, and `generation` is the answer path (`summary` for `/query`;
`offline` or `live:<model>` for `/query/stream`). So:

- same question + same settings → **hit**, including case/whitespace variants;
- a different **client_id** is always a **miss** — cached evidence never crosses accounts;
- a different `k`, threshold, model or endpoint is a miss.

**Stored:** only completed results — `answered` and `refused`. Errors, timeouts, streams the client abandoned,
and validation failures are never cached, so a retry always re-runs the pipeline.

**Hits:** `/query` returns the stored body; `/query/stream` replays the same event sequence (citations →
tokens → done, or refusal → done) without pacing. Both set `X-Cache: HIT|MISS` and return
`cache_hit` + `request_id`; the chat UI shows "Served from cache" under the answer.

| Setting | Default |
|---|---|
| `RAG_API_CACHE_ENABLED` | `true` |
| `RAG_API_CACHE_TTL_S` | `900` (15 min) |
| `RAG_API_CACHE_MAX_ENTRIES` | `256` (least recently used evicted) |

Recorded effect (from `cache_session.txt`): streamed misses took **2.8–3.4 s**, hits **4–27 ms**;
`/query` misses 21–32 ms, hits 4–5 ms.

## 2. Structured request log

One JSON object per request, appended to `outputs/logs/rag_requests.jsonl` (`RAG_API_REQUEST_LOG`; empty = stdout
only; `outputs/` is gitignored) and echoed to the application log. Logged for every outcome: `answered`,
`refused`, `error`, `rejected` (422), `incomplete`, and `client_disconnected`.

```json
{"timestamp": "2026-10-28T08:30:28.510Z", "request_id": "610bcc96280045499ebde8259b97756e",
 "endpoint": "/query/stream", "client_id": "NEXUS-002",
 "question": "What is the escalation path for a P1 database outage?", "k": 5, "threshold": 0.6,
 "cache_key": "cbc07fbb8866ebc7", "cache_hit": false, "mode": "offline", "first_event_ms": 78.76,
 "status": "answered",
 "answer_preview": "Grounded Answer (Sufficient Evidence): - Source [1]: nexus_database_failover_runbook, …",
 "sources": [{"marker": "[1]", "chunk_id": "nexus_database_failover_runbook#tok_000",
              "document_id": "nexus_database_failover_runbook", "section": "Nexus Financial Technologies - Databa...",
              "page": 1, "score": 0.7395}, "… 4 more"],
 "source_count": 5, "refusal_reason": null,
 "usage": {"model": "gpt-4o-mini", "token_source": "tiktoken-estimate", "llm_called": false,
           "input_tokens": 1767, "output_tokens": 152, "embedding_tokens": 12,
           "estimated_cost_usd": 0.00035649, "billed_cost_usd": 0.0},
 "latency_ms": 3328.5}
```

The repeat 4 s later is the same record with `"cache_hit": true`, `"latency_ms": 13.17` and
`usage.token_source: "cache"`, zero tokens and `saved_estimated_cost_usd: 0.00035649`.

**What is (not) logged.** Source *metadata* is logged, not chunk text; the answer is a 180-character preview;
exceptions are logged as `Type: message` (≤ 200 chars) server-side only — clients get a generic message.
No API keys or headers are logged. The question text **is** logged (needed to debug bad answers); `GET /usage`
returns aggregates only and never question text.

**Client disconnects** are logged deterministically: the stream is driven by an async wrapper and a
`StreamingResponse` subclass that always closes the body, so an abandoned stream writes one
`client_disconnected` record (with the partial answer preview) instead of depending on garbage collection.
(Before this fix, the first live session showed 12 requests but only 11 log lines.)

## 3. Token usage and cost

| Situation | Tokens | `estimated_cost_usd` | `billed_cost_usd` |
|---|---|---|---|
| Live LLM stream | model-reported (`stream_options.include_usage`), else tiktoken | priced from tokens | same |
| Offline stream (this capture) | tiktoken count of the grounded prompt that **would** be sent + the answer | what that call would cost | **0** — no model called |
| `/query` (templated summary, never calls an LLM) | 0 generation tokens | query embedding only | embedding only when live |
| Refusal | 0 generation tokens (guardrail stops before generation) | embedding only | embedding only when live |
| Cache hit | 0 | 0 | 0 (+ `saved_*` = original request's cost) |

Prices come from the existing `MODEL_PRICING` table in `src/token_cost_estimator.py`
(`gpt-4o-mini` $0.15 / $0.60 per 1M input/output tokens; `text-embedding-3-small` $0.02 per 1M) and tokens from
its `count_tokens()` (tiktoken `o200k_base` / `cl100k_base`, both verified to load). The stream's `done` event
carries the same `usage` object, which the UI shows as "~1,919 tokens · est. $0.000356 (not billed)".

## 4. Usage report

```bash
python -m src.usage_report                                   # outputs/logs/rag_requests.jsonl, per day
python -m src.usage_report --log docs/evidence/sample_rag_requests.jsonl --bucket minute --json report.json
curl -s localhost:8000/usage?bucket=hour                     # same summary as JSON (no question text)
```

Report from the committed sample (32 requests over ~3 minutes; `--bucket minute`):

```text
  Total requests:    32   by endpoint: {'/query/stream': 26, '/query': 6}
  By status:         {'answered': 23, 'refused': 5, 'rejected': 2, 'client_disconnected': 2}
  Cache:             14 hits / 30 lookups (hit rate 46.7%), saved ≈ $0.003538
  Tokens:            input 15003, output 1406, embedding 128
  Cost (estimated):  $0.003097   billed: $0.000000   LLM calls: 0
  Latency (ms):      avg 934.59, p50 18.36, p95 3328.5   | hit avg 8.58, miss avg 1744.84

  Usage over time (per minute):
    period         requests   hits    est. cost    avg ms  errors
    2026-10-28T08:30       14      6    $0.001399     958.1       1
    2026-10-28T08:31        2      1    $0.000356   1726.21       0
    2026-10-28T08:32        2      0    $0.000298    1459.3       0
    2026-10-28T08:33       14      7    $0.001043    708.57       1
```

The sample = scripted session 1 (14 requests) → API restart (cache cleared) → the chat UI asking the same
question twice (miss, then hit) → two requests typed manually in the UI ("hi") → scripted session 2 (14 requests;
its first request was already a hit because the UI had warmed the cache). "Saved" exceeds "estimated" because
14 hits each avoided a full request.

## Verification

| Check | Result |
|---|---|
| `tests/test_rag_observability.py` | 19/19 — key normalisation & isolation, TTL, LRU, disabled cache, usage math, `/query` + stream hits (pipeline called once), cached refusal, failures not cached, log fields, error + 422 logging, client disconnect logged once and not cached, `/usage` hides questions, report totals and time buckets |
| `tests/test_rag_api.py`, `tests/test_rag_stream.py` | 9/9, 8/8 (cache cleared per test) |
| Full suite | 178 tests, 1 failure: pre-existing, order-dependent `test_corpus_embedder.test_environment_config_loading` |
| UI | typecheck + build OK; browser: miss shows token/cost line, repeat shows "Served from cache" |

## Limitations

- The cache is **per process and in memory**: it is lost on restart and not shared between workers. A shared
  store (e.g. Redis) would be needed for multiple instances.
- No invalidation on re-indexing beyond the TTL; clear the cache (restart) after corpus changes.
- The log file has no rotation or retention policy yet.
- Live-mode usage/cost is only unit-tested with a fake stream (no API key available).
- Observation while capturing: the question "hi" with **no client selected** passed the relevance guardrail
  and was answered, while the same question scoped to NEXUS-002 was refused (best score 0.4664). Retrieval
  quality for very short queries is worth a follow-up; it is unrelated to caching.
