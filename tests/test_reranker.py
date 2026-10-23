"""
Unit tests for ClientVault Two-Stage Candidate Re-Ranking Pipeline (src/reranker.py).
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.reranker import (
    CandidateReranker,
    compute_cross_interaction_score,
    compute_phrase_and_identifier_score,
    compute_procedural_density_score,
    run_full_reranking_pipeline,
)
from src.vector_db import (
    VectorDatabaseManager,
    VectorDBConfig,
)
from src.vector_retriever import VectorRetriever


class TestCandidateReranker(unittest.TestCase):
    """Test suite for CandidateReranker, scoring algorithms, and before-and-after comparisons."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="clientvault_rerank_test_")
        cls.test_db_dir = Path(cls.temp_dir) / "chroma"
        cls.test_col_name = "test_rerank_col"

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
        cls.reranker = CandidateReranker(
            retriever=cls.vec_retriever,
            force_mock=True,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_compute_cross_interaction_score(self):
        """Test Task 2: Verify cross-interaction scoring on relevant vs irrelevant text."""
        query = "dual-operator authorization for credential provisioning"
        relevant_doc = "Dual-operator authorization is strictly required for credential provisioning in IAM."
        unrelated_doc = "The quick brown fox jumps over the lazy dog in the forest."

        score_rel = compute_cross_interaction_score(query, relevant_doc)
        score_unrel = compute_cross_interaction_score(query, unrelated_doc)

        self.assertGreater(score_rel, 0.40)
        self.assertEqual(score_unrel, 0.0)

    def test_compute_phrase_and_identifier_score(self):
        """Test Task 2: Verify detection of technical codes, identifiers, and phrases."""
        query = "Review ticket in queue SEC-ONB under SOP-DB-FAIL-04"
        doc = "ServiceNow queue SEC-ONB requires compliance with SOP-DB-FAIL-04."

        score, phrases, ids = compute_phrase_and_identifier_score(query, doc)
        self.assertGreater(score, 0.50)
        self.assertIn("sec-onb", ids)
        self.assertIn("sop-db-fail-04", ids)

    def test_compute_procedural_density_score(self):
        """Test Task 2: Verify procedural density scores numbered action steps."""
        proc_doc = "1. Initiate request in IAM. 2. Inspect verification ticket. 3. Sign off with OTP."
        prose_doc = "ACME Logistics was founded in 2012 to provide shipping solutions across North America."

        score_proc = compute_procedural_density_score(proc_doc)
        score_prose = compute_procedural_density_score(prose_doc)

        self.assertGreater(score_proc, score_prose)
        self.assertGreater(score_proc, 0.30)

    def test_retrieve_larger_candidate_set_and_rerank(self):
        """Test Task 1 & 3: Verify initial retrieval pulls K=10 and re-ranks down to K=3."""
        query = "What are the step-by-step procedural rules and dual-operator authorization requirements for provisioning credentials?"
        result = self.reranker.retrieve_and_rerank(
            query=query,
            initial_k=10,
            final_k=3,
            target_client_id="ACME-001",
        )

        self.assertGreaterEqual(result.initial_candidate_count, 5)
        self.assertEqual(len(result.final_selected_chunks), min(3, result.initial_candidate_count))
        self.assertEqual(result.final_k, 3)

        # Check ranks and rank delta logic
        for rc in result.final_selected_chunks:
            self.assertGreater(rc.rerank_score, 0.0)
            self.assertEqual(rc.rank_delta, rc.initial_rank - rc.reranked_rank)

        # Final Rank 1 must have high cross-interaction or phrase score
        top_chunk = result.final_selected_chunks[0]
        self.assertIn(top_chunk.client_id, ["ACME-001", "GLOBAL"])

    def test_before_and_after_comparison(self):
        """Test Task 4: Verify before-and-after ordering comparison tracks rank changes."""
        query = "What is the guaranteed response time SLA and service credit deduction for Sev-1 critical production outages?"
        result = self.reranker.retrieve_and_rerank(
            query=query,
            initial_k=10,
            final_k=3,
            target_client_id="NEXUS-002",
        )

        self.assertGreater(len(result.initial_candidates), 0)
        # Verify candidate pool is ordered descending by rerank_score
        scores = [c.rerank_score for c in result.initial_candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Check that top selected chunks are the first final_k of the pool
        for idx in range(len(result.final_selected_chunks)):
            self.assertEqual(
                result.final_selected_chunks[idx].chunk_id,
                result.initial_candidates[idx].chunk_id,
            )

    def test_full_pipeline_persistence(self):
        """Test Task 5: Verify run_full_reranking_pipeline writes log and JSON output."""
        test_log = Path(self.temp_dir) / "test_rerank.log"
        test_json = Path(self.temp_dir) / "test_rerank.json"

        report_text, results = run_full_reranking_pipeline(
            output_log_path=test_log,
            output_json_path=test_json,
            force_mock=True,
        )

        self.assertTrue(test_log.exists())
        self.assertTrue(test_json.exists())
        self.assertIn("TWO-STAGE CANDIDATE RE-RANKING AUDIT REPORT", report_text)
        self.assertIn("BEFORE-AND-AFTER ORDERING COMPARISON", report_text)
        self.assertEqual(len(results), 3)

        with open(test_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 3)
        self.assertIn("initial_candidates", data[0])
        self.assertIn("final_selected_chunks", data[0])


if __name__ == "__main__":
    unittest.main()
