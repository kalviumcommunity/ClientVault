"""
Automated Unit Tests for Multi-Turn History Management & Token Trimming

Tests:
1. Maintaining multi-turn message history with proper roles (Task 1)
2. Accurate token counting before requests including message protocol overhead (Task 2)
3. Trimming strategy enforcing token budget while strictly preserving system prompt (Task 3)
4. Overflowing conversation demonstration keeping requests within limit (Task 4)
5. Summarization alternative strategy functionality (Task 3)
"""

import unittest
from pathlib import Path

from src.history_manager import (
    ConversationHistoryManager,
    run_overflowing_conversation_demo,
)
from src.token_cost_estimator import count_tokens


class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        self.system_prompt = "You are the Client Support Assistant."
        self.manager = ConversationHistoryManager(
            system_prompt=self.system_prompt,
            max_token_budget=200,
            strategy="trim",
        )

    def test_task1_maintain_multiturn_history(self):
        """Verify Task 1: Maintains sequential history with system, user, and assistant roles."""
        self.manager.add_turn("user", "Hello, I need help with ACME-001 onboarding.")
        self.manager.add_turn("assistant", "Sure, what step are you working on?")

        messages = self.manager.get_messages()
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[2]["role"], "assistant")

        # Invalid role raises ValueError
        with self.assertRaises(ValueError):
            self.manager.add_turn("admin", "Invalid role")

    def test_task2_measure_tokens_before_call(self):
        """Verify Task 2: Measures total tokens including message structure overhead."""
        self.manager.add_turn("user", "Question 1")
        total = self.manager.count_total_tokens()

        sys_tokens = count_tokens(self.system_prompt)
        user_tokens = count_tokens("Question 1")
        # Total should include content tokens plus OpenAI message framing overhead
        self.assertGreater(total, sys_tokens + user_tokens)

    def test_task3_trim_enforces_budget_and_preserves_system_prompt(self):
        """Verify Task 3: When tokens exceed budget, oldest turns are trimmed but system prompt remains intact."""
        small_manager = ConversationHistoryManager(
            system_prompt=self.system_prompt,
            max_token_budget=100,
            strategy="trim",
        )

        # Add multiple verbose turns that exceed 100 tokens
        for i in range(5):
            small_manager.add_turn("user", f"Turn {i}: Very detailed long technical inquiry with document context " * 3)
            small_manager.add_turn("assistant", f"Turn {i}: Long procedural answer verifying facts against runbook " * 3)

        naive_tokens = small_manager.count_total_tokens()
        self.assertGreater(naive_tokens, 100)

        # Enforce budget
        tokens_before, tokens_after = small_manager.enforce_budget()
        self.assertLessEqual(tokens_after, 100)

        # System prompt MUST remain first message
        messages = small_manager.get_messages()
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], self.system_prompt)
        self.assertGreater(len(small_manager.trim_events), 0)

    def test_task4_overflowing_conversation_demo(self):
        """Verify Task 4: Full demo runs and successfully prevents token budget exhaustion."""
        result_text = run_overflowing_conversation_demo(token_budget=350, strategy="trim")
        self.assertIn("EXCEEDS budget limit", result_text)
        self.assertIn("Applied TRIM strategy", result_text)
        self.assertIn("System Prompt Preserved: True", result_text)
        self.assertIn("FINAL CONVERSATION PAYLOAD", result_text)

    def test_summarize_strategy(self):
        """Verify alternative summarization strategy preserves context note."""
        sum_manager = ConversationHistoryManager(
            system_prompt=self.system_prompt,
            max_token_budget=180,
            strategy="summarize",
        )
        for i in range(4):
            sum_manager.add_turn("user", f"Inquiry {i} about step {i} verification.")
            sum_manager.add_turn("assistant", f"Response {i} providing runbook section {i} details.")

        tokens_before, tokens_after = sum_manager.enforce_budget()
        self.assertLessEqual(tokens_after, 180)
        messages = sum_manager.get_messages()
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], self.system_prompt)


if __name__ == "__main__":
    unittest.main()
