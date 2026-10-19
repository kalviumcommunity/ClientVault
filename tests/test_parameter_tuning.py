"""
Automated Unit Tests for Hyperparameter Tuning & Grounding Experiments

Tests:
1. Temperature sensitivity handling (Task 1)
2. max_tokens length capping (Task 2)
3. Stop sequence and top_p execution (Task 3)
4. Recommended settings validation for grounded retrieval (Task 4)
5. Full experiment report generation (Task 5)
"""

import unittest
from pathlib import Path

from src.parameter_tuning import run_parameter_experiments
from src.token_cost_estimator import count_tokens


class TestParameterTuning(unittest.TestCase):
    def test_parameter_experiments_execution(self):
        """Verify all parameter tasks execute cleanly and output expected sections."""
        report = run_parameter_experiments(use_mock=True)

        # Task 1: Temperature variation
        self.assertIn("TASK 1: TEMPERATURE SENSITIVITY", report)
        self.assertIn("Temperature = 0.0", report)
        self.assertIn("Temperature = 1.2", report)

        # Task 2: max_tokens capping
        self.assertIn("TASK 2: RESPONSE LENGTH CAPPING VIA MAX_TOKENS", report)
        self.assertIn("max_tokens = 35", report)

        # Task 3: Stop sequence & top_p
        self.assertIn("TASK 3: STOP SEQUENCES & TOP_P", report)
        self.assertIn("Parameter 'stop'", report)
        self.assertIn("Parameter 'top_p'", report)

        # Task 4: Recommended settings
        self.assertIn("TASK 4: RECOMMENDED PRODUCTION SETTINGS FOR FACTUAL ENTERPRISE RAG", report)
        self.assertIn("temperature         0.0", report)
        self.assertIn("max_tokens          150 - 250", report)


if __name__ == "__main__":
    unittest.main()
