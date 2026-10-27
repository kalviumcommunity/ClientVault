"""
ClientVault — End-to-End RAG Pipeline Orchestrator

Connects existing components into a complete query-to-answer pipeline:
  embed_query → retrieve_context → assemble_context → generate_answer → answer_query

Handles empty retrieval with the PRD-mandated INSUFFICIENT EVIDENCE fallback.
Supports deterministic mock mode for environments without an API key.
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.chat_completion import (
    load_llm_config,
    create_client,
    send_chat_completion,
    load_default_system_prompt,
)
from src.filtered_retriever import FilteredRetriever, MetadataFilter, FilteredRetrievedChunk
from src.prompt_template import render_support_chat_messages
from src.vector_db import load_vector_db_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.RAG: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.RAG")

DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "sample_rag_output.log"

INSUFFICIENT_EVIDENCE_FALLBACK = (
    "INSUFFICIENT EVIDENCE: No approved source in this client's knowledge base "
    "supports this procedure. Please escalate to the Account Lead or consult "
    "the designated runbook."
)


@dataclass
class RAGContext:
    """Formatted context assembled from retrieved chunks."""
    text: str
    citations: List[Dict[str, Any]]
    chunk_count: int


@dataclass
class RAGResult:
    """Complete end-to-end RAG pipeline result."""
    query: str
    client_id: Optional[str]
    answer: str
    retrieved_chunks: List[FilteredRetrievedChunk]
    context: RAGContext
    latency_ms: float
    insufficient_evidence: bool
    from_mock: bool


# ---------------------------------------------------------------------------
# Stage 1: Embed Query
# ---------------------------------------------------------------------------

def embed_query(retriever: FilteredRetriever, query: str) -> List[float]:
    """Embed a user query using the existing retriever's embedder."""
    return retriever.vector_retriever.embed_query(query)


# ---------------------------------------------------------------------------
# Stage 2: Retrieve Context
# ---------------------------------------------------------------------------

def retrieve_context(
    retriever: FilteredRetriever,
    query: str,
    k: int = 5,
    client_id: Optional[str] = None,
    search_mode: str = "hybrid",
    score_threshold: Optional[float] = None,
) -> List[FilteredRetrievedChunk]:
    """Retrieve top-k relevant chunks using the existing FilteredRetriever."""
    mf = MetadataFilter(client_id=client_id) if client_id else None
    res = retriever.search(
        query=query,
        k=k,
        metadata_filter=mf,
        search_mode=search_mode,
        target_client_id=client_id,
        score_threshold=score_threshold,
    )
    return res.chunks


# ---------------------------------------------------------------------------
# Stage 3: Assemble Context
# ---------------------------------------------------------------------------

def assemble_context(chunks: List[FilteredRetrievedChunk]) -> RAGContext:
    """Format retrieved chunks into a single context block with source citations."""
    if not chunks:
        return RAGContext(text="", citations=[], chunk_count=0)

    parts: List[str] = []
    citations: List[Dict[str, Any]] = []

    for i, c in enumerate(chunks, 1):
        citation = {
            "rank": i,
            "chunk_id": c.chunk_id,
            "document_id": c.document_id,
            "section": c.section,
            "page": c.page,
            "client_id": c.client_id,
            "hybrid_score": round(c.hybrid_score, 4),
        }
        citations.append(citation)
        parts.append(
            f"[Source: {c.document_id}, Section: {c.section}, Page: {c.page}]\n"
            f"{c.content.strip()}"
        )

    return RAGContext(
        text="\n\n---\n\n".join(parts),
        citations=citations,
        chunk_count=len(chunks),
    )


# ---------------------------------------------------------------------------
# Stage 4: Generate Answer
# ---------------------------------------------------------------------------

def generate_answer(
    query: str,
    client_id: Optional[str],
    context: RAGContext,
    force_mock: bool = False,
) -> Tuple[str, bool]:
    """
    Generate a grounded answer from retrieved context.
    
    Returns (answer_text, from_mock_flag).
    
    If context is empty, returns the INSUFFICIENT EVIDENCE fallback
    immediately without calling the LLM.
    """
    # Empty retrieval — return fallback immediately
    if context.chunk_count == 0:
        logger.info("Empty retrieval — returning INSUFFICIENT EVIDENCE fallback")
        return INSUFFICIENT_EVIDENCE_FALLBACK, False

    # Check LLM availability
    config = load_llm_config()
    api_key = config.get("api_key", "")
    is_configured = bool(api_key) and api_key != "your_openai_api_key_here"

    # Deterministic mock fallback
    if force_mock or not is_configured:
        logger.info("API key not configured — using deterministic context summarization fallback")
        first = context.citations[0]
        lines = [
            f"Based on the retrieved knowledge base entry for {first['client_id']}:",
            "",
            f"Source document: {first['document_id']}",
            f"Section: {first['section']}, Page: {first['page']}",
            "",
        ]
        # Extract key sentences from the first chunk
        for cit in context.citations[:3]:
            lines.append(f"- Relevant passage from {cit['document_id']} "
                         f"(§{cit['section']}, p.{cit['page']}) [score: {cit['hybrid_score']}]")
        lines.append("")
        lines.append("Review the cited sources above for the complete procedure.")
        return "\n".join(lines), True

    # Live LLM path
    logger.info("Calling LLM for grounded answer generation")
    client = create_client(base_url=config["base_url"], api_key=api_key)

    # Build the system prompt
    sys_prompt = load_default_system_prompt()

    # Build user message using the existing template renderer
    cid_for_template = client_id or context.citations[0]["client_id"]
    first_cit = context.citations[0]

    messages = render_support_chat_messages(
        client_id=cid_for_template,
        clearance_level="Internal Support",
        document_id=first_cit["document_id"],
        section=first_cit["section"],
        page=first_cit["page"],
        context=context.text,
        question=query,
    )
    # Prepend system prompt — render_support_chat_messages returns [system, user]
    # but it loads from templates; we override with our system prompt
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": messages[-1]["content"]},
    ]

    response = send_chat_completion(
        messages=messages,
        config=config,
        client=client,
        temperature=0.0,
        max_tokens=500,
    )

    if response.get("success"):
        answer = response["content"]
        return answer, False
    else:
        logger.warning("LLM call failed: %s — using fallback", response.get("error"))
        return INSUFFICIENT_EVIDENCE_FALLBACK, False


