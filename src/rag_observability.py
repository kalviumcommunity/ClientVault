"""
ClientVault — Query cache, usage metering and structured request logging
for the RAG API (src/rag_api.py).

QueryCache
    In-memory TTL + LRU cache of finished RAG results. The key covers every
    setting that changes the answer: endpoint, normalised question, client_id
    (account isolation), k, relevance threshold and generation mode/model.
    Only completed results (answered / refused) are stored — never errors,
    interrupted streams or validation failures.

estimate_usage
    Token counts and cost per request. Live LLM calls use the model's own
    usage numbers when it reports them; otherwise tokens are counted with
    tiktoken (src/token_cost_estimator.count_tokens) and priced with
    MODEL_PRICING. In offline mode no model is called, so the billed cost is
    0 and the "equivalent" cost is what the same prompt would cost live.

RequestLogger
    One JSON object per request, appended to a JSONL file and echoed to the
    application log. Stores source metadata (not chunk text), an answer
    preview, cache hit/miss, usage, latency and errors. Never logs secrets.
"""

import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.token_cost_estimator import MODEL_PRICING, calculate_cost, count_tokens

logger = logging.getLogger("ClientVault.Observability")

ANSWER_PREVIEW_CHARS = 180
EMBEDDING_MODEL = "text-embedding-3-small"
SOURCE_LOG_FIELDS = ("marker", "chunk_id", "document_id", "section", "page", "score")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def normalize_question(question: str) -> str:
    """Case- and whitespace-insensitive form used in the cache key."""
    return re.sub(r"\s+", " ", question.strip().lower())


def cache_key(endpoint: str, question: str, settings: Dict[str, Any]) -> str:
    raw = json.dumps(
        {"endpoint": endpoint, "question": normalize_question(question), **settings},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class QueryCache:
    """Thread-safe TTL + LRU cache (sync endpoints run in a thread pool)."""

    def __init__(self, ttl_seconds: float = 900, max_entries: int = 256,
                 enabled: bool = True, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.enabled = enabled
        self._clock = clock
        self._items: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if self._clock() - entry["created_at"] > self.ttl_seconds:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return entry["value"]

    def set(self, key: str, value: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._items[key] = {"created_at": self._clock(), "value": value}
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


# ---------------------------------------------------------------------------
# Usage / cost
# ---------------------------------------------------------------------------

def estimate_usage(
    *,
    model: str,
    prompt_text: str,
    answer_text: str,
    question: str,
    llm_called: bool,
    embeddings_called: bool,
    model_usage: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Tokens and USD cost for one request that ran the pipeline (cache miss)."""
    if model_usage:
        input_tokens = int(model_usage.get("prompt_tokens", 0))
        output_tokens = int(model_usage.get("completion_tokens", 0))
        token_source = "model"
    else:
        input_tokens = count_tokens(prompt_text, model) if prompt_text else 0
        output_tokens = count_tokens(answer_text, model) if answer_text else 0
        token_source = "tiktoken-estimate"
    pricing_model = model if model in MODEL_PRICING else "gpt-4o-mini"
    generation_cost = calculate_cost(input_tokens, output_tokens, pricing_model)["total_cost_usd"]

    embedding_tokens = count_tokens(question, EMBEDDING_MODEL)
    embedding_cost = calculate_cost(embedding_tokens, 0, EMBEDDING_MODEL)["total_cost_usd"]

    equivalent = generation_cost + embedding_cost
    billed = (generation_cost if llm_called else 0.0) + (embedding_cost if embeddings_called else 0.0)
    return {
        "model": model,
        "token_source": token_source,
        "llm_called": llm_called,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "embedding_tokens": embedding_tokens,
        "estimated_cost_usd": round(equivalent, 8),
        "billed_cost_usd": round(billed, 8),
    }


def cache_hit_usage(original: Dict[str, Any]) -> Dict[str, Any]:
    """A cache hit spends nothing; record what the original request cost."""
    return {
        "model": original.get("model"),
        "token_source": "cache",
        "llm_called": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "embedding_tokens": 0,
        "estimated_cost_usd": 0.0,
        "billed_cost_usd": 0.0,
        "saved_estimated_cost_usd": original.get("estimated_cost_usd", 0.0),
        "saved_billed_cost_usd": original.get("billed_cost_usd", 0.0),
    }


# ---------------------------------------------------------------------------
# Structured request log
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Source metadata for the log (no chunk text)."""
    return [{f: s.get(f) for f in SOURCE_LOG_FIELDS} for s in sources]


def answer_preview(answer: str) -> str:
    flat = re.sub(r"\s+", " ", answer or "").strip()
    return flat if len(flat) <= ANSWER_PREVIEW_CHARS else flat[:ANSWER_PREVIEW_CHARS - 1] + "…"


class RequestLogger:
    """Append-only JSONL request log (one object per line)."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        self._lock = threading.Lock()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: Dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str)
        logger.info(line)
        if not self.path:
            return
        try:
            with self._lock, self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            logger.exception("Could not write request log to %s", self.path)


def read_records(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL records, skipping blank or corrupt lines."""
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping corrupt log line in %s", path)
    return records
