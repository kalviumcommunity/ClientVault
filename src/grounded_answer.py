"""
ClientVault — Grounded Answer Generation Engine

Generates grounded answers from retrieved context using the augmented RAG prompt.
Verifies answer claims against supporting chunks, includes source citations,
and handles empty retrieval / insufficient evidence with a clear fallback.

Provides a side-by-side comparison of direct LLM output vs grounded RAG output.
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
from src.context_injector import (
    assemble_context_budgeted,
    build_augmented_prompt,
    INSUFFICIENT_EVIDENCE_INSTRUCTION,
)
from src.chat_completion import load_llm_config, create_client, send_chat_completion
from src.token_cost_estimator import count_tokens

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.GroundedAnswer: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.GroundedAnswer")

DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "sample_grounded_comparison_output.log"


@dataclass
class GroundedAnswerResult:
    """Result of grounded answer generation with evidence verification."""
    query: str
    client_id: Optional[str]
    answer: str
    supporting_chunks: List[Dict[str, Any]]
    source_citations: List[str]
    context_token_count: int
    total_latency_ms: float
    insufficient_evidence: bool
    from_mock: bool
    verification_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonEntry:
    """Side-by-side comparison of direct LLM vs grounded RAG."""
    query: str
    direct_llm_answer: str
    grounded_answer: str
    grounded_latency_ms: float
    direct_latency_ms: float
    insufficient_evidence: bool
    sources_used: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Source citation extraction
# ---------------------------------------------------------------------------

def extract_source_citations(answer: str) -> List[str]:
    """Extract [N] source markers from an answer string."""
    import re
    return re.findall(r'\[\d+\]', answer)


def find_supporting_chunks(
    answer: str,
    chunks: List[Any],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Identify which retrieved chunks are cited in the answer."""
    cited_markers = extract_source_citations(answer)
    supporting: List[Dict[str, Any]] = []
    markers: List[str] = []

    for i, c in enumerate(chunks, 1):
        marker = f"[{i}]"
        if marker in cited_markers or marker in answer:
            supporting.append({
                "source_marker": marker,
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "section": c.section,
                "page": c.page,
                "score": round(c.hybrid_score, 4),
                "content_snippet": c.content[:200].replace("\n", " ") + "..." if len(c.content) > 200 else c.content.replace("\n", " "),
            })
            markers.append(f"{marker} {c.document_id}#{c.chunk_id.split('#')[-1] if '#' in c.chunk_id else c.chunk_id}")

    return supporting, markers


# ---------------------------------------------------------------------------
# Grounded answer generation
# ---------------------------------------------------------------------------

def generate_grounded_answer(
    query: str,
    client_id: Optional[str] = None,
    k: int = 5,
    max_context_tokens: int = 4096,
    reserve_tokens: int = 2048,
    force_mock: bool = False,
) -> GroundedAnswerResult:
    """Full grounded answer generation pipeline.

    1. Retrieve chunks (account-filtered if client_id provided)
    2. Assemble context within token budget
    3. Build augmented RAG prompt via existing template
    4. Generate answer via LLM (or mock fallback)
    5. Verify against supporting chunks
    """
    t0 = time.perf_counter()

    # Step 1: Retrieve
    retriever = FilteredRetriever(force_mock=force_mock)
    mf = MetadataFilter(client_id=client_id) if client_id else None
    res = retriever.search(query, k=k, metadata_filter=mf, target_client_id=client_id)
    chunks = res.chunks

    # Step 2 + 3: Assemble context + build augmented prompt
    ctx = assemble_context_budgeted(
        chunks, max_context_tokens=max_context_tokens, reserve_tokens=reserve_tokens
    )

    first = chunks[0] if chunks else None
    augmented = build_augmented_prompt(
        query=query,
        context_result=ctx,
        client_id=client_id or (first.client_id if first else "UNKNOWN"),
        document_id=first.document_id if first else "unknown",
        section=first.section if first else "General",
        page=first.page if first else 1,
    )

    # Step 4: Generate answer
    if ctx.insufficient_evidence:
        answer = INSUFFICIENT_EVIDENCE_INSTRUCTION
        from_mock = False
    else:
        config = load_llm_config()
        api_key = config.get("api_key", "")
        is_configured = bool(api_key) and api_key != "your_openai_api_key_here" and not api_key.startswith("local-")

        if force_mock or not is_configured:
            logger.info("LLM unavailable — using deterministic mock answer from retrieved sources")
            answer_lines = ["Grounded Answer (Mock Mode):"]
            answer_lines.append("")
            for s in ctx.sources_included:
                answer_lines.append(f"- Source {s.display}: relevant passage found in {s.document_id}")
            answer_lines.append("")
            answer_lines.append("Review the cited sources above for the complete procedure.")
            answer = "\n".join(answer_lines)
            from_mock = True
        else:
            logger.info("Calling LLM for grounded answer")
            client = create_client(config["base_url"], config["api_key"])
            messages = [
                {"role": "system", "content": "You are a grounded answer generator. Answer ONLY from the context provided. Cite sources as [N]. If context is insufficient, say so."},
                {"role": "user", "content": f"Context:\n{ctx.context_text}\n\nQuestion: {query}\n\nProvide a grounded answer with source citations."},
            ]
            response = send_chat_completion(messages=messages, config=config, client=client, temperature=0.0, max_tokens=500)
            if response.get("success"):
                answer = response["content"]
            else:
                answer = INSUFFICIENT_EVIDENCE_INSTRUCTION
            from_mock = False

    # Step 5: Verify against supporting chunks
    supporting, markers = find_supporting_chunks(answer, chunks)
    if ctx.insufficient_evidence:
        verification = "No evidence found — insufficient-evidence fallback returned."
    elif not supporting:
        verification = "WARNING: answer does not cite any retrieved source chunk."
    else:
        verification = f"Answer cites {len(supporting)} source(s): {', '.join(markers)}"

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return GroundedAnswerResult(
        query=query,
        client_id=client_id,
        answer=answer,
        supporting_chunks=supporting,
        source_citations=markers,
        context_token_count=ctx.total_tokens,
        total_latency_ms=round(elapsed_ms, 1),
        insufficient_evidence=ctx.insufficient_evidence,
        from_mock=from_mock,
        verification_notes=verification,
    )


