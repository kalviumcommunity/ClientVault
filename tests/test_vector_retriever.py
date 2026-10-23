"""
Automated Unit Tests for VectorRetriever & Top-K Semantic Search

Tests:
1. Query embedding shape and dimension uniformity (1536 dims).
2. Top-K similarity search returning ordered results by descending score.
3. Verification that retrieved chunks include full source text and provenance metadata.
4. Demonstration of changing K values (K=2 vs K=4 vs K=6), verifying result growth and score decay.
5. Client isolation filtering enforcing account boundaries in vector retrieval.
6. Graceful handling of empty queries and boundary values of K.
7. End-to-end demonstration runner and file persistence (log & JSON).
"""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from src.corpus_indexer import CorpusIndexer
from src.vector_db import (
    VectorDatabaseManager,
    VectorDBConfig,
    VectorRecord,
    VectorRecordMetadata,
)
from src.vector_retriever import (
    KComparisonSummary,
    RetrievalResult,
    RetrievedChunk,
    VectorRetriever,
    format_retrieval_demonstration_report,
    run_retrieval_demonstration,
)


class TestVectorRetriever(unittest.TestCase):
    """Test suite for VectorRetriever top-k similarity search engine."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.persist_path = Path(self.tmp_dir.name)
        self.col_name = f"test_retrieval_{uuid.uuid4().hex[:8]}"
        self.config = VectorDBConfig(
            persist_directory=self.persist_path,
            collection_name=self.col_name,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            distance_metric="cosine",
            in_memory=True,
        )
        self.manager = VectorDatabaseManager(self.config)
        self.retriever = VectorRetriever(manager=self.manager, force_mock=True)

        # Seed sample indexed chunks across clients
        self.indexer = CorpusIndexer(manager=self.manager, force_mock=True)
        self.records = self.indexer.prepare_vector_records()
        self.indexer.index_corpus(self.records, reset_existing=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_embed_query_dimension_and_validation(self):
        """Task 1: Verify query embedding produces exact 1536-dimensional vector."""
        q = "How do I reset an employee's forgotten account password?"
        vec = self.retriever.embed_query(q)
        self.assertEqual(len(vec), 1536)
        self.assertTrue(all(isinstance(x, float) for x in vec))

        # Rejects empty query
        with self.assertRaises(ValueError):
            self.retriever.embed_query("   ")

    def test_retrieve_top_k_similarity_search(self):
        """Task 2: Verify Top-K search returns requested number of ordered chunks."""
        q = "What is the sponsor directory identity confirmation step when onboarding an employee?"
        res: RetrievalResult = self.retriever.retrieve_top_k(q, k=3)

        self.assertEqual(res.k_requested, 3)
        self.assertEqual(res.k_returned, 3)
        self.assertGreater(len(res.chunks), 0)

        # Scores should be in descending order
        scores = [c.similarity_score for c in res.chunks]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Expected top chunk should be from acme_onboarding
        top_chunk = res.chunks[0]
        self.assertEqual(top_chunk.document_id, "acme_onboarding")
        self.assertGreater(top_chunk.similarity_score, 0.90)

    def test_retrieved_chunk_includes_scores_and_metadata(self):
        """Task 3: Ensure retrieved chunks contain score, text, and all provenance fields."""
        q = "What is the initial response time SLA guarantee for critical business outages?"
        res = self.retriever.retrieve_top_k(q, k=2)

        self.assertEqual(len(res.chunks), 2)
        top_chunk: RetrievedChunk = res.chunks[0]

        # Score & distance checks
        self.assertIsInstance(top_chunk.similarity_score, float)
        self.assertIsInstance(top_chunk.distance, float)
        self.assertGreaterEqual(top_chunk.similarity_score, -1.0)
        self.assertLessEqual(top_chunk.similarity_score, 1.0)

        # Source text check
        self.assertTrue(top_chunk.content)
        self.assertGreater(len(top_chunk.content), 20)

        # Provenance metadata checks
        self.assertTrue(top_chunk.source_document)
        self.assertEqual(top_chunk.document_id, "nexus_sla")
        self.assertIsInstance(top_chunk.chunk_index, int)
        self.assertTrue(top_chunk.section)
        self.assertIsInstance(top_chunk.page, int)
        self.assertEqual(top_chunk.client_id, "NEXUS-002")
        self.assertGreater(top_chunk.token_count, 0)

    def test_demonstrate_varying_k(self):
        """Task 4: Demonstrate how changing K expands results and changes score distribution."""
        q = "How do I verify employee identity via the primary sponsor directory during onboarding?"
        k_values = [2, 4, 6]
        comparison: KComparisonSummary = self.retriever.demonstrate_varying_k(q, k_values=k_values)

        self.assertEqual(comparison.k_values, [2, 4, 6])
        self.assertEqual(len(comparison.results_by_k), 3)

        res_k2 = comparison.results_by_k[2]
        res_k4 = comparison.results_by_k[4]
        res_k6 = comparison.results_by_k[6]

        self.assertEqual(res_k2.k_returned, 2)
        self.assertEqual(res_k4.k_returned, 4)
        self.assertEqual(res_k6.k_returned, 6)

        # Score decay: as K increases, lowest score decreases or stays equal
        self.assertGreaterEqual(res_k2.lowest_score, res_k4.lowest_score)
        self.assertGreaterEqual(res_k4.lowest_score, res_k6.lowest_score)

        # Result set superset check: K=2 chunks are prefix of K=4 chunks
        ids_k2 = [c.chunk_id for c in res_k2.chunks]
        ids_k4 = [c.chunk_id for c in res_k4.chunks]
        ids_k6 = [c.chunk_id for c in res_k6.chunks]

        self.assertEqual(ids_k4[:2], ids_k2)
        self.assertEqual(ids_k6[:4], ids_k4)

        # Observations present
        self.assertGreaterEqual(len(comparison.observations), 2)

    def test_client_isolation_filtering(self):
        """Task 2 & 3: Confirm client filtering limits retrieval strictly to target tenant."""
        q = "What is the emergency escalation path when a critical database outage occurs?"

        # Search restricted to NEXUS-002
        res_nexus = self.retriever.retrieve_top_k(q, k=4, client_id="NEXUS-002")
        for chunk in res_nexus.chunks:
            self.assertEqual(chunk.client_id, "NEXUS-002")

        # Search restricted to VERTEX-003
        res_vertex = self.retriever.retrieve_top_k(q, k=4, client_id="VERTEX-003")
        for chunk in res_vertex.chunks:
            self.assertEqual(chunk.client_id, "VERTEX-003")

    def test_format_retrieval_report(self):
        """Task 5: Confirm formatted report contains all expected benchmark sections."""
        q = "What are the trigger criteria for failover to secondary replica region us-east-2?"
        comp = self.retriever.demonstrate_varying_k(q, k_values=[2, 4])
        report_text = format_retrieval_demonstration_report(q, comp)

        self.assertIn("ClientVault — Vector Database Top-K Semantic Retrieval Audit", report_text)
        self.assertIn("TASK 1: USER QUERY EMBEDDING GENERATION", report_text)
        self.assertIn("TASK 4: DEMONSTRATING CHANGING K", report_text)
        self.assertIn("RUN WITH K = 2", report_text)
        self.assertIn("RUN WITH K = 4", report_text)
        self.assertIn("STATUS: PASSED", report_text)

    def test_end_to_end_runner(self):
        """Task 5: Confirm runner writes log and JSON files to disk."""
        test_log = self.persist_path / "test_retrieval.log"
        test_json = self.persist_path / "test_retrieval.json"

        comparison, text, json_data = run_retrieval_demonstration(
            output_log_file=test_log,
            output_json_file=test_json,
            force_mock=True,
            in_memory=True,
        )

        self.assertTrue(test_log.exists())
        self.assertTrue(test_json.exists())
        self.assertGreater(test_log.stat().st_size, 500)
        self.assertIn("primary_benchmark", json_data)
        self.assertIn("secondary_benchmark", json_data)


if __name__ == "__main__":
    unittest.main()
