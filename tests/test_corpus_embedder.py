"""
Automated Unit Tests for Corpus Embedding Generation and Vector Storage Pipeline
"""

import json
import tempfile
import unittest
from pathlib import Path

from src.corpus_embedder import (
    CorpusEmbedder,
    EmbeddedChunk,
    VectorStore,
    cosine_similarity,
    load_embedding_config,
    prepare_corpus_chunks,
    run_corpus_embedding_pipeline,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
)
from src.chunker import Chunk, ChunkMetadata


class TestCorpusEmbedder(unittest.TestCase):
    def setUp(self):
        self.config = {
            "base_url": "https://api.openai.com/v1",
            "api_key": "test-key-mock",
            "model": "text-embedding-3-small",
            "is_configured": True,
        }
        self.embedder = CorpusEmbedder(config=self.config, force_mock=True, dimension=DEFAULT_EMBEDDING_DIM)

    def test_environment_config_loading(self):
        """Task 3: Confirm config loads from environment without hardcoded secrets."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_env = Path(tmp_dir) / ".env"
            test_env.write_text(
                "OPENAI_BASE_URL=https://custom.endpoint.com/v1\n"
                "OPENAI_API_KEY=sk-test-secret-123456789012\n"
                "OPENAI_EMBEDDING_MODEL=text-embedding-3-large\n",
                encoding="utf-8",
            )
            cfg = load_embedding_config(test_env)
            self.assertEqual(cfg["base_url"], "https://custom.endpoint.com/v1")
            self.assertEqual(cfg["api_key"], "sk-test-secret-123456789012")
            self.assertEqual(cfg["model"], "text-embedding-3-large")
            self.assertTrue(cfg["is_configured"])

    def test_embed_chunks_dimension_and_norm(self):
        """Task 1: Verify generated embeddings match expected dimension and unit norm."""
        chunks = [
            Chunk(
                chunk_id="chunk_01",
                content="How to reset forgotten password for client user account.",
                metadata=ChunkMetadata(
                    source_id="doc1",
                    document_id="doc1",
                    file_path="doc1.md",
                    file_format="md",
                    section="Security",
                    page=1,
                    chunk_index=0,
                    total_chunks=1,
                    start_char=0,
                    end_char=58,
                    char_count=58,
                    token_count=12,
                    strategy="token_aware",
                    client_id="ACME-001",
                ),
            ),
            Chunk(
                chunk_id="chunk_02",
                content="Emergency database disaster recovery and failover procedure.",
                metadata=ChunkMetadata(
                    source_id="doc2",
                    document_id="doc2",
                    file_path="doc2.txt",
                    file_format="txt",
                    section="Disaster Recovery",
                    page=1,
                    chunk_index=0,
                    total_chunks=1,
                    start_char=0,
                    end_char=60,
                    char_count=60,
                    token_count=10,
                    strategy="token_aware",
                    client_id="VERTEX-003",
                ),
            ),
        ]

        records = self.embedder.embed_chunks(chunks)
        self.assertEqual(len(records), 2)

        for rec in records:
            self.assertEqual(rec.vector_dim, DEFAULT_EMBEDDING_DIM)
            self.assertEqual(len(rec.vector), DEFAULT_EMBEDDING_DIM)
            # Test unit norm
            norm = sum(x * x for x in rec.vector) ** 0.5
            self.assertAlmostEqual(norm, 1.0, places=2)

    def test_vector_store_storage_and_metadata_retention(self):
        """Task 2: Verify vectors are stored with source chunks and metadata."""
        meta = {
            "source_id": "nexus_sla",
            "document_id": "nexus_sla",
            "section": "Escalation Matrix",
            "page": 2,
            "chunk_index": 1,
            "client_id": "NEXUS-002",
            "token_count": 150,
        }
        chunk = EmbeddedChunk(
            chunk_id="nexus_sla#c01",
            content="Initial response time <= 4 business hours.",
            vector=[0.05] * DEFAULT_EMBEDDING_DIM,
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata=meta,
            model=DEFAULT_EMBEDDING_MODEL,
        )

        store = VectorStore()
        store.add(chunk)

        self.assertEqual(len(store), 1)
        retrieved = store.get("nexus_sla#c01")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.content, "Initial response time <= 4 business hours.")
        self.assertEqual(retrieved.metadata["client_id"], "NEXUS-002")
        self.assertEqual(retrieved.metadata["section"], "Escalation Matrix")
        self.assertEqual(retrieved.metadata["page"], 2)

    def test_vector_store_client_isolation_filter(self):
        """Task 2: Verify filtering by client_id strictly isolates client records."""
        rec1 = EmbeddedChunk(
            chunk_id="c1",
            content="ACME content",
            vector=[0.1] * DEFAULT_EMBEDDING_DIM,
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata={"client_id": "ACME-001"},
            model=DEFAULT_EMBEDDING_MODEL,
        )
        rec2 = EmbeddedChunk(
            chunk_id="c2",
            content="NEXUS content",
            vector=[0.2] * DEFAULT_EMBEDDING_DIM,
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata={"client_id": "NEXUS-002"},
            model=DEFAULT_EMBEDDING_MODEL,
        )
        rec3 = EmbeddedChunk(
            chunk_id="c3",
            content="ACME second content",
            vector=[0.3] * DEFAULT_EMBEDDING_DIM,
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata={"client_id": "ACME-001"},
            model=DEFAULT_EMBEDDING_MODEL,
        )

        store = VectorStore([rec1, rec2, rec3])
        acme_only = store.filter_by_client("ACME-001")
        self.assertEqual(len(acme_only), 2)
        self.assertTrue(all(r.metadata["client_id"] == "ACME-001" for r in acme_only))

        nexus_only = store.filter_by_client("NEXUS-002")
        self.assertEqual(len(nexus_only), 1)
        self.assertEqual(nexus_only[0].chunk_id, "c2")

    def test_vector_store_json_serialization_roundtrip(self):
        """Task 5: Verify saving and loading vector records from JSON."""
        rec = EmbeddedChunk(
            chunk_id="test#01",
            content="Test content for persistence.",
            vector=[0.1234, -0.5678] + [0.0] * (DEFAULT_EMBEDDING_DIM - 2),
            vector_dim=DEFAULT_EMBEDDING_DIM,
            metadata={"source_id": "test_doc", "client_id": "TEST-001", "page": 1},
            model=DEFAULT_EMBEDDING_MODEL,
        )
        store = VectorStore([rec])

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "store.json"
            store.save_to_json(json_path)

            loaded_store = VectorStore.load_from_json(json_path)
            self.assertEqual(len(loaded_store), 1)
            loaded_rec = loaded_store.get("test#01")
            self.assertIsNotNone(loaded_rec)
            self.assertEqual(loaded_rec.content, "Test content for persistence.")
            self.assertEqual(loaded_rec.vector_dim, DEFAULT_EMBEDDING_DIM)
            self.assertEqual(loaded_rec.metadata["client_id"], "TEST-001")
            self.assertAlmostEqual(loaded_rec.vector[0], 0.1234, places=4)

    def test_end_to_end_pipeline_runner(self):
        """Task 4 & 5: Verify full pipeline outputs log and saves records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "output.log"
            rec_path = Path(tmp_dir) / "records.json"

            store, report = run_corpus_embedding_pipeline(
                output_log_file=log_path,
                output_records_file=rec_path,
                force_mock=True,
            )

            self.assertGreater(len(store), 0)
            self.assertTrue(log_path.exists())
            self.assertTrue(rec_path.exists())

            self.assertIn("Corpus Embedding Generation & Vector Storage Pipeline", report)
            self.assertIn("TASK 1 & 2: EMBEDDING GENERATION & METADATA STORAGE", report)
            self.assertIn("Total Chunks Embedded:", report)
            self.assertIn("1536 dimensions", report)
            self.assertIn("PASSED — All vectors match exact dimension", report)


if __name__ == "__main__":
    unittest.main()
