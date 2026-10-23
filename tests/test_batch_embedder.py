"""
Automated Unit Tests for Scalable Batch Embedding Pipeline, Retries & Cost Tracking
"""

import tempfile
import unittest
from pathlib import Path

from src.batch_embedder import (
    BatchEmbedder,
    BatchEmbeddingStats,
    TransientAPIError,
    TransientRateLimitError,
    calculate_embedding_cost,
    compute_content_hash,
    run_batch_embedding_demonstration,
    DEFAULT_BATCH_SIZE,
    DEFAULT_EMBEDDING_MODEL,
)
from src.chunker import Chunk, ChunkMetadata
from src.corpus_embedder import VectorStore


class TestBatchEmbedder(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tmp_dir.name) / "test_store.json"

        # Create 5 test chunks
        self.chunks = [
            Chunk(
                chunk_id=f"doc_test#tok_{i:03d}",
                content=f"Sample procedural instructions for client onboarding step {i}.",
                metadata=ChunkMetadata(
                    source_id="doc_test",
                    document_id="doc_test",
                    file_path="doc_test.md",
                    file_format="md",
                    section=f"Section {i}",
                    page=1,
                    chunk_index=i,
                    total_chunks=5,
                    start_char=i * 50,
                    end_char=(i + 1) * 50,
                    char_count=50,
                    token_count=15,
                    strategy="token_aware",
                    client_id="ACME-001",
                ),
            )
            for i in range(5)
        ]

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_batch_partitioning(self):
        """Task 1: Verify chunks are split into batches according to batch_size."""
        embedder = BatchEmbedder(
            batch_size=2,
            store_path=self.store_path,
            force_mock=True,
        )
        store, stats = embedder.process_chunks(self.chunks)

        self.assertEqual(stats.total_chunks, 5)
        self.assertEqual(stats.embeddings_generated, 5)
        self.assertEqual(stats.batches_processed, 3)  # ceil(5 / 2) = 3 batches
        self.assertEqual(len(store), 5)

    def test_retry_with_backoff_recovery(self):
        """Task 2: Verify transient errors trigger retry with backoff and succeed."""
        embedder = BatchEmbedder(
            batch_size=3,
            max_retries=2,
            initial_backoff=0.01,
            backoff_factor=1.5,
            store_path=self.store_path,
            force_mock=True,
        )

        # Inject transient rate limit error on batch 1
        embedder.simulate_transient_failure_on_batch(
            batch_idx=1,
            error=TransientRateLimitError("Rate limit exceeded: 429 Too Many Requests"),
        )

        store, stats = embedder.process_chunks(self.chunks)

        self.assertEqual(stats.retry_count, 1)
        self.assertEqual(len(stats.retry_events), 1)
        self.assertEqual(stats.retry_events[0]["error_type"], "TransientRateLimitError")
        self.assertEqual(stats.batches_failed, 0)
        self.assertEqual(stats.embeddings_generated, 5)

    def test_failed_batch_exhaustion_recorded(self):
        """Task 2: Verify exhausted retries mark batch as failed and report details."""
        embedder = BatchEmbedder(
            batch_size=5,
            max_retries=1,
            initial_backoff=0.01,
            store_path=self.store_path,
            force_mock=True,
        )

        # Inject 2 consecutive errors on batch 1 (exceeding max_retries = 1)
        embedder.simulate_transient_failure_on_batch(batch_idx=1, error=TransientAPIError("503 Service Unavailable"))
        embedder.simulate_transient_failure_on_batch(batch_idx=1, error=TransientAPIError("503 Service Unavailable"))

        store, stats = embedder.process_chunks(self.chunks)

        self.assertEqual(stats.batches_failed, 1)
        self.assertEqual(stats.embeddings_generated, 0)
        self.assertEqual(len(stats.failed_batches), 1)
        self.assertEqual(stats.failed_batches[0]["batch_idx"], 1)
        self.assertIn("503 Service Unavailable", stats.failed_batches[0]["final_error"])

    def test_cost_calculation(self):
        """Task 3: Verify token cost calculations across model tiers."""
        cost_1m = calculate_embedding_cost(1_000_000, model="text-embedding-3-small")
        self.assertAlmostEqual(cost_1m, 0.020, places=4)

        cost_500k = calculate_embedding_cost(500_000, model="text-embedding-3-small")
        self.assertAlmostEqual(cost_500k, 0.010, places=4)

        cost_large = calculate_embedding_cost(1_000_000, model="text-embedding-3-large")
        self.assertAlmostEqual(cost_large, 0.130, places=4)

    def test_skip_already_embedded_chunks_on_rerun(self):
        """Task 4: Verify already-embedded chunks are skipped on subsequent runs."""
        embedder = BatchEmbedder(
            batch_size=2,
            store_path=self.store_path,
            force_mock=True,
        )

        # Run 1: Embed all chunks
        store1, stats1 = embedder.process_chunks(self.chunks)
        self.assertEqual(stats1.embeddings_generated, 5)
        self.assertEqual(stats1.chunks_skipped, 0)
        self.assertGreater(stats1.run_cost_usd, 0.0)

        # Run 2: Re-run over identical corpus
        embedder_rerun = BatchEmbedder(
            batch_size=2,
            store_path=self.store_path,
            force_mock=True,
        )
        store2, stats2 = embedder_rerun.process_chunks(self.chunks)

        self.assertEqual(stats2.embeddings_generated, 0)
        self.assertEqual(stats2.chunks_skipped, 5)
        self.assertEqual(stats2.batches_processed, 0)
        self.assertEqual(stats2.run_cost_usd, 0.0)
        self.assertGreater(stats2.cost_saved_usd, 0.0)

    def test_content_hash_mutation_detection(self):
        """Task 4: Changing chunk text must invalidate cache and trigger re-embedding."""
        embedder = BatchEmbedder(
            batch_size=5,
            store_path=self.store_path,
            force_mock=True,
        )
        embedder.process_chunks(self.chunks)

        # Mutate 1 chunk content
        mutated_chunks = list(self.chunks)
        mutated_chunks[0] = Chunk(
            chunk_id=self.chunks[0].chunk_id,
            content="Brand new revised instructions that differ from original.",
            metadata=self.chunks[0].metadata,
        )

        embedder2 = BatchEmbedder(
            batch_size=5,
            store_path=self.store_path,
            force_mock=True,
        )
        store, stats = embedder2.process_chunks(mutated_chunks)

        # 4 chunks should be skipped, 1 re-embedded
        self.assertEqual(stats.chunks_skipped, 4)
        self.assertEqual(stats.embeddings_generated, 1)

    def test_run_batch_demonstration_end_to_end(self):
        """Task 5: Verify the complete demonstration runner executes cleanly."""
        log_path = Path(self.tmp_dir.name) / "test_run.log"
        store_path = Path(self.tmp_dir.name) / "test_vectors.json"

        report = run_batch_embedding_demonstration(
            output_log_file=log_path,
            output_store_file=store_path,
            batch_size=2,
            force_mock=True,
        )

        self.assertTrue(log_path.exists())
        self.assertTrue(store_path.exists())
        self.assertIn("Scalable Batch Embedding & Cost-Tracking Pipeline", report)
        self.assertIn("RUN 1: INITIAL BATCH EMBEDDING WITH TRANSIENT RETRY", report)
        self.assertIn("RUN 2: IDEMPOTENT RE-RUN", report)
        self.assertIn("Zero duplicate API calls", report)


if __name__ == "__main__":
    unittest.main()
