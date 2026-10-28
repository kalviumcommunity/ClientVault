"""
ClientVault — Conversational RAG Engine

Supports multi-turn conversations by tracking chat history, rewriting
follow-up questions into standalone retrieval queries, retrieving context
using the rewritten query, and answering the original question with
grounded evidence. Reuses existing retrieval, citation, guardrail,
and history-management components.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.history_manager import ConversationHistoryManager as ConversationHistoryManager
from src.filtered_retriever import FilteredRetriever, MetadataFilter
from src.hallucination_guardrails import (
    assess_retrieval,
    REFUSAL_MESSAGE,
    DEFAULT_RELEVANCE_THRESHOLD,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.ConvRAG: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.ConvRAG")

DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "sample_conversational_rag_output.log"


@dataclass
class ConversationTurn:
    """A single turn in the conversation with rewrite and retrieval info."""
    turn_number: int
    original_question: str
    rewritten_query: str
    retrieved_chunks: List[Dict[str, Any]]
    answer: str
    sources_used: List[str]
    refusal: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationResult:
    """Complete multi-turn conversation."""
    turns: List[ConversationTurn]
    history_limit: int


@dataclass
class RewriteResult:
    """Result of query rewriting."""
    rewritten_query: str
    original_question: str
    used_history: bool
    fallback_used: bool


# ---------------------------------------------------------------------------
# Query rewriting
# ---------------------------------------------------------------------------

def rewrite_followup(
    latest_question: str,
    history: Optional[List[Dict[str, str]]] = None,
    force_mock: bool = True,
) -> RewriteResult:
    """Rewrite a follow-up question into a standalone retrieval query.

    Uses the conversation history to resolve pronouns and implicit references.
    Falls back to the original question on first turn, empty history, or
    any failure.
    """
    if not history or len(history) < 2:
        # First turn or only system message — no rewrite needed
        return RewriteResult(
            rewritten_query=latest_question,
            original_question=latest_question,
            used_history=False,
            fallback_used=False,
        )

    if force_mock:
        # Deterministic rewrite using simple context resolution
        last_user_q = ""
        for msg in reversed(history):
            if msg["role"] == "user":
                last_user_q = msg["content"]
                break

        # Simple heuristics for common referential patterns
        rewritten = resolve_references(latest_question, last_user_q)
        return RewriteResult(
            rewritten_query=rewritten,
            original_question=latest_question,
            used_history=True,
            fallback_used=(rewritten == latest_question),
        )

    # Live LLM path (not used in mock mode)
    return RewriteResult(
        rewritten_query=latest_question,
        original_question=latest_question,
        used_history=False,
        fallback_used=True,
    )


def resolve_references(latest_question: str, prev_question: str) -> str:
    """Resolve referential follow-up questions into standalone queries.

    Handles 'what about X' -> rewrites as 'what is the X related to <prev topic>'.
    Falls back to original question when no reference pattern matches.
    """
    lower_q = latest_question.lower().strip()

    # "What about escalation contacts?" -> "What are the escalation contacts?"
    if lower_q.startswith("what about"):
        topic = latest_question[len("what about"):].strip().strip("?").strip()
        # Build a keyword context from the previous question
        stop_words = {"the", "a", "an", "is", "are", "was", "were",
                      "what", "how", "why", "when", "where", "who",
                      "do", "does", "did", "can", "will", "would",
                      "for", "of", "in", "to", "by", "on", "with",
                      "this", "that", "these", "those", "it", "its"}
        context = " ".join(w for w in prev_question.split()
                          if w.lower() not in stop_words)
        return f"What are the {topic} for {context.lower()}?"

    return latest_question


# ---------------------------------------------------------------------------
# Conversational RAG
# ---------------------------------------------------------------------------

class ConversationalRAG:
    """Multi-turn conversational RAG engine.

    Maintains conversation history, rewrites follow-up questions,
    retrieves context, and generates grounded answers.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        k: int = 5,
        threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
        history_limit: int = 6,
        force_mock: bool = True,
    ):
        self.client_id = client_id
        self.k = k
        self.threshold = threshold
        self.force_mock = force_mock
        self.history = ConversationHistoryManager(system_prompt="You are a grounded answer generator.", max_token_budget=600)
        self.turns: List[ConversationTurn] = []

    def ask(self, question: str) -> ConversationTurn:
        """Process one turn: rewrite → retrieve → assess → answer."""
        turn_number = len(self.turns) + 1
        hist_msgs = self.history.get_messages()

        # 1. Rewrite follow-up
        rewrite = rewrite_followup(question, hist_msgs, force_mock=self.force_mock)
        rewritten = rewrite.rewritten_query

        # 2. Retrieve using rewritten query
        retriever = FilteredRetriever(force_mock=self.force_mock)
        mf = MetadataFilter(client_id=self.client_id) if self.client_id else None
        res = retriever.search(rewritten, k=self.k, metadata_filter=mf,
                               target_client_id=self.client_id)
        chunks = res.chunks

        # 3. Assess retrieval quality
        assessment = assess_retrieval(chunks, threshold=self.threshold)

        # 4. Generate or refuse
        sources_used = []
        if not assessment.passes_guard:
            answer = REFUSAL_MESSAGE
            refusal = True
        else:
            # Build grounded answer with citations
            answer_lines = [f"Grounded Answer (Turn {turn_number}):", ""]
            for i, c in enumerate(chunks[:3], 1):
                snippet = c.content[:120].replace("\n", " ") + ("..." if len(c.content) > 120 else "")
                answer_lines.append(
                    f"[{i}] {c.document_id}#{c.chunk_id.split('#')[-1]} — {snippet}"
                )
                sources_used.append(f"[{i}] {c.document_id}#{c.chunk_id.split('#')[-1]}")
            if len(chunks) > 3:
                answer_lines.append(f"")
                answer_lines.append(f"(+ {len(chunks)-3} additional sources)")
            answer_lines.append("")
            answer_lines.append("The above sources provide sufficient relevant context.")
            answer = "\n".join(answer_lines)
            refusal = False

        # 5. Update history
        self.history.add_turn("user", question)
        self.history.add_turn("assistant", answer)

        turn = ConversationTurn(
            turn_number=turn_number,
            original_question=question,
            rewritten_query=rewritten,
            retrieved_chunks=[
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "section": c.section,
                    "score": round(c.hybrid_score, 4),
                }
                for c in chunks
            ],
            answer=answer,
            sources_used=sources_used,
            refusal=refusal,
        )
        self.turns.append(turn)

        # Trim history
        self.history.enforce_budget()

        return turn

    def get_conversation(self) -> ConversationResult:
        return ConversationResult(turns=self.turns, history_limit=self.history.max_token_budget)


