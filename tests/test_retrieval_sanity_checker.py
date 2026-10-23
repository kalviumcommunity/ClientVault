"""
Automated Unit Tests for Retrieval Sanity Checker

Tests:
1. Test suite structure and metadata completeness.
2. Confirmation that related documents rank above unrelated ones across positive test cases.
3. Verification of positive separation margins (related score - unrelated score > 0).
4. Reproduction and diagnosis of the surprising case (header dominance over tail chunk in TC-05).
5. Validation of out-of-domain query confidence thresholding (TC-06 low score detection).
6. Validation of client isolation filtering (TC-07 zero cross-client leakage).
7. End-to-end report generation and JSON serialization.
"""

import json
import tempfile
import unittest
from pathlib import Path

from src.corpus_embedder import EmbeddedChunk, VectorStore
from src.retrieval_sanity_checker import (
    RelevanceTestCase,
    RetrievalSanityChecker,
    SanitySummaryReport,
    SanityTestResult,
    format_sanity_report,
    get_curated_sanity_suite,
    run_sanity_benchmark,
)
from src.similarity_ranker import SimilarityRanker


class TestRetrievalSanityChecker(unittest.TestCase):
    """Test suite for the retrieval sanity-checking and quality audit engine."""

    def setUp(self):
        self.checker = RetrievalSanityChecker(force_mock=True)

    def test_default_suite_structure(self):
        """Task 1: Verify curated suite contains complete, valid test case definitions."""
        suite = get_curated_sanity_suite()
        self.assertGreaterEqual(len(suite), 5)

        test_ids = [tc.test_id for tc in suite]
        self.assertEqual(len(test_ids), len(set(test_ids)), "Duplicate test IDs found in suite")

        for tc in suite:
            self.assertTrue(tc.query, f"Test {tc.test_id} has empty query")
            self.assertTrue(tc.intent, f"Test {tc.test_id} has empty intent")
            self.assertTrue(tc.expected_document_id, f"Test {tc.test_id} missing expected document")
            self.assertIsInstance(tc.unrelated_document_ids, list)

    def test_positive_test_cases_related_ranks_above_unrelated(self):
        """Task 2: Confirm related documents rank above unrelated ones for positive test cases."""
        suite = get_curated_sanity_suite()
        standard_cases = [tc for tc in suite if tc.category == "standard"]
        self.assertGreaterEqual(len(standard_cases), 3)

        for tc in standard_cases:
            result: SanityTestResult = self.checker.evaluate_test_case(tc)
            self.assertTrue(result.passed, f"Standard test {tc.test_id} failed: {result.notes}")
            self.assertEqual(
                result.top_ranked_document_id,
                tc.expected_document_id,
                f"Test {tc.test_id}: Expected '{tc.expected_document_id}' at #1, got '{result.top_ranked_document_id}'",
            )
            # Confirm related ranks above unrelated
            self.assertGreater(
                result.expected_doc_best_score,
                result.unrelated_max_score,
                f"Test {tc.test_id}: Expected doc score ({result.expected_doc_best_score}) not higher than unrelated ({result.unrelated_max_score})",
            )
            self.assertGreater(result.margin, 0.20, f"Test {tc.test_id}: Margin {result.margin} below 0.20 threshold")

    def test_surprising_case_header_dominance_tc05(self):
        """Task 3: Identify and verify surprising case of header dominance over granular answer chunk."""
        suite = get_curated_sanity_suite()
        tc05 = next(tc for tc in suite if tc.test_id == "TC-05")

        result = self.checker.evaluate_test_case(tc05)

        # Document-level match should succeed
        self.assertEqual(result.top_ranked_document_id, "acme_onboarding")
        self.assertEqual(result.status, "BORDERLINE")

        # Surprising behavior: chunk tok_000 (header) ranks ahead of tok_002 (exact 48hr rule)
        self.assertEqual(result.top_ranked_chunk_id, "acme_onboarding#tok_000")
        self.assertGreater(result.rank_of_expected_chunk, 1)
        self.assertIn("behind header chunk", result.notes)

    def test_out_of_domain_confidence_cutoff_tc06(self):
        """Task 3: Confirm out-of-domain query is correctly flagged as low confidence."""
        suite = get_curated_sanity_suite()
        tc06 = next(tc for tc in suite if tc.test_id == "TC-06")

        result = self.checker.evaluate_test_case(tc06)

        # Should PASS the threshold test because max score is well below 0.60
        self.assertEqual(result.status, "PASS")
        self.assertTrue(result.passed)
        self.assertLess(result.top_score, 0.60, f"Out of domain query scored too high: {result.top_score}")
        self.assertIn("Prevents false positive hallucinations", result.notes)

    def test_cross_client_isolation_tc07(self):
        """Task 2 & 3: Confirm client filtering isolates candidates and prevents tenant leakage."""
        suite = get_curated_sanity_suite()
        tc07 = next(tc for tc in suite if tc.test_id == "TC-07")

        result = self.checker.evaluate_test_case(tc07)

        # All candidate previews must strictly belong to client NEXUS-002
        for cand in result.ranking_preview:
            # Check against vector store chunk metadata
            chunk = self.checker.ranker.store.get(cand["chunk_id"])
            self.assertIsNotNone(chunk)
            self.assertEqual(chunk.metadata.get("client_id"), "NEXUS-002")

    def test_run_suite_and_report_summary(self):
        """Task 4: Confirm complete suite execution compiles clean metrics and findings."""
        report: SanitySummaryReport = self.checker.run_suite()

        self.assertEqual(report.total_tests, 7)
        self.assertEqual(report.failed_count, 0)
        self.assertGreater(report.passed_count, 0)
        self.assertGreater(report.borderline_count, 0)
        self.assertGreaterEqual(len(report.surprising_findings), 3)
        self.assertGreaterEqual(len(report.recommendations), 3)

        # Format report text
        text_report = format_sanity_report(report)
        self.assertIn("ClientVault — Retrieval Relevance Sanity Report", text_report)
        self.assertIn("EXECUTIVE SUMMARY", text_report)
        self.assertIn("SURPRISING & FAILING CASE DIAGNOSTICS", text_report)

        # JSON dictionary export
        data = report.to_dict()
        self.assertEqual(data["total_tests"], 7)
        self.assertEqual(data["failed_count"], 0)

    def test_run_sanity_benchmark_persistence(self):
        """Task 5: Confirm benchmark runner writes log and JSON files to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_log = Path(tmpdir) / "test_sanity.log"
            tmp_json = Path(tmpdir) / "test_sanity.json"

            report, text = run_sanity_benchmark(
                output_log_file=tmp_log,
                output_json_file=tmp_json,
                force_mock=True,
            )

            self.assertTrue(tmp_log.exists())
            self.assertTrue(tmp_json.exists())
            self.assertGreater(tmp_log.stat().st_size, 500)

            with open(tmp_json, "r", encoding="utf-8") as f:
                saved_json = json.load(f)
            self.assertEqual(saved_json["total_tests"], 7)


if __name__ == "__main__":
    unittest.main()
