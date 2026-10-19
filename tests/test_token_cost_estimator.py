"""
Automated Unit Tests for Token Counting & Cost Estimation

Tests:
1. Tiktoken tokenizer counting accuracy (Task 1)
2. Token reporting across 3 sample tiers (Task 2)
3. Input vs. Output distinct rate cost calculation (Task 3)
4. Character-to-token ratio variations across prose, code, and symbols (Task 4)
5. Full report generation functionality (Task 5)
"""

import unittest
from pathlib import Path

from src.token_cost_estimator import (
    count_tokens,
    calculate_cost,
    analyze_length_token_relationship,
    run_full_token_and_cost_report,
    SAMPLE_1_SHORT_QUERY,
    SAMPLE_2_PARAGRAPH,
    SAMPLE_3_FULL_DOCUMENT,
    SAMPLE_OUTPUT_RESPONSE,
    MODEL_PRICING,
)


class TestTokenCostEstimator(unittest.TestCase):
    def test_task1_count_tokens(self):
        """Verify Task 1: count_tokens returns positive integer for non-empty text."""
        token_count = count_tokens("Hello world! This is a test.", model_name="gpt-4o-mini")
        self.assertIsInstance(token_count, int)
        self.assertGreater(token_count, 0)
        self.assertEqual(count_tokens(""), 0)

    def test_task2_three_sample_counts_scale(self):
        """Verify Task 2: Reports token counts for short inquiry, paragraph, and full document."""
        count_short = count_tokens(SAMPLE_1_SHORT_QUERY)
        count_para = count_tokens(SAMPLE_2_PARAGRAPH)
        count_doc = count_tokens(SAMPLE_3_FULL_DOCUMENT)
        count_resp = count_tokens(SAMPLE_OUTPUT_RESPONSE)

        # Assert scale: short < paragraph < full document
        self.assertGreater(count_short, 5)
        self.assertLess(count_short, count_para)
        self.assertLess(count_para, count_doc)
        self.assertGreater(count_doc, 300)
        self.assertGreater(count_resp, 10)

    def test_task3_cost_calculation_differentiates_input_output(self):
        """Verify Task 3: Cost calculation bills input and output tokens at different rates."""
        input_tokens = 1_000_000
        output_tokens = 1_000_000
        pricing = MODEL_PRICING["gpt-4o-mini"]

        result = calculate_cost(input_tokens, output_tokens, model_name="gpt-4o-mini")

        self.assertAlmostEqual(result["input_cost_usd"], pricing["input_per_million"], places=4)
        self.assertAlmostEqual(result["output_cost_usd"], pricing["output_per_million"], places=4)
        self.assertAlmostEqual(
            result["total_cost_usd"],
            pricing["input_per_million"] + pricing["output_per_million"],
            places=4,
        )
        self.assertGreater(result["output_cost_usd"], result["input_cost_usd"])

    def test_task4_length_token_relationship_demonstration(self):
        """Verify Task 4: Length and token count vary across prose vs. code vs. dense IDs."""
        analysis = analyze_length_token_relationship(model_name="gpt-4o-mini")
        self.assertEqual(len(analysis), 5)

        # Standard prose has higher chars per token than dense identifiers or code
        prose_metric = next(item for item in analysis if item["type"] == "Standard English Prose")
        code_metric = next(item for item in analysis if item["type"] == "Code & Shell Snippet")
        id_metric = next(item for item in analysis if item["type"] == "Dense Identifiers & UUIDs")

        self.assertGreater(prose_metric["chars_per_token"], code_metric["chars_per_token"])
        self.assertGreater(prose_metric["chars_per_token"], id_metric["chars_per_token"])

    def test_task5_report_generation(self):
        """Verify Task 5: run_full_token_and_cost_report outputs all required sections."""
        report = run_full_token_and_cost_report(model_name="gpt-4o-mini")
        self.assertIn("TASK 2: TOKEN COUNTS FOR CORPUS SAMPLES", report)
        self.assertIn("TASK 3: RAG COST ESTIMATES", report)
        self.assertIn("TASK 4: TEXT LENGTH VS. TOKEN RELATIONSHIP ANALYSIS", report)
        self.assertIn("Cost Per 1,000 Queries", report)


if __name__ == "__main__":
    unittest.main()
