"""
Automated Unit Tests for Prompt Engineering & Evaluation Suite

Verifies:
1. System and user role distinctness and prompt constraints (Tasks 1 & 2)
2. Prompt variation comparison metrics (Task 3)
3. Safe fallback vs hallucination detection (Tasks 3 & 4)
4. Markdown comparison report generation (Task 5)
"""

import unittest
from pathlib import Path

from src.prompt_eval import (
    load_prompt_text,
    evaluate_output,
    run_prompt_evaluation,
    V1_PATH,
    V2_PATH,
    OUTPUT_REPORT_PATH,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT_DIR / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"


class TestPromptEvaluation(unittest.TestCase):
    def test_task1_and_task2_production_prompt_constraints(self):
        """Verify Task 2: Production prompt defines role, scope (do/don't), length, tone, citations, and fallback."""
        prompt_text = load_prompt_text(V2_PATH)

        # 1. Role & Identity
        self.assertIn("Client Support Knowledge Assistant", prompt_text)
        self.assertIn("ROLE & PURPOSE", prompt_text)

        # 2. Scope Inclusions & Exclusions
        self.assertIn("What you MUST do", prompt_text)
        self.assertIn("What you MUST NOT do", prompt_text)
        self.assertIn("Do NOT hallucinate", prompt_text)
        self.assertIn("Do NOT provide security workarounds", prompt_text)

        # 3. Fallback constraint
        self.assertIn("INSUFFICIENT EVIDENCE: No approved source in this client's knowledge base supports this procedure.", prompt_text)

        # 4. Length and Formatting constraints
        self.assertIn("under 150 words", prompt_text)
        self.assertIn("numbered, sequential steps", prompt_text)

        # 5. Citation constraint
        self.assertIn("[Source: <Document-ID>, Section: <Section-Number>, Page: <Page-Number>]", prompt_text)

        # Ensure default system_prompt.txt matches the production prompt
        default_prompt = load_prompt_text(SYSTEM_PROMPT_PATH)
        self.assertEqual(prompt_text, default_prompt)

    def test_vague_prompt_lacks_safety_controls(self):
        """Verify that Variation A (vague baseline) lacks enterprise constraints."""
        vague_text = load_prompt_text(V1_PATH)
        self.assertNotIn("INSUFFICIENT EVIDENCE", vague_text)
        self.assertNotIn("What you MUST NOT do", vague_text)
        self.assertNotIn("[Source:", vague_text)

    def test_task3_and_task4_prompt_evaluation_mock_execution(self):
        """Verify Task 3 & 4: Execute comparative evaluation and verify metrics."""
        eval_result = run_prompt_evaluation(use_mock=True)
        self.assertEqual(eval_result["status"], "completed")
        results = eval_result["results"]
        self.assertEqual(len(results), 2)

        # Scenario 1: Supported
        sc1 = results[0]
        v1_s1 = sc1["variation_a"]["metrics"]
        v2_s1 = sc1["variation_b"]["metrics"]
        self.assertTrue(v2_s1["has_citation"])
        self.assertFalse(v2_s1["has_filler"])
        self.assertLess(v2_s1["word_count"], v1_s1["word_count"])

        # Scenario 2: Unsupported (2FA Bypass)
        sc2 = results[1]
        v1_s2 = sc2["variation_a"]["metrics"]
        v2_s2 = sc2["variation_b"]["metrics"]
        # Variation A hallucinates
        self.assertTrue(v1_s2["hallucination_detected"])
        self.assertFalse(v1_s2["has_fallback"])
        # Variation B triggers safe fallback
        self.assertTrue(v2_s2["has_fallback"])
        self.assertFalse(v2_s2["hallucination_detected"])

        # Verify report generation
        self.assertTrue(OUTPUT_REPORT_PATH.exists())
        report_content = OUTPUT_REPORT_PATH.read_text(encoding="utf-8")
        self.assertIn("Variation B (Constrained Production)", report_content)
        self.assertIn("INSUFFICIENT EVIDENCE", report_content)


if __name__ == "__main__":
    unittest.main()
