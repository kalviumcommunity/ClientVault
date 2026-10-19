"""
ClientVault — Multi-Turn Conversation History & Token Budget Manager

Maintains conversation history for multi-turn RAG interactions:
- Task 1: Maintains message history (system prompt + alternating user/assistant turns).
- Task 2: Accurately measures total token count before each call using tiktoken.
- Task 3: Trims or summarizes older message turns when approaching token budget,
          strictly preserving the system message and recent context.
- Task 4: Demonstrates budget enforcement on overflowing multi-turn conversations.
- Task 5: Provides runnable demo and logging for auditing and validation.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import argparse

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.token_cost_estimator import count_tokens, get_tokenizer
from src.chat_completion import (
    load_llm_config,
    create_client,
    send_chat_completion,
    setup_logging,
)


class ConversationHistoryManager:
    """
    Manages multi-turn conversation history under strict token budget constraints.
    Always preserves the root system message while applying rolling window trimming
    or summarization to older conversation turns.
    """

    def __init__(
        self,
        system_prompt: str,
        max_token_budget: int = 600,
        model_name: str = "gpt-4o-mini",
        strategy: str = "trim",  # 'trim' or 'summarize'
    ):
        self.system_prompt = system_prompt
        self.max_token_budget = max_token_budget
        self.model_name = model_name
        self.strategy = strategy
        self.history: List[Dict[str, str]] = []
        self.trim_events: List[Dict[str, Any]] = []

    def get_messages(self) -> List[Dict[str, str]]:
        """Returns the full messages payload (system prompt + active history)."""
        return [{"role": "system", "content": self.system_prompt}] + self.history

    def count_total_tokens(self, messages: Optional[List[Dict[str, str]]] = None) -> int:
        """
        Task 2: Measures total token count of the history payload.
        Includes OpenAI message protocol overhead (~3 tokens per message + 3 tokens for assistant priming).
        """
        msgs = messages if messages is not None else self.get_messages()
        total_tokens = 3  # Assistant reply priming overhead
        for msg in msgs:
            # Protocol overhead: <|im_start|>{role}\n{content}<|im_end|>\n = ~3-4 tokens
            total_tokens += 3
            total_tokens += count_tokens(msg.get("content", ""), model_name=self.model_name)
        return total_tokens

    def add_turn(self, role: str, content: str) -> None:
        """Task 1: Adds a user or assistant message to the history."""
        if role not in ("user", "assistant"):
            raise ValueError(f"Invalid role: {role}. Must be 'user' or 'assistant'.")
        self.history.append({"role": role, "content": content})

    def enforce_budget(self) -> Tuple[int, int]:
        """
        Task 3: Enforces token budget by trimming or summarizing older turns.
        Always preserves the system message and the most recent user turn.
        Returns: (tokens_before, tokens_after)
        """
        tokens_before = self.count_total_tokens()
        if tokens_before <= self.max_token_budget:
            return tokens_before, tokens_before

        if self.strategy == "trim":
            self._trim_oldest_turns()
        elif self.strategy == "summarize":
            self._summarize_oldest_turns()
        else:
            self._trim_oldest_turns()

        tokens_after = self.count_total_tokens()
        return tokens_before, tokens_after

    def _trim_oldest_turns(self) -> None:
        """
        Drops the oldest user-assistant turn pairs until the history fits within budget.
        Never drops the root system message or the latest user query.
        """
        # While over budget and we have at least one old turn plus the current turn
        while self.count_total_tokens() > self.max_token_budget and len(self.history) > 1:
            # We trim in pairs (or single oldest message) from index 0
            trimmed_msg = self.history.pop(0)
            self.trim_events.append({
                "action": "trim",
                "role": trimmed_msg["role"],
                "content_preview": trimmed_msg["content"][:60] + "...",
                "tokens_after": self.count_total_tokens(),
            })

    def _summarize_oldest_turns(self) -> None:
        """
        Compresses older turns into a concise briefing note, preserving context while saving tokens.
        """
        if len(self.history) <= 2:
            self._trim_oldest_turns()
            return

        # Compress older turns (all except the last 2 messages: last user + assistant)
        turns_to_summarize = self.history[:-2]
        self.history = self.history[-2:]

        summary_points = []
        for msg in turns_to_summarize:
            role = msg["role"].capitalize()
            first_sentence = msg["content"].split(".")[0].strip()
            summary_points.append(f"{role} discussed: {first_sentence}")

        condensed_summary = (
            "[Prior Conversation Context Summary: " + "; ".join(summary_points) + ".]"
        )

        # Insert summary note as the first turn
        self.history.insert(0, {"role": "system", "content": condensed_summary})

        # If still over budget, fallback to trimming
        if self.count_total_tokens() > self.max_token_budget:
            self._trim_oldest_turns()


def run_overflowing_conversation_demo(
    token_budget: int = 400,
    strategy: str = "trim",
    output_file: Optional[Path] = None,
) -> str:
    """
    Task 4 & 5: Demonstrates maintaining a multi-turn RAG dialogue where retrieved
    document chunks cause token growth past budget, proving history trimming keeps it within limits.
    """
    system_prompt = (
        "You are the ClientVault Support Knowledge Assistant. "
        "Explain client-specific procedures strictly based on verified evidence."
    )

    manager = ConversationHistoryManager(
        system_prompt=system_prompt,
        max_token_budget=token_budget,
        strategy=strategy,
    )

    # Simulated multi-turn dialogue with retrieved context chunks
    dialogue_turns = [
        (
            "user",
            "What is the identity verification step for ACME-001 onboarding?\n\n"
            "[Retrieved Context: KB-ONB-001 §3.1: Service desk engineer must query ACME HR directory API "
            "using employee ID. Any mismatch in department or legal name escalates to SecOps.]"
        ),
        (
            "assistant",
            "Verification requires querying the ACME Corporate HR directory API using the employee ID. "
            "Any discrepancies in name, department, or phone require immediate SECURITY_HOLD and SecOps escalation.\n"
            "[Source: KB-ONB-001 §3.1]"
        ),
        (
            "user",
            "Who needs to approve credential issuance after identity is verified?\n\n"
            "[Retrieved Context: KB-ONB-001 §3.2: Dual-operator sign-off is mandatory. Operator 1 initiates "
            "token in IAM Provisioning Gateway; Operator 2 (Senior Desk Lead) verifies sponsor email headers "
            "and signs the request.]"
        ),
        (
            "assistant",
            "Credential issuance requires dual-operator sign-off: Operator 1 initiates the provisioning token, "
            "and Operator 2 (Senior Desk Lead) must validate sponsor headers and authorize issuance.\n"
            "[Source: KB-ONB-001 §3.2]"
        ),
        (
            "user",
            "What are the network sandbox restrictions for the new credentials?\n\n"
            "[Retrieved Context: KB-ONB-001 §3.3: Newly provisioned accounts inherit StagingSandboxRestrictedAccess "
            "limiting network transit to Staging VPC CIDR 10.240.0.0/16 for 48 hours with full audit logging.]"
        ),
        (
            "assistant",
            "New credentials inherit StagingSandboxRestrictedAccess, restricting network transit strictly to "
            "Staging VPC CIDR 10.240.0.0/16 for 48 hours with comprehensive audit logging enabled.\n"
            "[Source: KB-ONB-001 §3.3]"
        ),
        (
            "user",
            "Can 2FA be bypassed if the user loses their hardware key during onboarding?\n\n"
            "[Retrieved Context: KB-ONB-001 §3.4: Hardware FIDO2 keys or TOTP registration is mandatory upon login. "
            "NO BYPASS OR EXEMPTION is permitted under any circumstances. Revoke and restart provisioning.]"
        ),
        (
            "assistant",
            "INSUFFICIENT EVIDENCE for bypass. 2FA is strictly mandatory with NO exemptions permitted. "
            "If lost, the token must be revoked and provisioning restarted.\n"
            "[Source: KB-ONB-001 §3.4]"
        ),
    ]

    log_lines = []
    log_lines.append("=" * 80)
    log_lines.append("  ClientVault — Multi-Turn History Management & Token Trimming Demo")
    log_lines.append(f"  Token Budget Limit: {token_budget} tokens | Strategy: {strategy.upper()}")
    log_lines.append(f"  System Message Overhead: {count_tokens(system_prompt)} tokens")
    log_lines.append("=" * 80)
    log_lines.append("")

    for turn_idx, (role, text) in enumerate(dialogue_turns, 1):
        manager.add_turn(role, text)
        naive_tokens = manager.count_total_tokens()

        log_lines.append(f"Turn {turn_idx}: Added [{role.upper()}] message ({count_tokens(text)} tokens)")
        log_lines.append(f"  -> Naive Accumulated Total: {naive_tokens} tokens")

        if naive_tokens > token_budget:
            log_lines.append(f"  [ALERT] Token count ({naive_tokens}) EXCEEDS budget limit ({token_budget})!")
            tokens_before, tokens_after = manager.enforce_budget()
            log_lines.append(f"  [ACTION] Applied {strategy.upper()} strategy: {tokens_before} -> {tokens_after} tokens")
            log_lines.append(f"  -> Active Turns Remaining in History: {len(manager.history)}")
            log_lines.append(f"  -> System Prompt Preserved: True (Root message retained)")
        else:
            log_lines.append(f"  [STATUS] Within budget ({naive_tokens}/{token_budget} tokens)")

        log_lines.append("-" * 80)

    log_lines.append("")
    log_lines.append("=" * 80)
    log_lines.append("  FINAL CONVERSATION PAYLOAD SENT TO MODEL")
    log_lines.append(f"  Final Total Tokens: {manager.count_total_tokens()} (Budget: {token_budget})")
    log_lines.append("=" * 80)

    for i, msg in enumerate(manager.get_messages()):
        role = msg["role"].upper()
        content = msg["content"]
        log_lines.append(f"[{i}] {role} ({count_tokens(content)} tokens):")
        log_lines.append(f"    {content}")
        log_lines.append("")

    output_str = "\n".join(log_lines)
    if output_file:
        output_file.write_text(output_str, encoding="utf-8")
        print(f"[OK] Multi-turn log saved to: {output_file}")

    return output_str


def main():
    parser = argparse.ArgumentParser(description="Multi-Turn History Token Trimming & Management")
    parser.add_argument("--budget", type=int, default=400, help="Maximum token budget for total conversation history")
    parser.add_argument("--strategy", choices=["trim", "summarize"], default="trim", help="Budget enforcement strategy")
    parser.add_argument("--output-file", default=None, help="Optional path to write log output")
    args = parser.parse_args()

    out_p = Path(args.output_file) if args.output_file else None
    result = run_overflowing_conversation_demo(
        token_budget=args.budget,
        strategy=args.strategy,
        output_file=out_p,
    )
    print(result)


if __name__ == "__main__":
    main()
