"""
Unit tests for ClientVault Retrieval Tuning and Configuration Optimizer (src/retrieval_tuner.py).
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.filtered_retriever import FilteredRetriever
from src.retrieval_tuner import (
    RetrievalSettingConfig,
    RetrievalTuner,
    TuningTestQuery,
    get_benchmark_test_queries,
    get_candidate_retrieval_settings,
    run_full_tuning_pipeline,
)
from src.vector_db import (
    VectorDatabaseManager,
    VectorDBConfig,
)
from src.vector_retriever import VectorRetriever


class TestRetrievalTuner(unittest.TestCase):
    """Test suite for retrieval tuning experiment, settings comparison, and relevance metrics."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="clientvault_tuning_test_")
        cls.test_db_dir = Path(cls.temp_dir) / "chroma"
        cls.test_col_name = "test_tuning_col"

        cls.config = VectorDBConfig(
            persist_directory=cls.test_db_dir,
            collection_name=cls.test_col_name,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            distance_metric="cosine",
            in_memory=True,
        )
        cls.manager = VectorDatabaseManager(cls.config)
        cls.vec_retriever = VectorRetriever(manager=cls.manager, force_mock=True)
        cls.vec_retriever.ensure_corpus_indexed()
        cls.filtered_retriever = FilteredRetriever(
            vector_retriever=cls.vec_retriever,
            force_mock=True,
        )
        cls.tuner = RetrievalTuner(
            retriever=cls.filtered_retriever,
            force_mock=True,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_benchmark_test_queries_schema(self):
        """Test Task 1: Verify benchmark queries contain in-domain and out-of-domain cases."""
        queries = get_benchmark_test_queries()
        self.assertGreaterEqual(len(queries), 5)

        in_domain = [q for q in queries if not q.is_out_of_domain]
        out_of_domain = [q for q in queries if q.is_out_of_domain]

        self.assertGreater(len(in_domain), 0)
        self.assertGreater(len(out_of_domain), 0)

        for q in in_domain:
            self.assertIsNotNone(q.target_client_id)
            self.assertGreater(len(q.expected_document_ids), 0)

    def test_candidate_retrieval_settings(self):
        """Test Task 2: Verify candidate retrieval settings define distinct configurations."""
        settings = get_candidate_retrieval_settings()
        self.assertGreaterEqual(len(settings), 3)

        setting_ids = [s.setting_id for s in settings]
        self.assertIn("SETTING_A_NAIVE_VECTOR", setting_ids)
        self.assertIn("SETTING_B_FILTERED_VECTOR", setting_ids)
        self.assertIn("SETTING_D_OPTIMAL_FILTERED_HYBRID", setting_ids)

        naive = next(s for s in settings if s.setting_id == "SETTING_A_NAIVE_VECTOR")
        optimal = next(s for s in settings if s.setting_id == "SETTING_D_OPTIMAL_FILTERED_HYBRID")

        self.assertFalse(naive.use_metadata_filter)
        self.assertTrue(optimal.use_metadata_filter)
        self.assertEqual(optimal.search_mode, "hybrid")
        self.assertIsNotNone(optimal.score_threshold)

    def test_in_domain_and_out_of_domain_evaluation(self):
        """Test Task 3: Verify evaluate_query calculates hit rates and safe rejection."""
        settings = get_candidate_retrieval_settings()
        optimal_setting = next(s for s in settings if s.setting_id == "SETTING_D_OPTIMAL_FILTERED_HYBRID")

        queries = get_benchmark_test_queries()
        in_query = next(q for q in queries if q.query_id == "TQ-01")
        out_query = next(q for q in queries if q.is_out_of_domain)

        # In-domain query evaluation
        in_res = self.tuner.evaluate_query(in_query, optimal_setting)
        self.assertTrue(in_res.top_1_hit)
        self.assertTrue(in_res.top_k_hit)
        self.assertEqual(in_res.account_isolation_pct, 100.0)

        # Out-of-domain query evaluation (should safely return 0 results above threshold)
        out_res = self.tuner.evaluate_query(out_query, optimal_setting)
        self.assertTrue(out_res.safe_rejection)
        self.assertEqual(out_res.retrieved_count, 0)

    def test_setting_comparison_and_winner_selection(self):
        """Test Task 2 & 4: Verify Setting D outperforms Setting A and is chosen as winner."""
        report = self.tuner.run_tuning_experiment()
        self.assertEqual(report.best_setting_id, "SETTING_D_OPTIMAL_FILTERED_HYBRID")

        summary_a = next(s for s in report.settings_evaluated if s.setting.setting_id == "SETTING_A_NAIVE_VECTOR")
        summary_d = next(s for s in report.settings_evaluated if s.setting.setting_id == "SETTING_D_OPTIMAL_FILTERED_HYBRID")

        # Optimal setting must have strictly higher Account Isolation than Naive setting
        self.assertGreater(summary_d.account_isolation_pct, summary_a.account_isolation_pct)
        # Optimal setting must have higher Top-1 Hit Rate
        self.assertGreaterEqual(summary_d.top_1_hit_rate_pct, summary_a.top_1_hit_rate_pct)
        # Optimal setting must achieve 100% Out-of-Domain Safety
        self.assertEqual(summary_d.out_of_domain_safety_pct, 100.0)
        # Optimal setting must achieve higher composite score
        self.assertGreater(summary_d.composite_score, summary_a.composite_score)

    def test_full_pipeline_persistence(self):
        """Test Task 5: Verify run_full_tuning_pipeline persists formatted log and JSON."""
        test_log = Path(self.temp_dir) / "test_tuning.log"
        test_json = Path(self.temp_dir) / "test_tuning.json"

        report_text, report = run_full_tuning_pipeline(
            output_log_path=test_log,
            output_json_path=test_json,
            force_mock=True,
        )

        self.assertTrue(test_log.exists())
        self.assertTrue(test_json.exists())
        self.assertIn("RETRIEVAL TUNING EXPERIMENT & OPTIMIZATION AUDIT", report_text)
        self.assertIn("WINNER:", report_text)

        with open(test_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("best_setting_id", data)
        self.assertIn("settings_evaluated", data)
        self.assertEqual(len(data["settings_evaluated"]), 4)


if __name__ == "__main__":
    unittest.main()
