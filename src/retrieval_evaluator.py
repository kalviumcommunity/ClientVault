"""
ClientVault — Retrieval Quality Evaluation Module (Recall@k & Precision@k)

Computes recall@k and precision@k using the existing FilteredRetriever
and a labelled query dataset. Handles edge cases: empty results, queries
with no relevant labels (unsupported), duplicate chunk IDs, division by
zero. Produces per-query results, macro-averaged metrics, safe-rejection
statistics, and a concise failure analysis.
"""

import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.filtered_retriever import FilteredRetriever, MetadataFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.Evaluator: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.Evaluator")

DEFAULT_EVAL_LOG = PROJECT_ROOT / "retrieval_evaluation_output.log"
DEFAULT_EVAL_JSON = PROJECT_ROOT / "retrieval_evaluation_results.json"
DEFAULT_QUERIES_PATH = PROJECT_ROOT / "retrieval_eval_queries.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EvalQueryResult:
    """Per-query evaluation result."""
    query_id: str
    query: str
    target_client_id: Optional[str]
    is_out_of_domain: bool
    relevant_chunk_ids: List[str]
    retrieved_chunk_ids: List[str]
    retrieved_chunk_ids_set: set  # deduplicated for scoring
    hits_at_k: List[str]
    return_count: int
    recall_at_k: Optional[float]   # None when |relevant| == 0
    precision_at_k: Optional[float]  # None when |relevant| == 0
    safe_rejected: Optional[bool]   # only meaningful for ood queries

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query": self.query,
            "target_client_id": self.target_client_id,
            "is_out_of_domain": self.is_out_of_domain,
            "relevant_chunk_ids": self.relevant_chunk_ids,
            "retrieved_chunk_ids": self.retrieved_chunk_ids,
            "hits_at_k": self.hits_at_k,
            "return_count": self.return_count,
            "recall_at_k": round(self.recall_at_k, 4) if self.recall_at_k is not None else None,
            "precision_at_k": round(self.precision_at_k, 4) if self.precision_at_k is not None else None,
            "safe_rejected": self.safe_rejected,
        }


@dataclass
class EvalSummary:
    """Aggregated evaluation summary."""
    total_queries: int
    in_domain_queries: int
    out_of_domain_queries: int
    macro_avg_recall: Optional[float]
    macro_avg_precision: Optional[float]
    safe_rejection_rate: Optional[float]
    queries_with_recall_zero: int
    queries_with_precision_zero: int
    per_query: List[EvalQueryResult]
    failure_analysis: str


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

def compute_recall_precision(
    retrieved_ids: List[str],
    relevant_ids: List[str],
) -> Tuple[Optional[float], Optional[float]]:
    """Recall@k, Precision@k given retrieved and relevant lists.

    Uses deduplicated set intersection. Returns (None, None) when
    |relevant| == 0 (division by zero guarded).
    """
    if not relevant_ids:
        return None, None
    retrieved_set = set(retrieved_ids)
    relevant_set = set(relevant_ids)
    hits = len(retrieved_set & relevant_set)
    recall = hits / len(relevant_set) if relevant_set else None
    precision = hits / len(retrieved_ids) if retrieved_ids else 0.0
    return recall, precision


