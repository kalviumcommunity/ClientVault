"""
ClientVault — Context Injection & Prompt Augmentation Engine

Formats retrieved chunks with compact source markers ([1] doc#chunk),
assembles context within a configurable token budget (reserving space for
instructions, question and answer), and builds an augmented prompt that
strictly separates context from the question.

Integrates with existing count_tokens() from token_cost_estimator and
the PromptTemplate / user_retrieval.template from prompt_template.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.token_cost_estimator import count_tokens
from src.filtered_retriever import FilteredRetrievedChunk
from src.prompt_template import PromptTemplate, TemplateRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.CtxInjector: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.CtxInjector")

DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "sample_augmented_prompt_output.log"

# Default budget: gpt-4o-mini 128k total, reserve 4k for sys+user framing+answer
DEFAULT_MAX_CONTEXT_TOKENS = 4096
DEFAULT_RESERVE_TOKENS = 2048  # system prompt + user template framing + question + answer
INSUFFICIENT_EVIDENCE_INSTRUCTION = (
    "INSUFFICIENT EVIDENCE: No approved source in this client's knowledge base "
    "supports this procedure. Please escalate to the Account Lead or consult "
    "the designated runbook."
)


@dataclass
class SourceMarker:
    """Compact source marker referencing a single chunk."""
    idx: int
    display: str  # e.g. "[1] acme_onboarding#tok_000"
    chunk_id: str
    document_id: str
    token_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BudgetedContextResult:
    """Result of token-budgeted context assembly."""
    context_text: str
    total_tokens: int
    max_tokens: int
    budget_remaining: int
    sources_included: List[SourceMarker]
    sources_excluded: List[SourceMarker]
    truncated: bool
    fully_empty: bool
    insufficient_evidence: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_text": self.context_text,
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "budget_remaining": self.budget_remaining,
            "sources_included": [s.to_dict() for s in self.sources_included],
            "sources_excluded": [s.to_dict() for s in self.sources_excluded],
            "truncated": self.truncated,
            "fully_empty": self.fully_empty,
            "insufficient_evidence": self.insufficient_evidence,
        }


@dataclass
class AugmentedPrompt:
    """Complete augmented prompt ready for LLM submission."""
    full_prompt: str
    context_token_count: int
    sources_included: List[SourceMarker]
    truncated: bool
    insufficient_evidence: bool
    budget_config: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "full_prompt": self.full_prompt,
            "context_token_count": self.context_token_count,
            "sources_included": [s.to_dict() for s in self.sources_included],
            "truncated": self.truncated,
            "insufficient_evidence": self.insufficient_evidence,
            "budget_config": self.budget_config,
        }


# ---------------------------------------------------------------------------
# Source marker formatting
# ---------------------------------------------------------------------------

def format_source_marker(idx: int, chunk: FilteredRetrievedChunk) -> str:
    """Compact source marker: [1] acme_onboarding#tok_000"""
    chunk_id = chunk.chunk_id
    # chunk_id already has the full form like acme_onboarding#tok_000
    return f"[{idx}] {chunk_id}"


def _build_source_marker_text(idx: int, chunk: FilteredRetrievedChunk) -> str:
    """Build the full formatted text for one chunk including its source marker."""
    marker = format_source_marker(idx, chunk)
    return f"\n{marker}\n{chunk.content.strip()}"


def _estimate_chunk_token_cost(chunk: FilteredRetrievedChunk) -> int:
    """Estimate tokens for a formatted chunk (marker + content)."""
    marker_text = _build_source_marker_text(1, chunk)  # idx placeholder, fine for estim
    return count_tokens(marker_text)


# ---------------------------------------------------------------------------
# Token-budgeted context assembly
# ---------------------------------------------------------------------------

