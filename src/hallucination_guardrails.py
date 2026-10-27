"""
ClientVault — Hallucination Guardrails Engine

Detects weak retrieval (empty results, low relevance scores, too few
chunks above threshold) and refuses BEFORE generation with a clear
'I don't have enough reliable context' response.

Configurable relevance threshold defaults to 0.60, chosen empirically
from retrieval evaluation: top-3 factual chunks score 0.82–0.97,
while out-of-domain / low-relevance chunks score 0.40–0.60.
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.filtered_retriever import FilteredRetriever, MetadataFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.Guardrails: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.Guardrails")

DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "sample_guardrails_output.log"

# Default threshold: 0.60. Rationale documented in docstring above.
# Tune by running: python src/hallucination_guardrails.py --threshold 0.70 --query "your query"
DEFAULT_RELEVANCE_THRESHOLD = 0.60
MIN_CHUNKS_ABOVE_THRESHOLD = 1

REFUSAL_MESSAGE = (
    "I don't have enough reliable context to answer that. "
    "The retrieved evidence does not contain sufficient relevant information "
    "to provide a grounded answer."
)


@dataclass
class RetrievalAssessment:
    """Assessment of retrieval quality before generation."""
    total_chunks_retrieved: int
    chunks_above_threshold: int
    highest_score: float
    lowest_score: float
    passes_guard: bool
    threshold_used: float
    refusal_reason: Optional[str]


@dataclass
class GuardedResult:
    """Final output after guardrail check — either refused or passed."""
    query: str
    client_id: Optional[str]
    passed_guard: bool
    refusal_reason: Optional[str]
    refusal_message: Optional[str]
    assessment: RetrievalAssessment
    threshold_used: float
    source_count: int
    chunks_above_threshold: int
    answer: str  # refusal message or actual grounded answer
    sources: List[Dict[str, Any]]


def assess_retrieval(
    chunks: List[Any],
    threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    min_chunks: int = MIN_CHUNKS_ABOVE_THRESHOLD,
) -> RetrievalAssessment:
    """Evaluate whether retrieved chunks provide sufficient evidence.

    Returns an assessment with pass/fail status and detailed reasons.
    """
    total = len(chunks)
    above = sum(1 for c in chunks if c.hybrid_score >= threshold)
    scores = [c.hybrid_score for c in chunks]
    highest = max(scores) if scores else 0.0
    lowest = min(scores) if scores else 0.0

    reasons: List[str] = []

    if total == 0:
        reasons.append("No chunks retrieved from vector database")
    if above < min_chunks:
        reasons.append(
            f"Only {above}/{total} chunks above threshold {threshold} "
            f"(highest: {highest:.4f})"
        )
    if total > 0 and above == 0:
        reasons.append(f"No chunks meet minimum score threshold {threshold}")

    passes = len(reasons) == 0

    return RetrievalAssessment(
        total_chunks_retrieved=total,
        chunks_above_threshold=above,
        highest_score=round(highest, 4),
        lowest_score=round(lowest, 4),
        passes_guard=passes,
        threshold_used=threshold,
        refusal_reason="; ".join(reasons) if reasons else None,
    )


def guarded_generate(
    query: str,
    client_id: Optional[str] = None,
    k: int = 5,
    threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    min_chunks: int = MIN_CHUNKS_ABOVE_THRESHOLD,
    force_mock: bool = True,
) -> GuardedResult:
    """Full guardrail pipeline: retrieve → assess → refuse or generate."""
    retriever = FilteredRetriever(force_mock=force_mock)
    mf = MetadataFilter(client_id=client_id) if client_id else None
    res = retriever.search(query, k=k, metadata_filter=mf, target_client_id=client_id)
    chunks = res.chunks

    # Assess before generation
    assessment = assess_retrieval(chunks, threshold=threshold, min_chunks=min_chunks)

    sources = [
        {
            "marker": f"[{i}]",
            "chunk_id": c.chunk_id,
            "document_id": c.document_id,
            "section": c.section,
            "page": c.page,
            "score": round(c.hybrid_score, 4),
        }
        for i, c in enumerate(chunks, 1)
    ]

    if not assessment.passes_guard:
        return GuardedResult(
            query=query,
            client_id=client_id,
            passed_guard=False,
            refusal_reason=assessment.refusal_reason,
            refusal_message=REFUSAL_MESSAGE,
            assessment=assessment,
            threshold_used=threshold,
            source_count=len(chunks),
            chunks_above_threshold=assessment.chunks_above_threshold,
            answer=REFUSAL_MESSAGE,
            sources=sources,
        )

    # Generate grounded answer (mock mode)
    first = chunks[0]
    answer_lines = ["Grounded Answer (Sufficient Evidence):", ""]
    for i, c in enumerate(chunks, 1):
        answer_lines.append(
            f"- Source [{i}]: {c.document_id}, Section {c.section} "
            f"(score: {c.hybrid_score:.4f})"
        )
    answer_lines.append("")
    answer_lines.append("The above sources provide sufficient relevant context.")
    answer = "\n".join(answer_lines)

    return GuardedResult(
        query=query,
        client_id=client_id,
        passed_guard=True,
        refusal_reason=None,
        refusal_message=None,
        assessment=assessment,
        threshold_used=threshold,
        source_count=len(chunks),
        chunks_above_threshold=assessment.chunks_above_threshold,
        answer=answer,
        sources=sources,
    )


def format_report(result: GuardedResult) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("  ClientVault — Hallucination Guardrails Report")
    lines.append("=" * 80)
    lines.append(f"  Query:                   {result.query}")
    lines.append(f"  Client ID:               {result.client_id or '(none)'}")
    lines.append(f"  Threshold:               {result.threshold_used}")
    lines.append(f"  Chunks retrieved:        {result.assessment.total_chunks_retrieved}")
    lines.append(f"  Chunks above threshold:  {result.assessment.chunks_above_threshold}")
    lines.append(f"  Highest score:           {result.assessment.highest_score}")
    lines.append(f"  Lowest score:            {result.assessment.lowest_score}")
    lines.append(f"  Guard passed:            {result.passed_guard}")
    lines.append(f"  Refusal reason:          {result.refusal_reason or '(none)'}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  Sources:")
    lines.append("-" * 80)
    for s in result.sources:
        lines.append(f"  {s['marker']} {s['document_id']}#{s['chunk_id'].split('#')[-1]}  "
                      f"(§{s['section']}, p.{s['page']}) score={s['score']}")
    lines.append("")
    lines.append("-" * 80)
    lines.append(f"  {'REFUSAL' if not result.passed_guard else 'ANSWER'}:")
    lines.append("-" * 80)
    lines.append(f"  {result.answer}")
    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ClientVault Hallucination Guardrails")
    parser.add_argument("--query", type=str, default="What is the Sev-1 response time?")
    parser.add_argument("--client-id", type=str, default="NEXUS-002")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=DEFAULT_RELEVANCE_THRESHOLD)
    parser.add_argument("--min-chunks", type=int, default=MIN_CHUNKS_ABOVE_THRESHOLD)
    parser.add_argument("--mock", action="store_true", default=True)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_LOG))
    args = parser.parse_args()

    result = guarded_generate(
        query=args.query,
        client_id=args.client_id,
        k=args.k,
        threshold=args.threshold,
        min_chunks=args.min_chunks,
        force_mock=args.mock,
    )
    report = format_report(result)
    print(report)

    Path(args.output).write_text(report, encoding="utf-8")
    json_path = Path(args.output).with_suffix(".json")
    json_path.write_text(json.dumps({
        "query": result.query,
        "client_id": result.client_id,
        "passed_guard": result.passed_guard,
        "refusal_reason": result.refusal_reason,
        "refusal_message": result.refusal_message,
        "threshold_used": result.threshold_used,
        "total_chunks": result.assessment.total_chunks_retrieved,
        "chunks_above_threshold": result.assessment.chunks_above_threshold,
        "highest_score": result.assessment.highest_score,
        "lowest_score": result.assessment.lowest_score,
        "answer": result.answer,
        "sources": result.sources,
    }, indent=2), encoding="utf-8")
    logger.info("Report saved to %s", args.output)


if __name__ == "__main__":
    main()
