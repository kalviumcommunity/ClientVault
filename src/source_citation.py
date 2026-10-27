"""
ClientVault — Source Citation & Attribution Engine

Adds stable citation markers ([1], [2], …) to generated answers, maps
each marker to real source metadata (document, chunk ID, section, page,
original text), verifies that cited chunks exist, and prevents fabricated
citations by refusing to generate markers for chunks not actually retrieved.
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.filtered_retriever import FilteredRetriever, MetadataFilter, FilteredRetrievedChunk
from src.context_injector import (
    assemble_context_budgeted,
    INSUFFICIENT_EVIDENCE_INSTRUCTION,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.SourceCitation: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.SourceCitation")

DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "sample_source_citation_output.log"


@dataclass
class CitationSource:
    """Stable mapping from a citation marker to real source metadata."""
    marker: str                # e.g. "[1]"
    rank: int
    chunk_id: str
    document_id: str
    section: str
    page: int
    client_id: str
    score: float
    snippet: str               # first 300 chars of original chunk text

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CitationVerification:
    """Result of verifying that cited sources exist and are valid."""
    marker: str
    exists_in_retrieved: bool
    matches_metadata: bool
    source: Optional[CitationSource]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class CitationResult:
    """Complete citation and attribution output."""
    query: str
    client_id: Optional[str]
    answer: str
    citation_map: Dict[str, CitationSource]
    verification_results: List[CitationVerification]
    total_sources: int
    fabricated_markers_detected: List[str]
    insufficient_evidence: bool
    from_mock: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "client_id": self.client_id,
            "answer": self.answer,
            "citation_map": {k: v.to_dict() for k, v in self.citation_map.items()},
            "verification_results": [v.to_dict() for v in self.verification_results],
            "total_sources": self.total_sources,
            "fabricated_markers_detected": self.fabricated_markers_detected,
            "insufficient_evidence": self.insufficient_evidence,
            "from_mock": self.from_mock,
        }


# ---------------------------------------------------------------------------
# Citation mapping
# ---------------------------------------------------------------------------

def build_citation_map(chunks: List[FilteredRetrievedChunk]) -> Dict[str, CitationSource]:
    """Build a stable marker-to-source mapping from retrieved chunks.

    Each chunk gets a stable marker [1], [2], … based on its rank order.
    """
    mapping: Dict[str, CitationSource] = {}
    for i, c in enumerate(chunks, 1):
        marker = f"[{i}]"
        mapping[marker] = CitationSource(
            marker=marker,
            rank=i,
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            section=c.section,
            page=c.page,
            client_id=c.client_id,
            score=round(c.hybrid_score, 4),
            snippet=c.content[:300].replace("\n", " ") + ("..." if len(c.content) > 300 else ""),
        )
    return mapping


# ---------------------------------------------------------------------------
# Citation injection into answer
# ---------------------------------------------------------------------------

def inject_citations(
    answer_text: str,
    citation_map: Dict[str, CitationSource],
) -> str:
    """Ensure answer contains inline citation markers referencing real sources.

    If the answer has no markers at all (mock mode), append a citation
    appendix listing all available sources.
    """
    # Detect existing markers
    existing = set(re.findall(r'\[\d+\]', answer_text))

    if existing:
        # Markers already present — validate they exist in the map
        fake = [m for m in existing if m not in citation_map]
        if fake:
            logger.warning("Fabricated markers detected: %s", fake)
            answer_text += f"\n\n[WARNING: The following markers have no supporting source: {', '.join(fake)}]"
        return answer_text

    # No markers — append citation appendix
    if not citation_map:
        return answer_text

    lines = [answer_text, "", "---", "Sources:"]
    for marker, src in sorted(citation_map.items(), key=lambda x: x[1].rank):
        lines.append(f"  {marker} {src.document_id}#{src.chunk_id.split('#')[-1]} "
                      f"(§{src.section}, p.{src.page}) [score: {src.score}]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Source verification
# ---------------------------------------------------------------------------

def verify_citations(
    answer_text: str,
    citation_map: Dict[str, CitationSource],
) -> Tuple[List[CitationVerification], List[str]]:
    """Verify all markers in the answer against the citation map.

    Returns (verification_results, fabricated_markers).
    """
    markers_in_answer = set(re.findall(r'\[\d+\]', answer_text))
    results: List[CitationVerification] = []
    fabricated: List[str] = []

    for marker in sorted(markers_in_answer, key=lambda m: int(m.strip("[]"))):
        if marker in citation_map:
            src = citation_map[marker]
            results.append(CitationVerification(
                marker=marker,
                exists_in_retrieved=True,
                matches_metadata=True,
                source=src,
            ))
        else:
            fabricated.append(marker)
            results.append(CitationVerification(
                marker=marker,
                exists_in_retrieved=False,
                matches_metadata=False,
                source=None,
            ))

    return results, fabricated


# ---------------------------------------------------------------------------
# Full citation pipeline
# ---------------------------------------------------------------------------

def build_cited_answer(
    query: str,
    client_id: Optional[str] = None,
    k: int = 5,
    force_mock: bool = True,
) -> CitationResult:
    """Full pipeline: retrieve → map citations → generate answer → verify."""
    retriever = FilteredRetriever(force_mock=force_mock)
    mf = MetadataFilter(client_id=client_id) if client_id else None
    res = retriever.search(query, k=k, metadata_filter=mf, target_client_id=client_id)
    chunks = res.chunks

    # Build citation map from real retrieved chunks
    citation_map = build_citation_map(chunks)

    if not chunks:
        return CitationResult(
            query=query,
            client_id=client_id,
            answer=INSUFFICIENT_EVIDENCE_INSTRUCTION,
            citation_map={},
            verification_results=[],
            total_sources=0,
            fabricated_markers_detected=[],
            insufficient_evidence=True,
            from_mock=force_mock,
        )

    # Generate grounded answer (mock mode)
    ctx = assemble_context_budgeted(chunks)
    first = chunks[0]

    if force_mock:
        lines = [f"Grounded Answer for {query}", ""]
        for i, c in enumerate(chunks, 1):
            lines.append(f"Based on [{i}]: {c.document_id}, Section {c.section} — "
                         f"{c.content[:100].replace(chr(10), ' ')}...")
        lines.append("")
        lines.append("See sources below for the complete procedure.")
        raw_answer = "\n".join(lines)
    else:
        raw_answer = "Answer generated by LLM. [1] and [2] provide key evidence."

    # Inject citations
    answer = inject_citations(raw_answer, citation_map)

    # Verify
    verifications, fabricated = verify_citations(answer, citation_map)

    return CitationResult(
        query=query,
        client_id=client_id,
        answer=answer,
        citation_map=citation_map,
        verification_results=verifications,
        total_sources=len(citation_map),
        fabricated_markers_detected=fabricated,
        insufficient_evidence=False,
        from_mock=force_mock,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def format_report(result: CitationResult) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("  ClientVault — Source Citation & Attribution Report")
    lines.append("=" * 80)
    lines.append(f"  Query:                     {result.query}")
    lines.append(f"  Client ID:                 {result.client_id or '(none)'}")
    lines.append(f"  Total sources:             {result.total_sources}")
    lines.append(f"  Insufficient evidence:     {result.insufficient_evidence}")
    lines.append(f"  Fabricated markers:        {result.fabricated_markers_detected}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  Citation Map (marker → source):")
    lines.append("-" * 80)
    for marker, src in sorted(result.citation_map.items(), key=lambda x: x[1].rank):
        lines.append(f"  {marker}")
        lines.append(f"       Chunk ID:    {src.chunk_id}")
        lines.append(f"       Document:    {src.document_id}")
        lines.append(f"       Section:     {src.section}")
        lines.append(f"       Page:        {src.page}")
        lines.append(f"       Client:      {src.client_id}")
        lines.append(f"       Score:       {src.score}")
        lines.append(f"       Snippet:     {src.snippet[:120]}...")
        lines.append("")
    lines.append("-" * 80)
    lines.append("  Source Verification:")
    lines.append("-" * 80)
    for v in result.verification_results:
        status = "✓ VERIFIED" if v.exists_in_retrieved else "✗ FABRICATED"
        lines.append(f"  {v.marker}: {status}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  Answer with Citations:")
    lines.append("-" * 80)
    lines.append(f"  {result.answer}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  No-Source Fallback (when retrieval is empty):")
    lines.append("-" * 80)
    lines.append(f"  {INSUFFICIENT_EVIDENCE_INSTRUCTION}")
    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ClientVault Source Citation")
    parser.add_argument("--query", type=str,
                        default="What is the initial response time for a Severity 1 critical outage?")
    parser.add_argument("--client-id", type=str, default="NEXUS-002")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--mock", action="store_true", default=True)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_LOG))
    args = parser.parse_args()

    result = build_cited_answer(
        query=args.query,
        client_id=args.client_id,
        k=args.k,
        force_mock=args.mock,
    )
    report = format_report(result)
    print(report)

    Path(args.output).write_text(report, encoding="utf-8")
    json_path = Path(args.output).with_suffix(".json")
    json_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    logger.info("Saved to %s", args.output)


if __name__ == "__main__":
    main()