def assemble_context_budgeted(
    chunks: List[FilteredRetrievedChunk],
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS,
) -> BudgetedContextResult:
    """
    Assemble context from retrieved chunks respecting a token budget.
    
    Chunks are included in rank order (highest score first) until the budget
    is exhausted. Each chunk is prefixed with a compact source marker.
    If no chunks fit at all, or chunks is empty, returns empty context with
    insufficient_evidence=True.
    
    Args:
        chunks: Retrieved chunks (pre-sorted by relevance).
        max_context_tokens: Maximum tokens for the entire prompt.
        reserve_tokens: Tokens reserved for system prompt, user template framing,
                       question, and answer output.
    
    Returns:
        BudgetedContextResult with assembled text, token counts, and source lists.
    """
    if not chunks:
        return BudgetedContextResult(
            context_text="",
            total_tokens=0,
            max_tokens=max_context_tokens,
            budget_remaining=max_context_tokens - reserve_tokens,
            sources_included=[],
            sources_excluded=[],
            truncated=False,
            fully_empty=True,
            insufficient_evidence=True,
        )

    available = max_context_tokens - reserve_tokens
    if available <= 0:
        # No room for any context
        return BudgetedContextResult(
            context_text="",
            total_tokens=0,
            max_tokens=max_context_tokens,
            budget_remaining=available,
            sources_included=[],
            sources_excluded=[SourceMarker(
                idx=i + 1,
                display=format_source_marker(i + 1, c),
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                token_count=count_tokens(c.content),
            ) for i, c in enumerate(chunks)],
            truncated=True,
            fully_empty=True,
            insufficient_evidence=True,
        )

    parts: List[str] = []
    included: List[SourceMarker] = []
    excluded: List[SourceMarker] = []
    running_tokens = 0

    for i, chunk in enumerate(chunks):
        marker_display = format_source_marker(i + 1, chunk)
        chunk_text = _build_source_marker_text(i + 1, chunk)
        chunk_tokens = count_tokens(chunk_text)

        if running_tokens + chunk_tokens <= available:
            parts.append(chunk_text)
            included.append(SourceMarker(
                idx=i + 1,
                display=marker_display,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                token_count=count_tokens(chunk.content),
            ))
            running_tokens += chunk_tokens
        else:
            # Check if this is the first chunk (nothing fits)
            if not parts:
                # Try to fit at least the highest-scoring chunk
                parts.append(chunk_text)
                included.append(SourceMarker(
                    idx=i + 1,
                    display=marker_display,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    token_count=count_tokens(chunk.content),
                ))
                running_tokens += chunk_tokens
            else:
                excluded.append(SourceMarker(
                    idx=i + 1,
                    display=marker_display,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    token_count=count_tokens(chunk.content),
                ))

    context_text = "\n\n".join(p for p in parts) if parts else ""
    truncated = bool(excluded)
    insufficient = len(included) == 0

    return BudgetedContextResult(
        context_text=context_text,
        total_tokens=running_tokens,
        max_tokens=max_context_tokens,
        budget_remaining=available - running_tokens,
        sources_included=included,
        sources_excluded=excluded,
        truncated=truncated,
        fully_empty=(len(included) == 0),
        insufficient_evidence=insufficient,
    )


# ---------------------------------------------------------------------------
# Augmented prompt builder
# ---------------------------------------------------------------------------

def build_augmented_prompt(
    query: str,
    context_result: BudgetedContextResult,
    client_id: str = "UNKNOWN",
    document_id: str = "unknown",
    section: str = "General",
    page: int = 1,
    override_instructions: Optional[str] = None,
) -> AugmentedPrompt:
    """
    Build the full augmented prompt using the user_retrieval template.
    
    If context is empty/insufficient, injects the INSUFFICIENT EVIDENCE
    instruction instead of context passages.
    """
    sys_template = TemplateRegistry.get("system_prompt")
    user_template = TemplateRegistry.get("user_retrieval")

    system_content = sys_template.render(
        client_id=client_id,
        clearance_level="Internal Support",
    )

    if context_result.insufficient_evidence or not context_result.context_text:
        # Augmented prompt with explicit insufficient-evidence instruction
        context_block = (
            "NO RELEVANT EVIDENCE FOUND.\n\n"
            f"{INSUFFICIENT_EVIDENCE_INSTRUCTION}"
        )
    else:
        context_block = context_result.context_text

    user_content = user_template.render(
        client_id=client_id,
        document_id=document_id,
        section=section,
        page=str(page),
        context=context_block,
        question=query,
    )

    full_prompt = f"{system_content}\n\n{user_content}"
    context_token_count = context_result.total_tokens

    return AugmentedPrompt(
        full_prompt=full_prompt,
        context_token_count=context_token_count,
        sources_included=context_result.sources_included,
        truncated=context_result.truncated,
        insufficient_evidence=context_result.insufficient_evidence,
        budget_config={
            "max_context_tokens": context_result.max_tokens,
            "reserve_tokens": DEFAULT_RESERVE_TOKENS,
        },
    )


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------