# ---------------------------------------------------------------------------
# Direct LLM comparison
# ---------------------------------------------------------------------------

def generate_direct_llm(query: str, force_mock: bool = True) -> Tuple[str, float]:
    """Generate answer WITHOUT retrieval context — direct LLM call."""
    t0 = time.perf_counter()
    if force_mock:
        answer = "Direct LLM Answer (Mock Mode): I don't have specific information about that without accessing the knowledge base."
    else:
        config = load_llm_config()
        api_key = config.get("api_key", "")
        if not api_key or api_key == "your_openai_api_key_here":
            answer = "Direct LLM Answer (No API Key): No credentials configured."
        else:
            client = create_client(config["base_url"], api_key)
            response = send_chat_completion(
                messages=[{"role": "user", "content": query}],
                config=config, client=client, temperature=0.0, max_tokens=300,
            )
            answer = response.get("content", "No response from LLM.")
    elapsed = (time.perf_counter() - t0) * 1000
    return answer, round(elapsed, 1)


def run_comparison(
    query: str,
    client_id: Optional[str] = None,
    k: int = 5,
    force_mock: bool = True,
) -> ComparisonEntry:
    """Run side-by-side comparison of direct LLM vs grounded RAG."""
    logger.info("Running comparison for query: %s", query)

    # Direct LLM
    direct_answer, direct_latency = generate_direct_llm(query, force_mock=force_mock)

    # Grounded RAG
    grounded = generate_grounded_answer(
        query=query, client_id=client_id, k=k, force_mock=force_mock,
    )

    return ComparisonEntry(
        query=query,
        direct_llm_answer=direct_answer,
        grounded_answer=grounded.answer,
        grounded_latency_ms=grounded.total_latency_ms,
        direct_latency_ms=direct_latency,
        insufficient_evidence=grounded.insufficient_evidence,
        sources_used=grounded.source_citations,
    )


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------

def format_report(comparison: ComparisonEntry) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("  ClientVault — Grounded Answer Generation Comparison")
    lines.append("=" * 80)
    lines.append(f"  Query:              {comparison.query}")
    lines.append(f"  Insufficient evid.: {comparison.insufficient_evidence}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  [Direct LLM] (no retrieval context)")
    lines.append("-" * 80)
    lines.append(f"  Latency: {comparison.direct_latency_ms} ms")
    lines.append(f"  Answer:  {comparison.direct_llm_answer}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  [Grounded RAG] (retrieval + context injection)")
    lines.append("-" * 80)
    lines.append(f"  Latency: {comparison.grounded_latency_ms} ms")
    lines.append(f"  Sources: {', '.join(comparison.sources_used) if comparison.sources_used else '(none)'}")
    lines.append(f"  Answer:  {comparison.grounded_answer}")
    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ClientVault Grounded Answer Generation")
    parser.add_argument("--query", type=str,
                        default="What is the initial response time for a Severity 1 critical outage?")
    parser.add_argument("--client-id", type=str, default="NEXUS-002")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--mock", action="store_true", default=True)
    parser.add_argument("--no-mock", action="store_false", dest="mock")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_LOG))
    args = parser.parse_args()

    comparison = run_comparison(
        query=args.query,
        client_id=args.client_id,
        k=args.k,
        force_mock=args.mock,
    )

    report = format_report(comparison)
    print(report)

    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")

    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(comparison.to_dict(), indent=2), encoding="utf-8")
    logger.info("Report saved to %s", output_path)


if __name__ == "__main__":
    main()