# ---------------------------------------------------------------------------
# Stage 5: Answer Query (Orchestrator)
# ---------------------------------------------------------------------------

def answer_query(
    query: str,
    client_id: Optional[str] = None,
    k: int = 5,
    search_mode: str = "hybrid",
    score_threshold: Optional[float] = None,
    force_mock: bool = False,
) -> RAGResult:
    """
    End-to-end query-to-answer pipeline.
    
    Returns a RAGResult containing the answer, retrieved chunks,
    assembled context, and metadata.
    """
    t0 = time.perf_counter()

    # Build retriever
    retriever = FilteredRetriever(force_mock=force_mock)

    # Stage 1: Embed (implicit inside retrieve)
    # Stage 2: Retrieve
    chunks = retrieve_context(
        retriever=retriever,
        query=query,
        k=k,
        client_id=client_id,
        search_mode=search_mode,
        score_threshold=score_threshold,
    )

    # Stage 3: Assemble context
    context = assemble_context(chunks)

    # Stage 4: Generate answer
    answer, from_mock = generate_answer(
        query=query,
        client_id=client_id,
        context=context,
        force_mock=force_mock or not load_llm_config().get("is_configured"),
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return RAGResult(
        query=query,
        client_id=client_id,
        answer=answer,
        retrieved_chunks=chunks,
        context=context,
        latency_ms=elapsed_ms,
        insufficient_evidence=(context.chunk_count == 0),
        from_mock=from_mock,
    )


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------

def format_report(result: RAGResult) -> str:
    """Format a human-readable pipeline audit report."""
    lines = []
    lines.append("=" * 80)
    lines.append("  ClientVault — End-to-End RAG Pipeline Report")
    lines.append("=" * 80)
    lines.append(f"  Query:                     {result.query}")
    lines.append(f"  Client ID:                 {result.client_id or '(none)'}")
    lines.append(f"  Chunks retrieved:          {len(result.retrieved_chunks)}")
    lines.append(f"  Insufficient evidence:     {result.insufficient_evidence}")
    lines.append(f"  Answer source:             {'Mock Fallback' if result.from_mock else 'LLM'}")
    lines.append(f"  Total pipeline latency:    {result.latency_ms:.1f} ms")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  Retrieved Sources:")
    lines.append("-" * 80)
    for i, c in enumerate(result.retrieved_chunks, 1):
        snippet = c.content[:120].replace("\n", " ") + ("..." if len(c.content) > 120 else "")
        lines.append(f"  [{i}] {c.chunk_id}  (score: {c.hybrid_score:.4f})")
        lines.append(f"       Client: {c.client_id}  Doc: {c.document_id}  "
                      f"Section: {c.section}  Page: {c.page}")
        lines.append(f"       {snippet}")
        lines.append("")
    lines.append("-" * 80)
    lines.append("  Generated Answer:")
    lines.append("-" * 80)
    lines.append(f"  {result.answer}")
    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ClientVault RAG Pipeline")
    parser.add_argument("--query", type=str,
                        default="What is the initial response time for a Severity 1 critical outage?")
    parser.add_argument("--client-id", type=str, default=None,
                        help="Filter retrieval to a specific client (e.g., NEXUS-002)")
    parser.add_argument("--k", type=int, default=5, help="Number of chunks to retrieve")
    parser.add_argument("--search-mode", type=str, default="hybrid",
                        choices=["vector", "hybrid"])
    parser.add_argument("--score-threshold", type=float, default=None,
                        help="Minimum hybrid score threshold")
    parser.add_argument("--mock", action="store_true",
                        help="Use deterministic fallback instead of LLM")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_LOG),
                        help="Output log file path")
    args = parser.parse_args()

    result = answer_query(
        query=args.query,
        client_id=args.client_id,
        k=args.k,
        search_mode=args.search_mode,
        score_threshold=args.score_threshold,
        force_mock=args.mock,
    )

    report = format_report(result)
    print(report)

    # Save to file
    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")
    logger.info("Pipeline report saved to %s", output_path)

    # Also save structured JSON
    json_path = output_path.with_suffix(".json")
    json_data = {
        "query": result.query,
        "client_id": result.client_id,
        "answer": result.answer,
        "insufficient_evidence": result.insufficient_evidence,
        "from_mock": result.from_mock,
        "latency_ms": round(result.latency_ms, 2),
        "retrieved_chunks": [
            {
                "rank": i,
                "chunk_id": c.chunk_id,
                "client_id": c.client_id,
                "document_id": c.document_id,
                "section": c.section,
                "page": c.page,
                "hybrid_score": round(c.hybrid_score, 4),
                "content_snippet": c.content[:200].replace("\n", " ") + ("..." if len(c.content) > 200 else ""),
            }
            for i, c in enumerate(result.retrieved_chunks, 1)
        ],
        "citations": result.context.citations,
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    logger.info("Structured results saved to %s", json_path)


if __name__ == "__main__":
    main()