def evaluate_query_set(
    queries_path: Path = DEFAULT_QUERIES_PATH,
    k: int = 5,
    retriever: Optional[FilteredRetriever] = None,
    search_mode: str = "hybrid",
    score_threshold: Optional[float] = None,
) -> EvalSummary:
    """Run the full evaluation on all queries in the labelled dataset."""
    with open(queries_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    if retriever is None:
        retriever = FilteredRetriever(force_mock="OPENAI_API_KEY" not in __builtins__ or True)

    access_retriever = retriever.vector_retriever
    access_retriever.ensure_corpus_indexed()

    per_query: List[EvalQueryResult] = []
    queries = dataset["queries"]

    for q in queries:
        qid = q["query_id"]
        query_text = q["query"]
        client = q.get("target_client_id")
        relevant = q.get("relevant_chunk_ids", [])
        ood = q.get("is_out_of_domain", False)

        # Build metadata filter
        mf = MetadataFilter(client_id=client) if client else None

        # Retrieve
        res = retriever.search(
            query=query_text,
            k=k,
            metadata_filter=mf,
            search_mode=search_mode,
            target_client_id=client,
            score_threshold=score_threshold,
        )

        retrieved = [c.chunk_id for c in res.chunks]
        retrieved_set = list(set(retrieved))
        hits = [rid for rid in retrieved_set if rid in relevant]

        recall, precision = compute_recall_precision(retrieved, relevant)

        safe_rejected = (len(retrieved) == 0) if ood else None

        eqr = EvalQueryResult(
            query_id=qid,
            query=query_text,
            target_client_id=client,
            is_out_of_domain=ood,
            relevant_chunk_ids=relevant,
            retrieved_chunk_ids=retrieved,
            retrieved_chunk_ids_set=set(retrieved),
            hits_at_k=hits,
            return_count=len(retrieved),
            recall_at_k=recall,
            precision_at_k=precision,
            safe_rejected=safe_rejected,
        )
        per_query.append(eqr)

    # Aggregate
    in_domain = [r for r in per_query if not r.is_out_of_domain]
    ood_queries = [r for r in per_query if r.is_out_of_domain]

    rec_vals = [r.recall_at_k for r in in_domain if r.recall_at_k is not None]
    prec_vals = [r.precision_at_k for r in in_domain if r.precision_at_k is not None]

    macro_rec = sum(rec_vals) / len(rec_vals) if rec_vals else None
    macro_prec = sum(prec_vals) / len(prec_vals) if prec_vals else None

    safe_rej_count = sum(1 for r in ood_queries if r.safe_rejected)
    safe_rate = safe_rej_count / len(ood_queries) if ood_queries else None

    zero_rec = sum(1 for r in in_domain if r.recall_at_k is not None and r.recall_at_k == 0.0)
    zero_prec = sum(1 for r in in_domain if r.precision_at_k is not None and r.precision_at_k == 0.0)

    # Build failure analysis
    failures = [r for r in in_domain if r.recall_at_k is None or r.recall_at_k < 1.0]
    fa_lines: List[str] = [
        f"FAILURE ANALYSIS — queries with recall<1.0 ({len(failures)}/{len(in_domain)})",
    ]
    for r in failures:
        fa_lines.append(f"")
        fa_lines.append(f"  [{r.query_id}] recall={r.recall_at_k}, precision={r.precision_at_k}")
        fa_lines.append(f"    query: {r.query[:80]}")
        fa_lines.append(f"    relevant: {r.relevant_chunk_ids}")
        fa_lines.append(f"    retrieved: {r.retrieved_chunk_ids}")
        fa_lines.append(f"    hits: {r.hits_at_k}")
        # likely causes
        reasons = []
        # missing a relevant chunk
        missed = set(r.relevant_chunk_ids) - set(r.retrieved_chunk_ids)
        if missed:
            reasons.append(f"missed relevant chunk(s) {missed}")
        # unexpected client is a metadata-filter issue (but shouldn't happen with filter)
        if r.return_count == 0:
            reasons.append("zero chunks returned — score threshold too aggressive or query out-of-scope")
        if r.return_count < 5 and r.recall_at_k is not None and r.recall_at_k < 1.0:
            reasons.append("possible embedding mismatch between query wording and chunk content")
        fa_lines.append(f"    likely causes: {'; '.join(reasons) if reasons else 'marginal similarity score — re-rank candidate'}")
    fa_lines.append("")
    fa_lines.append(f"Out-of-domain safe rejection: {safe_rej_count}/{len(ood_queries)} ({100*safe_rate:.1f}%)" if ood_queries else "No out-of-domain queries in dataset.")

    return EvalSummary(
        total_queries=len(queries),
        in_domain_queries=len(in_domain),
        out_of_domain_queries=len(ood_queries),
        macro_avg_recall=macro_rec,
        macro_avg_precision=macro_prec,
        safe_rejection_rate=safe_rate,
        queries_with_recall_zero=zero_rec,
        queries_with_precision_zero=zero_prec,
        per_query=per_query,
        failure_analysis="\n".join(fa_lines),
    )


def format_evaluation_report(summary: EvalSummary) -> str:
    """Produce a human-readable evaluation report."""
    lines = []
    lines.append("=" * 80)
    lines.append("  ClientVault — Retrieval Quality Evaluation Report")
    lines.append("=" * 80)
    lines.append(f"  Dataset queries        : {summary.total_queries}")
    lines.append(f"  In-domain              : {summary.in_domain_queries}")
    lines.append(f"  Out-of-domain          : {summary.out_of_domain_queries}")
    lines.append(f"  Macro avg recall@k     : {round(summary.macro_avg_recall, 4) if summary.macro_avg_recall is not None else 'N/A'}")
    lines.append(f"  Macro avg precision@k  : {round(summary.macro_avg_precision, 4) if summary.macro_avg_precision is not None else 'N/A'}")
    lines.append(f"  Safe rejection rate    : {round(summary.safe_rejection_rate, 4) if summary.safe_rejection_rate is not None else 'N/A'}")
    lines.append(f"  Queries with recall=0  : {summary.queries_with_recall_zero}")
    lines.append(f"  Queries with prec=0    : {summary.queries_with_precision_zero}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("Per-query results:")
    lines.append("-" * 80)
    header = f"{'ID':<8} {'Recall':<10} {'Prec':<10} {'Hits':<15} {'Retrieved':<10} {'Relevant':<10} {'OOD':<5}"
    lines.append(header)
    lines.append("-" * len(header))
    for r in summary.per_query:
        rec_s = f"{r.recall_at_k:.4f}" if r.recall_at_k is not None else "-"
        prec_s = f"{r.precision_at_k:.4f}" if r.precision_at_k is not None else "-"
        hits_s = ",".join(r.hits_at_k) if r.hits_at_k else "(none)"
        lines.append(f"{r.query_id:<8} {rec_s:<10} {prec_s:<10} {hits_s:<15} {r.return_count:<10d} {len(r.relevant_chunk_ids):<10d} {'Y' if r.is_out_of_domain else 'N':<5}")
    lines.append("")
    lines.append("=" * 80)
    lines.append(summary.failure_analysis)
    lines.append("=" * 80)
    return "\n".join(lines)


def save_evaluation_results(
    summary: EvalSummary,
    log_path: Path = DEFAULT_EVAL_LOG,
    json_path: Path = DEFAULT_EVAL_JSON,
):
    """Persist report to log file and structured JSON."""
    report = format_evaluation_report(summary)
    log_path.write_text(report, encoding="utf-8")
    logger.info("Saved evaluation report to %s", log_path)

    json_data = {
        "total_queries": summary.total_queries,
        "in_domain_queries": summary.in_domain_queries,
        "out_of_domain_queries": summary.out_of_domain_queries,
        "macro_avg_recall": round(summary.macro_avg_recall, 4) if summary.macro_avg_recall is not None else None,
        "macro_avg_precision": round(summary.macro_avg_precision, 4) if summary.macro_avg_precision is not None else None,
        "safe_rejection_rate": round(summary.safe_rejection_rate, 4) if summary.safe_rejection_rate is not None else None,
        "queries_with_recall_zero": summary.queries_with_recall_zero,
        "queries_with_precision_zero": summary.queries_with_precision_zero,
        "per_query": [r.to_dict() for r in summary.per_query],
        "failure_analysis": summary.failure_analysis,
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    logger.info("Saved structured results to %s", json_path)


def run_evaluation(
    queries_path: Path = DEFAULT_QUERIES_PATH,
    k: int = 5,
    search_mode: str = "hybrid",
    score_threshold: Optional[float] = None,
    force_mock: bool = True,
) -> EvalSummary:
    """Convenience entrypoint: create retriever, run evaluation, save results."""
    r = FilteredRetriever(force_mock=force_mock)
    summary = evaluate_query_set(
        queries_path=queries_path,
        k=k,
        retriever=r,
        search_mode=search_mode,
        score_threshold=score_threshold,
    )
    save_evaluation_results(summary)
    return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ClientVault retrieval evaluation")
    parser.add_argument("--queries", type=str, default=str(DEFAULT_QUERIES_PATH))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--search-mode", type=str, default="hybrid", choices=["vector", "hybrid"])
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument("--no-mock", action="store_true", help="Use live API if available")
    args = parser.parse_args()

    summary = run_evaluation(
        queries_path=Path(args.queries),
        k=args.k,
        search_mode=args.search_mode,
        score_threshold=args.score_threshold,
        force_mock=not args.no_mock,
    )
    print(format_evaluation_report(summary))


if __name__ == "__main__":
    main()
