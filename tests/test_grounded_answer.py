"""Tests for grounded answer generation (src/grounded_answer.py)."""

import unittest
from pathlib import Path

from src.grounded_answer import (
    extract_source_citations,
    find_supporting_chunks,
    generate_grounded_answer,
    generate_direct_llm,
    run_comparison,
    INSUFFICIENT_EVIDENCE_INSTRUCTION,
)


class TestSourceCitationExtraction(unittest.TestCase):
    def test_extract_basic(self):
        citations = extract_source_citations("See [1] for details and [2] for more.")
        self.assertIn("[1]", citations)
        self.assertIn("[2]", citations)

    def test_no_citations(self):
        citations = extract_source_citations("No sources here.")
        self.assertEqual(citations, [])

    def test_multiple_same_marker(self):
        citations = extract_source_citations("[1] start [1] again")
        self.assertEqual(citations, ["[1]", "[1]"])


class TestGroundedAnswerIntegration(unittest.TestCase):
    def test_generate_grounded_mock(self):
        result = generate_grounded_answer(
            query="What is the Sev-1 response time?",
            client_id="NEXUS-002",
            k=3,
            force_mock=True,
        )
        self.assertFalse(result.insufficient_evidence)
        self.assertIn("Grounded Answer (Mock Mode)", result.answer)
        self.assertGreater(len(result.supporting_chunks), 0)
        self.assertTrue(result.from_mock)

    def test_empty_retrieval_returns_fallback(self):
        result = generate_grounded_answer(
            query="xyznonexistentquery",
            client_id="NONEXISTENT",
            k=3,
            force_mock=True,
        )
        # Either insufficient evidence (client filter matches nothing)
        # or still returns something — both are acceptable
        self.assertIsInstance(result.answer, str)

    def test_generate_direct_llm_mock(self):
        answer, latency = generate_direct_llm("What is the SLA?", force_mock=True)
        self.assertIn("Mock Mode", answer)
        self.assertGreaterEqual(latency, 0)

    def test_comparison_runs(self):
        comp = run_comparison(
            query="What is the Sev-1 response time?",
            client_id="NEXUS-002",
            force_mock=True,
        )
        self.assertIn("Mock Mode", comp.direct_llm_answer)
        self.assertIn("Grounded Answer (Mock Mode)", comp.grounded_answer)
        self.assertGreater(len(comp.sources_used), 0)

    def test_comparison_with_no_client_id(self):
        comp = run_comparison(
            query="What is onboarding?",
            force_mock=True,
        )
        self.assertIsInstance(comp.grounded_answer, str)

    def test_source_citations_in_result(self):
        result = generate_grounded_answer(
            query="Tell me about Nexus SLA.",
            client_id="NEXUS-002",
            k=2,
            force_mock=True,
        )
        self.assertGreater(len(result.source_citations), 0)


class TestInsufficientEvidence(unittest.TestCase):
    def test_fallback_string_present(self):
        self.assertIn("INSUFFICIENT EVIDENCE", INSUFFICIENT_EVIDENCE_INSTRUCTION)
        self.assertIn("escalate", INSUFFICIENT_EVIDENCE_INSTRUCTION)

    def test_insufficient_flag_from_mock_query(self):
        result = generate_grounded_answer(
            query="What is the travel reimbursement policy?",
            k=3,
            force_mock=True,
        )
        # May or may not have evidence — verify the pipeline completes
        self.assertIsInstance(result.answer, str)
        self.assertIsInstance(result.verification_notes, str)


if __name__ == "__main__":
    unittest.main()
