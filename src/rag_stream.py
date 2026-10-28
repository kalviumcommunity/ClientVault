"""
ClientVault — Streaming RAG events for POST /query/stream

Produces the event sequence the chat UI renders progressively:

    citations  -> retrieval passed the relevance guardrail; sources incl. chunk text
    token*     -> answer text, in order
    done       -> {"status": "answered", "mode": "live" | "offline"}

or, when the guardrail rejects the evidence:

    refusal    -> refusal message, reason, below-threshold candidates
    done       -> {"status": "refused"}

Generation modes:
- live:    an LLM is configured (OPENAI_API_KEY) and RAG_API_FORCE_MOCK=false;
           tokens are forwarded from the model's stream as they arrive.
- offline: no LLM; the guardrail's grounded summary (the same text POST /query
           returns) is emitted word by word, paced by token_delay_s.

Exceptions propagate to the caller, which turns them into an `error` event.
"""

import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.chat_completion import create_client, load_default_system_prompt, load_llm_config
from src.hallucination_guardrails import guarded_generate
from src.prompt_template import render_support_chat_messages

logger = logging.getLogger("ClientVault.RAGStream")

# A word plus its trailing whitespace, so joined tokens reproduce the text exactly.
_TOKEN_RE = re.compile(r"\S+\s*|\s+")


def live_llm_available(config: Dict[str, Any]) -> bool:
    """Same rule as rag_pipeline.generate_answer: a real, non-placeholder key."""
    api_key = config.get("api_key", "")
    return bool(api_key) and api_key != "your_openai_api_key_here" and not api_key.startswith("local-")


def build_context_text(sources: List[Dict[str, Any]]) -> str:
    """Format sources like rag_pipeline.assemble_context."""
    return "\n\n---\n\n".join(
        f"[Source: {s['document_id']}, Section: {s['section']}, Page: {s['page']}]\n{s['text'].strip()}"
        for s in sources
    )


def stream_llm_tokens(
    question: str,
    client_id: Optional[str],
    sources: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Iterator[str]:
    """Forward content deltas from a streaming chat completion."""
    client = create_client(base_url=config["base_url"], api_key=config["api_key"])
    first = sources[0]
    user_message = render_support_chat_messages(
        client_id=client_id or "ALL",
        clearance_level="Internal Support",
        document_id=first["document_id"],
        section=first["section"],
        page=first["page"],
        context=build_context_text(sources),
        question=question,
    )[-1]["content"]
    messages = [
        {"role": "system", "content": load_default_system_prompt()},
        {"role": "user", "content": user_message},
    ]
    stream = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=0.0,
        max_tokens=500,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def paced_tokens(text: str, token_delay_s: float) -> Iterator[str]:
    """Emit already-generated text word by word (offline mode)."""
    for token in _TOKEN_RE.findall(text):
        if token_delay_s > 0:
            time.sleep(token_delay_s)
        yield token


def stream_rag_events(
    question: str,
    client_id: Optional[str] = None,
    k: int = 5,
    threshold: float = 0.6,
    force_mock: bool = True,
    token_delay_s: float = 0.0,
) -> Iterator[Dict[str, Any]]:
    """Yield the streaming event sequence for one question."""
    result = guarded_generate(
        query=question,
        client_id=client_id,
        k=k,
        threshold=threshold,
        force_mock=force_mock,
    )

    if not result.passed_guard:
        yield {
            "type": "refusal",
            "message": result.answer,
            "reason": result.refusal_reason,
            "threshold": result.threshold_used,
            "candidates": result.sources,
        }
        yield {"type": "done", "status": "refused"}
        return

    yield {"type": "citations", "sources": result.sources, "threshold": result.threshold_used}

    config = load_llm_config()
    if not force_mock and live_llm_available(config):
        mode = "live"
        tokens = stream_llm_tokens(question, client_id, result.sources, config)
    else:
        mode = "offline"
        tokens = paced_tokens(result.answer, token_delay_s)

    logger.info("Streaming answer (mode=%s, sources=%d)", mode, len(result.sources))
    for token in tokens:
        yield {"type": "token", "text": token}

    yield {"type": "done", "status": "answered", "mode": mode}