def format_report(augmented: AugmentedPrompt, query: str, client_id: Optional[str]) -> str:
    """Format a human-readable audit report."""
    lines = []
    lines.append("=" * 80)
    lines.append("  ClientVault — Context Injection & Augmented Prompt Report")
    lines.append("=" * 80)
    lines.append(f"  Query:                     {query}")
    lines.append(f"  Client ID:                 {client_id or '(none)'}")
    lines.append(f"  Context token count:       {augmented.context_token_count}")
    lines.append(f"  Sources included:          {len(augmented.sources_included)}")
    lines.append(f"  Sources excluded:          {sum(1 for s in augmented.sources_included if False)}")
    lines.append(f"  Truncated by budget:       {augmented.truncated}")
    lines.append(f"  Insufficient evidence:     {augmented.insufficient_evidence}")
    lines.append(f"  Budget (context):          {augmented.budget_config['max_context_tokens']}")
    lines.append(f"  Reserve (framing):         {augmented.budget_config['reserve_tokens']}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  Sources included:")
    lines.append("-" * 80)
    for s in augmented.sources_included:
        lines.append(f"  {s.display}  ({s.token_count} tokens)")
    lines.append("")
    lines.append("-" * 80)
    lines.append("  Augmented Prompt (first 1500 chars):")
    lines.append("-" * 80)
    lines.append(augmented.full_prompt[:1500])
    if len(augmented.full_prompt) > 1500:
        lines.append("  ... [truncated for display]")
    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ClientVault Context Injection")
    parser.add_argument("--query", type=str,
                        default="What is the initial response time for a Severity 1 critical outage?")
    parser.add_argument("--client-id", type=str, default=None)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--max-context-tokens", type=int, default=DEFAULT_MAX_CONTEXT_TOKENS)
    parser.add_argument("--reserve-tokens", type=int, default=DEFAULT_RESERVE_TOKENS)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_LOG))
    parser.add_argument("--mock", action="store_true", help="Force deterministic retriever")
    args = parser.parse_args()

    from src.filtered_retriever import FilteredRetriever, MetadataFilter

    retriever = FilteredRetriever(force_mock=args.mock)
    mf = MetadataFilter(client_id=args.client_id) if args.client_id else None
    res = retriever.search(args.query, k=args.k, metadata_filter=mf,
                           target_client_id=args.client_id)

    ctx = assemble_context_budgeted(
        res.chunks,
        max_context_tokens=args.max_context_tokens,
        reserve_tokens=args.reserve_tokens,
    )

    first = res.chunks[0] if res.chunks else None
    augmented = build_augmented_prompt(
        query=args.query,
        context_result=ctx,
        client_id=args.client_id or (first.client_id if first else "UNKNOWN"),
        document_id=first.document_id if first else "unknown",
        section=first.section if first else "General",
        page=first.page if first else 1,
    )

    report = format_report(augmented, args.query, args.client_id)
    print(report)

    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")

    json_path = output_path.with_suffix(".json")
    json_data = {
        "query": args.query,
        "client_id": args.client_id,
        "context_token_count": augmented.context_token_count,
        "sources_included": [s.to_dict() for s in augmented.sources_included],
        "truncated": augmented.truncated,
        "insufficient_evidence": augmented.insufficient_evidence,
        "budget_config": augmented.budget_config,
        "full_prompt": augmented.full_prompt,
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    logger.info("Report saved to %s", output_path)
    logger.info("JSON saved to %s", json_path)


if __name__ == "__main__":
    main()