# ---------------------------------------------------------------------------
# CLI & Sample Dialogue
# ---------------------------------------------------------------------------

def run_sample_dialogue() -> ConversationResult:
    """Run a two-turn dialogue demonstrating conversational RAG."""
    crag = ConversationalRAG(client_id="NEXUS-002", force_mock=True)

    print("=" * 80)
    print("  ClientVault — Conversational RAG Sample Dialogue")
    print("=" * 80)
    print()

    dialogues = [
        "What is the initial response time for a Severity 1 critical outage?",
        "What about escalation contacts?",
    ]

    for q in dialogues:
        print(f">> User: {q}")
        turn = crag.ask(q)
        print(f"[Rewritten query: {turn.rewritten_query}]")
        print()
        print(turn.answer)
        print()
        if turn.retrieved_chunks:
            print(f"  Retrieved {len(turn.retrieved_chunks)} chunk(s)")
            for c in turn.retrieved_chunks[:3]:
                print(f"    - {c['chunk_id']} (score: {c['score']:.4f})")
        print()
        print("-" * 60)
        print()

    return crag.get_conversation()


def main() -> None:
    parser = argparse.ArgumentParser(description="ClientVault Conversational RAG")
    parser.add_argument("--mock", action="store_true", default=True)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_LOG))
    args = parser.parse_args()

    conv = run_sample_dialogue()

    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("  ClientVault — Conversational RAG Demo")
    report_lines.append("=" * 80)
    report_lines.append(f"  History limit: {conv.history_limit} turns")
    report_lines.append("")

    for turn in conv.turns:
        report_lines.append(f"  Turn {turn.turn_number}:")
        report_lines.append(f"    Original:     {turn.original_question}")
        report_lines.append(f"    Rewritten:    {turn.rewritten_query}")
        report_lines.append(f"    Refusal:      {turn.refusal}")
        report_lines.append(f"    Sources:      {', '.join(turn.sources_used) if turn.sources_used else '(none)'}")
        report_lines.append("    --- Answer ---")
        report_lines.append(f"    {turn.answer}")
        report_lines.append("    ---")
        report_lines.append("")

    report = "\n".join(report_lines)
    print(report)

    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")

    json_path = output_path.with_suffix(".json")
    json_data = {
        "history_limit": conv.history_limit,
        "turns": [t.to_dict() for t in conv.turns],
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    logger.info("Report saved to %s", args.output)


if __name__ == "__main__":
    main()
