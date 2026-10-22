"""
Automated Unit Tests for Embedding Generation, Dimension Reporting, and Semantic Similarity
"""

import math
import tempfile
import unittest
from pathlib import Path

from src.embedding_demo import (
    SemanticEmbedder,
    cosine_similarity,
    l2_norm,
    normalize_vector,
    verify_vector_dimensions,
    compare_similarity_pairs,
    run_embedding_demonstration,
    DEFAULT_EMBEDDING_DIM,
    SAMPLE_TEXT_A,
    SAMPLE_TEXT_B,
    SAMPLE_TEXT_C,
    SAMPLE_TEXT_UNRELATED,
)


class TestEmbeddingDemo(unittest.TestCase):
    def setUp(self):
        self.embedder = SemanticEmbedder(force_mock=True, dimension=DEFAULT_EMBEDDING_DIM)

    def test_generate_embeddings_shape_and_norm(self):
        """Task 1: Verify embeddings are generated with correct dimension and normalized norm."""
        res_a = self.embedder.embed_text(SAMPLE_TEXT_A, label="text_a")
        res_b = self.embedder.embed_text(SAMPLE_TEXT_B, label="text_b")
        res_unrelated = self.embedder.embed_text(SAMPLE_TEXT_UNRELATED, label="text_unrelated")

        self.assertEqual(res_a.dimension, DEFAULT_EMBEDDING_DIM)
        self.assertEqual(res_b.dimension, DEFAULT_EMBEDDING_DIM)
        self.assertEqual(res_unrelated.dimension, DEFAULT_EMBEDDING_DIM)

        self.assertEqual(len(res_a.vector), DEFAULT_EMBEDDING_DIM)
        self.assertEqual(len(res_b.vector), DEFAULT_EMBEDDING_DIM)
        self.assertEqual(len(res_unrelated.vector), DEFAULT_EMBEDDING_DIM)

        # Norm should be approximately 1.0 (unit vector)
        self.assertAlmostEqual(res_a.norm, 1.0, places=2)
        self.assertAlmostEqual(res_b.norm, 1.0, places=2)
        self.assertAlmostEqual(res_unrelated.norm, 1.0, places=2)

    def test_vector_dimension_uniformity(self):
        """Task 2: Confirm that every sample text produces a vector of the exact same length."""
        samples = [
            ("short", "Short query"),
            ("medium", "This is a medium length procedural query for client support."),
            ("long", "A very long document paragraph detailing database disaster recovery protocols and steps."),
            ("special", "UUID: 1234-abcd-5678, IP: 192.168.1.1, Code: `auth.verify_token()`"),
        ]
        results = self.embedder.embed_corpus(samples)
        check = verify_vector_dimensions(results)

        self.assertTrue(check["all_same_length"])
        self.assertEqual(check["expected_dim"], DEFAULT_EMBEDDING_DIM)
        self.assertEqual(check["verified_count"], 4)
        for dim in check["dimensions"]:
            self.assertEqual(dim, DEFAULT_EMBEDDING_DIM)

    def test_compare_similar_and_dissimilar_texts(self):
        """Task 3: Confirm similar texts score higher than dissimilar texts using cosine similarity."""
        embed_a = self.embedder.embed_text(SAMPLE_TEXT_A, label="query")
        embed_b = self.embedder.embed_text(SAMPLE_TEXT_B, label="similar_runbook")
        embed_c = self.embedder.embed_text(SAMPLE_TEXT_C, label="paraphrase")
        embed_unrelated = self.embedder.embed_text(SAMPLE_TEXT_UNRELATED, label="unrelated")

        sim_ab = cosine_similarity(embed_a.vector, embed_b.vector)
        sim_ac = cosine_similarity(embed_a.vector, embed_c.vector)
        sim_a_unrelated = cosine_similarity(embed_a.vector, embed_unrelated.vector)

        # Similar pairs must score high
        self.assertGreater(sim_ab, 0.70)
        self.assertGreater(sim_ac, 0.70)

        # Dissimilar pair must score low
        self.assertLess(sim_a_unrelated, 0.20)

        # Similar pair must score strictly higher than dissimilar pair
        self.assertGreater(sim_ab, sim_a_unrelated)
        self.assertGreater(sim_ac, sim_a_unrelated)

        # Test pair comparison helper
        comp = compare_similarity_pairs(embed_a, embed_b, embed_unrelated)
        self.assertTrue(comp["similar_scores_higher"])
        self.assertGreater(comp["similarity_delta"], 0.50)

    def test_cosine_similarity_properties(self):
        """Verify mathematical properties of cosine similarity."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        vec3 = [0.0, 1.0, 0.0]
        vec4 = [-1.0, 0.0, 0.0]

        # Identical vectors: cos(theta) = 1.0
        self.assertAlmostEqual(cosine_similarity(vec1, vec2), 1.0)

        # Orthogonal vectors: cos(theta) = 0.0
        self.assertAlmostEqual(cosine_similarity(vec1, vec3), 0.0)

        # Opposite vectors: cos(theta) = -1.0
        self.assertAlmostEqual(cosine_similarity(vec1, vec4), -1.0)

        # Zero vector handling: no crash, returns 0.0
        zero_vec = [0.0, 0.0, 0.0]
        self.assertEqual(cosine_similarity(vec1, zero_vec), 0.0)

        # Dimension mismatch raises ValueError
        with self.assertRaises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_run_demonstration_end_to_end(self):
        """Task 5: Verify the end-to-end demonstration generates full report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "test_report.log"
            report = run_embedding_demonstration(output_file=out_file, force_mock=True)

            self.assertTrue(out_file.exists())
            self.assertIn("ClientVault — Text Embedding Generation", report)
            self.assertIn("TASK 1: GENERATE EMBEDDINGS", report)
            self.assertIn("TASK 2: REPORT VECTOR DIMENSION & UNIFORMITY", report)
            self.assertIn("TASK 3: COMPARE SIMILAR VS. DISSIMILAR TEXTS", report)
            self.assertIn("TASK 4: ARCHITECTURAL NOTE", report)
            self.assertIn("FULL PAIRWISE COSINE SIMILARITY MATRIX", report)
            self.assertIn("PASSED — Similar pair scores significantly higher", report)


if __name__ == "__main__":
    unittest.main()
