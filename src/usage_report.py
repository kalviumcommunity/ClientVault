"""
ClientVault — Usage report from the RAG API request log (JSONL).

Summarises requests over time: totals, cache hits, tokens, estimated and
billed cost, latency (overall and cache hit vs miss), status counts, errors,
and per-period buckets.

    python -m src.usage_report                       # text report of the default log
    python -m src.usage_report --log path.jsonl --json report.json --bucket hour
"""

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag_observability import normalize_question, read_records

DEFAULT_LOG = PROJECT_ROOT / "outputs" / "logs" / "rag_requests.jsonl"
BUCKET_CHARS = {"day": 10, "hour": 13, "minute": 16}  # ISO prefix: 2026-10-28 / …T07 / …T07:41


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return round(ordered[rank - 1], 2)


def _avg(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def summarize_usage(records: List[Dict[str, Any]], bucket: str = "day",
                    include_questions: bool = False, recent_errors: int = 5) -> Dict[str, Any]:
    cut = BUCKET_CHARS[bucket]
    usage = lambda r: r.get("usage") or {}
    cacheable = [r for r in records if r.get("cache_hit") is not None]
    hits = [r for r in cacheable if r["cache_hit"]]
    latencies = [r["latency_ms"] for r in records if isinstance(r.get("latency_ms"), (int, float))]
    errors = [r for r in records if r.get("status") in ("error", "rejected")]

    periods: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"requests": 0, "cache_hits": 0,
                                                              "estimated_cost_usd": 0.0, "billed_cost_usd": 0.0,
                                                              "errors": 0, "_lat": []})
    for r in records:
        p = periods[r.get("timestamp", "")[:cut] or "unknown"]
        p["requests"] += 1
        p["cache_hits"] += 1 if r.get("cache_hit") else 0
        p["estimated_cost_usd"] += usage(r).get("estimated_cost_usd", 0.0)
        p["billed_cost_usd"] += usage(r).get("billed_cost_usd", 0.0)
        p["errors"] += 1 if r.get("status") in ("error", "rejected") else 0
        if isinstance(r.get("latency_ms"), (int, float)):
            p["_lat"].append(r["latency_ms"])

    over_time = []
    for period in sorted(periods):
        p = periods[period]
        over_time.append({
            "period": period,
            "requests": p["requests"],
            "cache_hits": p["cache_hits"],
            "estimated_cost_usd": round(p["estimated_cost_usd"], 8),
            "billed_cost_usd": round(p["billed_cost_usd"], 8),
            "avg_latency_ms": _avg(p["_lat"]),
            "errors": p["errors"],
        })

    summary: Dict[str, Any] = {
        "window": {
            "first": min((r["timestamp"] for r in records if r.get("timestamp")), default=None),
            "last": max((r["timestamp"] for r in records if r.get("timestamp")), default=None),
        },
        "total_requests": len(records),
        "by_endpoint": dict(Counter(r.get("endpoint", "unknown") for r in records)),
        "by_status": dict(Counter(r.get("status", "unknown") for r in records)),
        "cache": {
            "lookups": len(cacheable),
            "hits": len(hits),
            "misses": len(cacheable) - len(hits),
            "hit_rate": round(len(hits) / len(cacheable), 3) if cacheable else 0.0,
            "saved_estimated_cost_usd": round(sum(usage(r).get("saved_estimated_cost_usd", 0.0) for r in hits), 8),
        },
        "tokens": {
            "input": sum(usage(r).get("input_tokens", 0) for r in records),
            "output": sum(usage(r).get("output_tokens", 0) for r in records),
            "embedding": sum(usage(r).get("embedding_tokens", 0) for r in records),
            "sources": dict(Counter(usage(r).get("token_source", "none") for r in records)),
        },
        "cost": {
            "estimated_cost_usd": round(sum(usage(r).get("estimated_cost_usd", 0.0) for r in records), 8),
            "billed_cost_usd": round(sum(usage(r).get("billed_cost_usd", 0.0) for r in records), 8),
            "llm_calls": sum(1 for r in records if usage(r).get("llm_called")),
        },
        "latency_ms": {
            "avg": _avg(latencies),
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "avg_cache_hit": _avg([r["latency_ms"] for r in hits if "latency_ms" in r]),
            "avg_cache_miss": _avg([r["latency_ms"] for r in cacheable if not r["cache_hit"] and "latency_ms" in r]),
        },
        "errors": {
            "count": len(errors),
            "recent": [
                {k: r.get(k) for k in ("timestamp", "request_id", "endpoint", "status", "error")}
                for r in errors[-recent_errors:]
            ],
        },
        "bucket": bucket,
        "over_time": over_time,
    }
    if include_questions:
        # Group the way the cache does (case/whitespace-insensitive); show the first wording seen.
        counts: Counter = Counter()
        wording: Dict[str, str] = {}
        for r in records:
            if r.get("question"):
                norm = normalize_question(r["question"])
                counts[norm] += 1
                wording.setdefault(norm, r["question"])
        summary["top_questions"] = [{"question": wording[q], "requests": n} for q, n in counts.most_common(5)]
    return summary


