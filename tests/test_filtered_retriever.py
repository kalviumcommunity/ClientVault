"""
Unit tests for ClientVault Filtered Retrieval and Hybrid Search Engine (src/filtered_retriever.py).
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.corpus_indexer import CorpusIndexer
from src.filtered_retriever import (
    FilteredRetriever,
    MetadataFilter,
    compute_keyword_similarity,
    extract_exact_identifiers,
    extract_keywords,
    run_full_filtered_retriever_pipeline,
    run_precision_demonstrations,
)
from src.vector_db import (
    VectorDatabaseManager,
    VectorDBConfig,
    load_vector_db_config,
)
from src.vector_retriever import VectorRetriever


class TestFilteredRetriever(unittest.TestCase):
    """Test suite for FilteredRetriever, MetadataFilter, and lexical hybrid matching."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="clientvault_filtered_test_")
        cls.test_db_dir = Path(cls.temp_dir) / "chroma"
        cls.test_col_name = "test_filtered_col"

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
        # Ensure corpus is indexed
        cls.vec_retriever.ensure_corpus_indexed()
        cls.filtered_retriever = FilteredRetriever(
            vector_retriever=cls.vec_retriever,
            force_mock=True,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_metadata_filter_to_chroma_where(self):
        """Test Task 1: Verify conversion of MetadataFilter to ChromaDB where clause syntax."""
        # Empty filter
        empty_filter = MetadataFilter()
        self.assertIsNone(empty_filter.to_chroma_where())

        # Single condition
        single_filter = MetadataFilter(client_id="ACME-001")
        self.assertEqual(single_filter.to_chroma_where(), {"client_id": "ACME-001"})

        # Multiple conditions -> $and
        multi_filter = MetadataFilter(
            client_id="NEXUS-002",
            document_id="nexus_sla",
            page=1,
        )
        chroma_where = multi_filter.to_chroma_where()
        self.assertIn("$and", chroma_where)
        self.assertEqual(len(chroma_where["$and"]), 3)
        self.assertIn({"client_id": "NEXUS-002"}, chroma_where["$and"])
        self.assertIn({"document_id": "nexus_sla"}, chroma_where["$and"])
        self.assertIn({"page": 1}, chroma_where["$and"])

    def test_metadata_filter_matches(self):
        """Test Task 1: Verify MetadataFilter.matches against record metadata dictionaries."""
        meta = {
            "client_id": "ACME-001",
            "document_id": "acme_onboarding",
            "section": "Provisioning",
            "page": 2,
        }
        f1 = MetadataFilter(client_id="ACME-001")
        self.assertTrue(f1.matches(meta))

        f2 = MetadataFilter(client_id="NEXUS-002")
        self.assertFalse(f2.matches(meta))

        f3 = MetadataFilter(client_id="ACME-001", page=2)
        self.assertTrue(f3.matches(meta))

        f4 = MetadataFilter(client_id="ACME-001", page=3)
        self.assertFalse(f4.matches(meta))

    def test_keyword_and_identifier_extraction(self):
        """Test Task 3: Verify keyword tokenization and identifier extraction."""
        text = "Ticket in queue SEC-ONB for SOP-DB-FAIL-04 contact admin@acme.com"
        keywords = extract_keywords(text)
        self.assertIn("ticket", keywords)
        self.assertIn("queue", keywords)
        self.assertIn("sec-onb", keywords)

        identifiers = extract_exact_identifiers(text)
        self.assertIn("sec-onb", identifiers)
        self.assertIn("sop-db-fail-04", identifiers)
        self.assertIn("admin@acme.com", identifiers)

    def test_compute_keyword_similarity(self):
        """Test Task 3: Verify keyword similarity score and identifier boost."""
        doc = "ServiceNow queue SEC-ONB governs onboarding verification."
        score, terms, ids = compute_keyword_similarity(
            query="SEC-ONB onboarding ticket",
            document_text=doc,
            boost_identifiers=True,
        )
        self.assertGreater(score, 0.5)
        self.assertIn("sec-onb", ids)
        self.assertIn("onboarding", terms)

        # Unrelated query has near-zero keyword score
        score_unrelated, terms_unrelated, _ = compute_keyword_similarity(
            query="quantum physics astrophysics galaxy",
            document_text=doc,
        )
        self.assertEqual(score_unrelated, 0.0)
        self.assertEqual(len(terms_unrelated), 0)

    def test_filtered_retrieval_account_isolation(self):
        """Test Task 1 & 2: Verify metadata filtering guarantees 100% account isolation."""
        query = "What is the initial response time and priority classification?"
        # Unfiltered search on K=3 returns mixed clients
        unfiltered = self.filtered_retriever.search(
            query=query,
            k=3,
            metadata_filter=None,
            search_mode="vector",
            target_client_id="NEXUS-002",
        )
        self.assertLess(unfiltered.account_isolation_pct, 100.0)

        # Filtered search strictly restricts to NEXUS-002
        filtered = self.filtered_retriever.search(
            query=query,
            k=3,
            metadata_filter=MetadataFilter(client_id="NEXUS-002"),
            search_mode="vector",
            target_client_id="NEXUS-002",
        )
        self.assertEqual(filtered.account_isolation_pct, 100.0)
        for chunk in filtered.chunks:
            self.assertEqual(chunk.client_id, "NEXUS-002")

    def test_hybrid_search_scoring_modes(self):
        """Test Task 3: Compare vector, keyword, and hybrid scoring modes."""
        query = "ticket queue SEC-ONB"
        filter_acme = MetadataFilter(client_id="ACME-001")

        vec_res = self.filtered_retriever.search(
            query=query,
            k=2,
            metadata_filter=filter_acme,
            search_mode="vector",
        )
        hyb_res = self.filtered_retriever.search(
            query=query,
            k=2,
            metadata_filter=filter_acme,
            search_mode="hybrid",
            alpha=0.60,
        )

        self.assertGreater(len(vec_res.chunks), 0)
        self.assertGreater(len(hyb_res.chunks), 0)
        # Check that hybrid results carry both vector and keyword scores
        self.assertGreater(hyb_res.chunks[0].hybrid_score, 0.0)
        self.assertIsNotNone(hyb_res.chunks[0].matched_terms)

    def test_compare_filtered_and_unfiltered_precision_gain(self):
        """Test Task 2 & 4: Verify compare_filtered_and_unfiltered reports positive precision gain."""
        comp = self.filtered_retriever.compare_filtered_and_unfiltered(
            query="What is the initial response time and priority classification for critical service issues?",
            k=3,
            target_client_id="NEXUS-002",
            metadata_filter=MetadataFilter(client_id="NEXUS-002"),
        )
        self.assertGreater(comp.precision_gain_pct, 0.0)
        self.assertGreater(comp.noise_chunks_eliminated, 0)
        self.assertEqual(comp.filtered_isolation_pct, 100.0)

    def test_full_pipeline_persistence(self):
        """Test Task 5: Verify run_full_filtered_retriever_pipeline persists log and JSON."""
        test_log = Path(self.temp_dir) / "test_filtered.log"
        test_json = Path(self.temp_dir) / "test_filtered.json"

        report_text, results = run_full_filtered_retriever_pipeline(
            output_log_path=test_log,
            output_json_path=test_json,
            force_mock=True,
        )

        self.assertTrue(test_log.exists())
        self.assertTrue(test_json.exists())
        self.assertIn("PRECISION GAIN & COMPLIANCE SUMMARY", report_text)

        with open(test_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("case_1_account_isolation", data)
        self.assertIn("case_2_exact_identifier_hybrid", data)
        self.assertIn("case_3_section_scoping", data)


if __name__ == "__main__":
    unittest.main()
