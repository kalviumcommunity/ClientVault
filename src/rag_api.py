"""
ClientVault — Backend API for the RAG Service (FastAPI)

POST /query — accepts a question and optional client_id, returns grounded
answer with sources, status, and citation metadata. Runs the existing RAG
pipeline through hallucination guardrails and citation verification.

POST /query/stream — same request; streams server-sent events (citations,
token, refusal, done, error) so the UI can render the answer progressively.

Both endpoints serve repeated identical queries (same question, client,
k, threshold and generation mode) from an in-memory TTL cache, attach a
request id and token/cost usage, and append one structured record per
request to a JSONL log. GET /usage summarises that log.
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from dotenv import load_dotenv

from src.hallucination_guardrails import (
    guarded_generate,
    REFUSAL_MESSAGE,
    DEFAULT_RELEVANCE_THRESHOLD,
)
from src.rag_observability import (
    QueryCache,
    RequestLogger,
    answer_preview,
    cache_hit_usage,
    cache_key,
    estimate_usage,
    log_sources,
    read_records,
    utc_now_iso,
)
from src.rag_stream import _TOKEN_RE, build_messages, generation_mode, stream_rag_events
from src.usage_report import summarize_usage

load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.RAGAPI: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.RAGAPI")

app = FastAPI(
    title="ClientVault RAG API",
    description="Grounded answer generation with source citations for client-specific knowledge bases.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the dev frontend (localhost:3000) and any production origin
# listed in RAG_API_CORS_ORIGINS (comma-separated).
# NEVER use allow_origins=["*"] in production with credentials.
# ---------------------------------------------------------------------------
_raw_origins = os.getenv("RAG_API_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Request-ID", "X-Cache"],
)

# ---------------------------------------------------------------------------
# Environment config
# ---------------------------------------------------------------------------
DEFAULT_PORT = int(os.getenv("RAG_API_PORT", "8000"))
MAX_QUESTION_LENGTH = int(os.getenv("RAG_API_MAX_QUESTION_LENGTH", "1000"))
FORCE_MOCK = os.getenv("RAG_API_FORCE_MOCK", "true").lower() in ("true", "1", "yes")
THRESHOLD = float(os.getenv("RAG_API_THRESHOLD", str(DEFAULT_RELEVANCE_THRESHOLD)))
# Offline mode only: pause between streamed words (live mode streams at model speed).
STREAM_TOKEN_DELAY_MS = int(os.getenv("RAG_API_STREAM_DELAY_MS", "40"))
STREAM_ERROR_MESSAGE = "The answer stopped streaming. Please retry."

CACHE = QueryCache(
    ttl_seconds=float(os.getenv("RAG_API_CACHE_TTL_S", "900")),
    max_entries=int(os.getenv("RAG_API_CACHE_MAX_ENTRIES", "256")),
    enabled=os.getenv("RAG_API_CACHE_ENABLED", "true").lower() in ("true", "1", "yes"),
)
_log_path = os.getenv("RAG_API_REQUEST_LOG", str(PROJECT_ROOT / "outputs" / "logs" / "rag_requests.jsonl"))
REQUEST_LOG = RequestLogger(Path(_log_path) if _log_path else None)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_LENGTH,
                          description="The user's question (1-1000 chars)")
    client_id: Optional[str] = Field(None, description="Optional account/client filter")
    k: int = Field(default=5, ge=1, le=20, description="Number of chunks to retrieve")

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("question must be a non-empty string")
        return stripped


class SourceItem(BaseModel):
    marker: str
    chunk_id: str
    document_id: str
    section: str
    page: int
    score: float
    text: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    status: str  # "answered" | "refused" | "error"
    sources: List[SourceItem]
    total_sources: int
    threshold_used: float
    refusal_reason: Optional[str] = None
    request_id: Optional[str] = None
    cache_hit: Optional[bool] = None
    usage: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Observability helpers
# ---------------------------------------------------------------------------

def _new_record(endpoint: str, req: QueryRequest, request_id: str) -> Dict[str, Any]:
    return {
        "timestamp": utc_now_iso(),
        "request_id": request_id,
        "endpoint": endpoint,
        "client_id": req.client_id,
        "question": req.question,
        "k": req.k,
        "threshold": THRESHOLD,
    }


def _cache_settings(req: QueryRequest, generation: Dict[str, Any]) -> Dict[str, Any]:
    """Everything besides the question that changes the answer."""
    return {"client_id": req.client_id, "k": req.k, "threshold": THRESHOLD, "generation": generation}


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def _elapsed_ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def log_rejected_request(request: Request, exc: RequestValidationError):
    """Log validation failures (they never reach the endpoints), then return the usual 422."""
    REQUEST_LOG.write({
        "timestamp": utc_now_iso(),
        "request_id": uuid.uuid4().hex,
        "endpoint": request.url.path,
        "status": "rejected",
        "cache_hit": None,
        "error": "; ".join(str(e.get("msg")) for e in exc.errors())[:300],
    })
    return await request_validation_exception_handler(request, exc)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy", "service": "ClientVault RAG API"}


@app.get("/usage", tags=["monitoring"])
def usage_endpoint(bucket: str = Query("day", pattern="^(day|hour|minute)$")) -> Dict[str, Any]:
    """Aggregate usage from the request log (no question text)."""
    records = read_records(REQUEST_LOG.path) if REQUEST_LOG.path else []
    summary = summarize_usage(records, bucket=bucket)
    summary["cache_state"] = {"entries": len(CACHE), "ttl_s": CACHE.ttl_seconds, "enabled": CACHE.enabled}
    return summary


@app.post("/query", response_model=QueryResponse, tags=["rag"])
def query_endpoint(req: QueryRequest, response: Response) -> QueryResponse:
    """Main RAG query endpoint (guardrail summary; never calls an LLM)."""
    request_id, t0 = uuid.uuid4().hex, time.perf_counter()
    record = _new_record("/query", req, request_id)
    generation = {"mode": "summary"}
    key = cache_key("/query", req.question, _cache_settings(req, generation))
    record.update(cache_key=key[:16], mode="summary")
    response.headers["X-Request-ID"] = request_id
    try:
        cached = CACHE.get(key)
        if cached:
            body, usage = cached["body"], cache_hit_usage(cached["usage"])
        else:
            result = guarded_generate(
                query=req.question,
                client_id=req.client_id,
                k=req.k,
                threshold=THRESHOLD,
                force_mock=FORCE_MOCK,
            )
            body = {
                "answer": result.answer,
                "status": "refused" if not result.passed_guard else "answered",
                "sources": result.sources,
                "total_sources": result.source_count,
                "threshold_used": result.threshold_used,
                "refusal_reason": result.refusal_reason,
            }
            # The summary is templated, not generated: only the query embedding costs anything.
            usage = estimate_usage(
                model=generation_mode(FORCE_MOCK)["model"], prompt_text="", answer_text="",
                question=req.question, llm_called=False, embeddings_called=not FORCE_MOCK,
            )
            CACHE.set(key, {"body": body, "usage": usage})

        response.headers["X-Cache"] = "HIT" if cached else "MISS"
        record.update(
            status=body["status"], cache_hit=bool(cached), answer_preview=answer_preview(body["answer"]),
            sources=log_sources(body["sources"]), source_count=len(body["sources"]),
            refusal_reason=body["refusal_reason"], usage=usage,
        )
        return QueryResponse(
            **{**body, "sources": [SourceItem(**{f: s.get(f) for f in SourceItem.model_fields}) for s in body["sources"]]},
            request_id=request_id, cache_hit=bool(cached), usage=usage,
        )
    except Exception as e:
        logger.exception("Internal error processing query")
        record.update(status="error", cache_hit=record.get("cache_hit", False), error=_error_text(e))
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        record["latency_ms"] = _elapsed_ms(t0)
        REQUEST_LOG.write(record)


def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _replay(cached: Dict[str, Any]):
    """Re-emit a cached result as the same event sequence (no pacing)."""
    if cached["status"] == "refused":
        yield {"type": "refusal", **cached["refusal"]}
    else:
        yield {"type": "citations", "sources": cached["sources"], "threshold": cached["threshold"]}
        for token in _TOKEN_RE.findall(cached["answer"]):
            yield {"type": "token", "text": token}
    yield {"type": "done", "status": cached["status"], "mode": cached["mode"]}


class ClosingStreamingResponse(StreamingResponse):
    """Always close the body iterator, even when the client disconnects mid-stream.

    Starlette abandons the iterator when send() fails, leaving cleanup to the
    garbage collector; closing it here makes the request log deterministic.
    """

    async def stream_response(self, send) -> None:
        try:
            await super().stream_response(send)
        finally:
            aclose = getattr(self.body_iterator, "aclose", None)
            if aclose is not None:
                await aclose()


@app.post("/query/stream", tags=["rag"])
def query_stream_endpoint(req: QueryRequest) -> StreamingResponse:
    """Streaming RAG query (server-sent events). Validation errors still return 422."""
    request_id, t0 = uuid.uuid4().hex, time.perf_counter()
    record = _new_record("/query/stream", req, request_id)
    generation = generation_mode(FORCE_MOCK)
    key = cache_key("/query/stream", req.question, _cache_settings(req, generation))
    cached = CACHE.get(key)
    record.update(cache_key=key[:16], cache_hit=cached is not None, mode=generation["mode"])

    # Shared by the worker-thread generator and the async driver; logged exactly once.
    state: Dict[str, Any] = {"status": "incomplete", "sources": [], "answer": [], "refusal": None,
                             "usage": None, "logged": False, "stopped": False}
    lock = threading.Lock()

    def write_log(status: Optional[str] = None) -> None:
        with lock:
            if state["logged"]:
                return
            state["logged"] = True
            if status:
                state["status"] = status
        refusal = state["refusal"]
        text = refusal.get("message", "") if refusal else "".join(state["answer"])
        record.update(
            status=state["status"], answer_preview=answer_preview(text), sources=log_sources(state["sources"]),
            source_count=len(state["sources"]), refusal_reason=(refusal or {}).get("reason"),
            usage=state["usage"], latency_ms=_elapsed_ms(t0),
        )
        REQUEST_LOG.write(record)

    def events():
        try:
            if cached:
                state["usage"] = cache_hit_usage(cached["usage"])
                refusal = cached.get("refusal")
                state.update(sources=cached["sources"] or (refusal or {}).get("candidates", []),
                             answer=[cached["answer"]], refusal=refusal)
                for event in _replay(cached):
                    if event["type"] == "done":
                        state["status"] = event["status"]
                        event = {**event, "cache_hit": True, "request_id": request_id, "usage": state["usage"]}
                    yield _sse(event)
                return

            model_usage = None
            threshold = THRESHOLD
            for event in stream_rag_events(
                question=req.question,
                client_id=req.client_id,
                k=req.k,
                threshold=THRESHOLD,
                force_mock=FORCE_MOCK,
                token_delay_s=STREAM_TOKEN_DELAY_MS / 1000,
            ):
                if state["stopped"]:  # client went away; stop generating
                    return
                kind = event["type"]
                record.setdefault("first_event_ms", _elapsed_ms(t0))
                if kind == "usage":  # internal: model-reported tokens
                    model_usage = {k: v for k, v in event.items() if k != "type"}
                    continue
                if kind == "citations":
                    state["sources"], threshold = event["sources"], event.get("threshold", THRESHOLD)
                elif kind == "token":
                    state["answer"].append(event["text"])
                elif kind == "refusal":
                    state["refusal"] = {k: v for k, v in event.items() if k != "type"}
                    state["sources"] = state["refusal"].get("candidates", [])
                elif kind == "done":
                    text = "".join(state["answer"])
                    answered = event["status"] == "answered"
                    sources = state["sources"]
                    state["usage"] = estimate_usage(
                        model=generation["model"],
                        prompt_text="\n".join(m["content"] for m in build_messages(req.question, req.client_id, sources)) if answered else "",
                        answer_text=text if answered else "",
                        question=req.question,
                        llm_called=answered and event.get("mode") == "live",
                        embeddings_called=not FORCE_MOCK,
                        model_usage=model_usage,
                    )
                    CACHE.set(key, {
                        "status": event["status"], "mode": event.get("mode", generation["mode"]), "answer": text,
                        "sources": sources if answered else [], "threshold": threshold,
                        "refusal": state["refusal"], "usage": state["usage"],
                    })
                    state["status"] = event["status"]
                    event = {**event, "cache_hit": False, "request_id": request_id, "usage": state["usage"]}
                yield _sse(event)
        except Exception as e:
            logger.exception("Streaming query failed")
            record["error"] = _error_text(e)
            state["status"] = "error"
            yield _sse({"type": "error", "message": STREAM_ERROR_MESSAGE, "request_id": request_id})
        finally:
            write_log()

    async def body():
        gen = events()
        finished = False
        try:
            while True:
                chunk = await run_in_threadpool(next, gen, None)
                if chunk is None:
                    finished = True
                    return
                yield chunk
        finally:
            if not finished:
                state["stopped"] = True
                write_log("client_disconnected" if state["status"] == "incomplete" else None)
                try:
                    gen.close()
                except ValueError:
                    pass  # a step is still running in a worker thread; it stops at the next event

    return ClosingStreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
            "X-Cache": "HIT" if cached else "MISS",
        },
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT)
