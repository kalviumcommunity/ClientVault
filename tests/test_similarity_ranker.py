"""
Automated Unit Tests for Similarity Ranking, Metric Computation, and Vector Retrieval
"""

import tempfile
import unittest
from pathlib import Path

from src.corpus_embedder import (
    CorpusEmbedder,
    EmbeddedChunk,
    VectorStore,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
)
from src.similarity_ranker import (
    RankedChunk,
    RankingSummary,
    SimilarityRanker,
    cosine_similarity,
    dot_product,
    euclidean_distance,
    get_metric_justification,
    run_similarity_ranking_demonstration,
)


class TestSimilarityRanker(unittest.TestCase):
    def setUp(self):
        # Create a small mock vector store with realistic 1536-dim vectors
        self.embedder = CorpusEmbedder(dimension=DEFAULT_EMBEDDING_DIM, force_mock=True)

        text_acme = "Password reset procedure for ACME client user account."
        text_nexus = "Nexus SLA escalation hierarchy and financial penalties."
        text_vertex = "Disaster recovery failover database replica activation."

        vecs = self.embedder.embed_texts([text_acme, text_nexus, text_vertex])

        self.chunk_acme = EmbeddedChunk(
            chunk_id="acme#c1",
            content=text_acme,
            vector=vecs[0],
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata={"source_id": "acme_doc", "client_id": "ACME-001", "section": "Security", "page": 1},
            model=DEFAULT_EMBEDDING_MODEL,
        )
        self.chunk_nexus = EmbeddedChunk(
            chunk_id="nexus#c1",
            content=text_nexus,
            vector=vecs[1],
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata={"source_id": "nexus_doc", "client_id": "NEXUS-002", "section": "SLA", "page": 1},
            model=DEFAULT_EMBEDDING_MODEL,
        )
        self.chunk_vertex = EmbeddedChunk(
            chunk_id="vertex#c1",
            content=text_vertex,
            vector=vecs[2],
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata={"source_id": "vertex_doc", "client_id": "VERTEX-003", "section": "DR", "page": 1},
            model=DEFAULT_EMBEDDING_MODEL,
        )
        self.store = VectorStore([self.chunk_acme, self.chunk_nexus, self.chunk_vertex])

    def test_metric_computation_cosine_similarity(self):
        """Task 1: Verify cosine similarity math, bounds, and edge cases."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.0, 2.0, 3.0]
        vec_orth = [-2.0, 1.0, 0.0]  # dot product = -2 + 2 = 0
        vec_opp = [-1.0, -2.0, -3.0]

        # Identical vectors
        self.assertAlmostEqual(cosine_similarity(vec1, vec2), 1.0, places=4)

        # Orthogonal vectors
        self.assertAlmostEqual(cosine_similarity(vec1, vec_orth), 0.0, places=4)

        # Opposing vectors
        self.assertAlmostEqual(cosine_similarity(vec1, vec_opp), -1.0, places=4)

        # Zero vector handling
        self.assertEqual(cosine_similarity(vec1, [0.0, 0.0, 0.0]), 0.0)

        # Dimension mismatch
        with self.assertRaises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_metric_computation_euclidean_distance(self):
        """Task 1: Verify Euclidean distance calculation and error handling."""
        p1 = [0.0, 0.0]
        p2 = [3.0, 4.0]
        self.assertAlmostEqual(euclidean_distance(p1, p2), 5.0, places=4)

        # Identical points
        self.assertEqual(euclidean_distance(p1, p1), 0.0)

        # Dimension mismatch
        with self.assertRaises(ValueError):
            euclidean_distance([1.0], [1.0, 2.0])

    def test_rank_for_query_descending_order(self):
        """Task 2 & 3: Verify candidate chunks are ranked strictly descending by score."""
        ranker = SimilarityRanker(store=self.store, force_mock=True)
        summary = ranker.rank_for_query("How do I reset my account password?", top_k=2, bottom_k=1)

        self.assertEqual(summary.total_candidates, 3)
        self.assertGreater(len(summary.ranked_chunks), 0)

        # Confirm strictly descending scores
        scores = [c.score for c in summary.ranked_chunks]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Confirm ranks start at 1 and increment sequentially
        ranks = [c.rank for c in summary.ranked_chunks]
        self.assertEqual(ranks, [1, 2, 3])

    def test_extrema_identification_most_and_least_similar(self):
        """Task 3: Confirm identification of most similar and least similar chunks."""
        ranker = SimilarityRanker(store=self.store, force_mock=True)
        summary = ranker.rank_for_query("How do I reset password?", top_k=1, bottom_k=1)

        # Most similar must have highest score
        self.assertEqual(len(summary.most_similar), 1)
        self.assertEqual(summary.most_similar[0].score, summary.highest_score)

        # Least similar must have lowest score
        self.assertEqual(len(summary.least_similar), 1)
        self.assertEqual(summary.least_similar[0].score, summary.lowest_score)

        # Top match should score higher than bottom match
        self.assertGreater(summary.most_similar[0].score, summary.least_similar[0].score)
        self.assertGreater(summary.score_spread, 0.0)

    def test_client_isolation_filtering_in_ranking(self):
        """Verify ranking with client isolation restricts candidates to target account."""
        ranker = SimilarityRanker(store=self.store, force_mock=True)
        summary = ranker.rank_for_query("password reset", client_id="ACME-001")

        self.assertEqual(summary.total_candidates, 1)
        self.assertEqual(summary.ranked_chunks[0].chunk_id, "acme#c1")
        self.assertEqual(summary.ranked_chunks[0].metadata["client_id"], "ACME-001")

    def test_metric_justification_structure(self):
        """Task 4: Confirm metric justification provides required rationales."""
        justification = get_metric_justification()
        self.assertEqual(justification["chosen_metric"], "Cosine Similarity")
        self.assertIn("Directional Alignment", justification["full_text"])
        self.assertIn("Hyperspheres", justification["full_text"])
        self.assertGreater(len(justification["reasons"]), 2)

    def test_run_similarity_ranking_demonstration_end_to_end(self):
        """Task 5: Verify the demonstration executes and saves log and JSON artifacts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "output.log"
            json_path = Path(tmp_dir) / "rankings.json"

            report = run_similarity_ranking_demonstration(
                output_log_file=log_path,
                output_json_file=json_path,
                force_mock=True,
            )

            self.assertTrue(log_path.exists())
            self.assertTrue(json_path.exists())
            self.assertIn("Semantic Similarity Ranking & Vector Retrieval Benchmark", report)
            self.assertIn("TASK 4: RETRIEVAL METRIC JUSTIFICATION", report)
            self.assertIn("MOST SIMILAR CHUNKS", report)
            self.assertIn("LEAST SIMILAR CHUNKS", report)


if __name__ == "__main__":
    unittest.main()