def format_report(s: Dict[str, Any]) -> str:
    money = lambda v: f"${v:.6f}"
    lines = [
        "=" * 78,
        "  ClientVault RAG API — Usage Report",
        "=" * 78,
        f"  Window:            {s['window']['first']}  →  {s['window']['last']}",
        f"  Total requests:    {s['total_requests']}   by endpoint: {s['by_endpoint']}",
        f"  By status:         {s['by_status']}",
        "",
        f"  Cache:             {s['cache']['hits']} hits / {s['cache']['lookups']} lookups "
        f"(hit rate {s['cache']['hit_rate']:.1%}), saved ≈ {money(s['cache']['saved_estimated_cost_usd'])}",
        f"  Tokens:            input {s['tokens']['input']}, output {s['tokens']['output']}, "
        f"embedding {s['tokens']['embedding']}   (sources: {s['tokens']['sources']})",
        f"  Cost (estimated):  {money(s['cost']['estimated_cost_usd'])}   billed: {money(s['cost']['billed_cost_usd'])}"
        f"   LLM calls: {s['cost']['llm_calls']}",
        f"  Latency (ms):      avg {s['latency_ms']['avg']}, p50 {s['latency_ms']['p50']}, p95 {s['latency_ms']['p95']}"
        f"   | hit avg {s['latency_ms']['avg_cache_hit']}, miss avg {s['latency_ms']['avg_cache_miss']}",
        f"  Errors:            {s['errors']['count']}",
    ]
    for e in s["errors"]["recent"]:
        lines.append(f"    - {e['timestamp']} {e['endpoint']} [{e['status']}] {e['error']} (req {e['request_id']})")
    lines += ["", f"  Usage over time (per {s['bucket']}):",
              f"    {'period':<14} {'requests':>8} {'hits':>6} {'est. cost':>12} {'avg ms':>9} {'errors':>7}"]
    for p in s["over_time"]:
        lines.append(f"    {p['period']:<14} {p['requests']:>8} {p['cache_hits']:>6} "
                     f"{money(p['estimated_cost_usd']):>12} {str(p['avg_latency_ms']):>9} {p['errors']:>7}")
    if s.get("top_questions"):
        lines += ["", "  Most repeated questions:"]
        lines += [f"    {q['requests']:>3} × {q['question']}" for q in s["top_questions"]]
    lines.append("=" * 78)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise the RAG API request log.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="JSONL request log")
    parser.add_argument("--bucket", choices=sorted(BUCKET_CHARS), default="day")
    parser.add_argument("--json", type=Path, help="Also write the summary as JSON here")
    args = parser.parse_args()

    records = read_records(args.log)
    if not records:
        print(f"No request records found in {args.log}")
        return
    summary = summarize_usage(records, bucket=args.bucket, include_questions=True)
    print(format_report(summary))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"\nJSON summary written to {args.json}")


if __name__ == "__main__":
    main()
