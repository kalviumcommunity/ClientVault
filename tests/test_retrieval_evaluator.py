"""
Unit tests for ClientVault retrieval evaluator metrics (src/retrieval_evaluator.py).
Tests recall@k, precision@k, edge cases: empty results, no relevant labels,
zero chunks returned, duplicate IDs, and out-of-domain handling.
"""

import unittest
from pathlib import Path

from src.retrieval_evaluator import compute_recall_precision


class TestRecallPrecision(unittest.TestCase):
    """Core metric calculation - pure function, no retriever."""

    def test_exact_match(self):
        recall, prec = compute_recall_precision(["a", "b"], ["a", "b"])
        self.assertEqual(recall, 1.0)
        self.assertEqual(prec, 1.0)

    def test_partial_match(self):
        recall, prec = compute_recall_precision(["a", "c"], ["a", "b"])
        self.assertEqual(recall, 0.5)
        self.assertEqual(prec, 0.5)

    def test_no_match(self):
        recall, prec = compute_recall_precision(["c", "d"], ["a", "b"])
        self.assertEqual(recall, 0.0)
        self.assertEqual(prec, 0.0)

    def test_empty_retrieved(self):
        recall, prec = compute_recall_precision([], ["a", "b"])
        self.assertEqual(recall, 0.0)
        self.assertEqual(prec, 0.0)

    def test_no_relevant(self):
        recall, prec = compute_recall_precision(["a", "b"], [])
        self.assertIsNone(recall)
        self.assertIsNone(prec)

    def test_both_empty(self):
        recall, prec = compute_recall_precision([], [])
        self.assertIsNone(recall)
        self.assertIsNone(prec)

    def test_duplicates_in_retrieved(self):
        recall, prec = compute_recall_precision(["a", "a", "b", "b"], ["a", "c"])
        self.assertEqual(recall, 0.5)
        # precision uses len(retrieved_ids), not set, so 1/4=0.25
        self.assertEqual(prec, 0.25)

    def test_more_relevant_than_retrieved(self):
        recall, prec = compute_recall_precision(["a"], ["a", "b", "c"])
        self.assertEqual(round(recall, 4), round(1.0/3.0, 4))
        self.assertEqual(prec, 1.0)

    def test_precision_handles_more_retrieved(self):
        recall, prec = compute_recall_precision(["a", "b", "c", "d"], ["a"])
        self.assertEqual(recall, 1.0)
        self.assertEqual(prec, 0.25)


class TestRecallPrecisionIntegration(unittest.TestCase):
    """Integration tests using real retriever and real query set."""

    @classmethod
    def setUpClass(cls):
        from src.retrieval_evaluator import evaluate_query_set
        from src.filtered_retriever import FilteredRetriever
        # store references as module-level to avoid unittest binding issues
        import tests.test_retrieval_evaluator as m
        m._EVAL_FN = evaluate_query_set
        m._RET_CLS = FilteredRetriever

    def _run_eval(self, k=5, search_mode="hybrid", threshold=None):
        import tests.test_retrieval_evaluator as m
        ret = m._RET_CLS(force_mock=True)
        return m._EVAL_FN(
            Path("retrieval_eval_queries.json"), k, ret, search_mode, threshold
        )

    def test_evaluation_runs(self):
        s = self._run_eval()
        self.assertGreater(s.total_queries, 0)
        self.assertGreater(s.in_domain_queries, 0)
        self.assertGreaterEqual(s.out_of_domain_queries, 1)

    def test_macro_avg_recall_is_float_or_none(self):
        s = self._run_eval()
        if s.macro_avg_recall is not None:
            self.assertGreaterEqual(s.macro_avg_recall, 0.0)
            self.assertLessEqual(s.macro_avg_recall, 1.0)

    def test_macro_avg_precision_is_float_or_none(self):
        s = self._run_eval()
        if s.macro_avg_precision is not None:
            self.assertGreaterEqual(s.macro_avg_precision, 0.0)
            self.assertLessEqual(s.macro_avg_precision, 1.0)

    def test_all_queries_present(self):
        s = self._run_eval()
        self.assertEqual(len(s.per_query), s.total_queries)

    def test_queries_match_expected_ids(self):
        s = self._run_eval()
        ids = {r.query_id for r in s.per_query}
        expected = {f"REQ-{i:02d}" for i in range(1, 11)}
        self.assertEqual(ids, expected)

    def test_vector_mode(self):
        s = self._run_eval(search_mode="vector")
        self.assertGreater(s.total_queries, 0)

    def test_safe_rejection_out_of_domain(self):
        s = self._run_eval()
        for r in s.per_query:
            if r.is_out_of_domain:
                self.assertIsNotNone(r.safe_rejected)

    def test_in_domain_no_safe_rejection(self):
        s = self._run_eval()
        for r in s.per_query:
            if not r.is_out_of_domain:
                self.assertIsNone(r.safe_rejected)

    def test_retrieved_ids_have_chunk_format(self):
        s = self._run_eval()
        for r in s.per_query:
            for cid in r.retrieved_chunk_ids:
                self.assertIn("#", cid)

    def test_k_3_still_runs(self):
        s = self._run_eval(k=3)
        self.assertGreater(s.total_queries, 0)


if __name__ == "__main__":
    unittest.main()
