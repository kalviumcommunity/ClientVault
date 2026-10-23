"""
Automated Unit Tests for Vector Database Collection Setup & Record Persistence

Tests:
1. Environment configuration loading and default resolution.
2. Database reachability check (heartbeat, client status).
3. Collection creation with HNSW cosine space and 1536-dimensional sizing.
4. Record validation and dimension mismatch enforcement.
5. Record insert and readback verifying ID, vector length, text, and metadata fields.
6. Reading non-existent record handling.
7. Persistent disk storage lifecycle and reload recovery.
8. End-to-end demonstration runner and output log generation.
"""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from src.vector_db import (
    VectorDatabaseManager,
    VectorDBConfig,
    VectorRecord,
    VectorRecordMetadata,
    load_vector_db_config,
    run_vector_db_demonstration,
)


class TestVectorDatabase(unittest.TestCase):
    """Test suite for ChromaDB vector database manager and record operations."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.persist_path = Path(self.tmp_dir.name)
        self.col_name = f"test_clientvault_{uuid.uuid4().hex[:8]}"
        self.config = VectorDBConfig(
            persist_directory=self.persist_path,
            collection_name=self.col_name,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            distance_metric="cosine",
            in_memory=True,
        )
        self.manager = VectorDatabaseManager(self.config)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_sample_record(
        self,
        record_id: str = "rec_001",
        dimension: int = 1536,
        client_id: str = "ACME-001",
    ) -> VectorRecord:
        vector = [0.01 * (i % 10) for i in range(dimension)]
        meta = VectorRecordMetadata(
            source_document="acme_onboarding.md",
            document_id="acme_onboarding",
            chunk_index=1,
            section="Step 3.1: Sponsor Verification",
            page=2,
            client_id=client_id,
            token_count=85,
            char_count=320,
            extra_tag="unit_test_sample",
        )
        return VectorRecord(
            record_id=record_id,
            vector=vector,
            document_text="Before generating credentials, verify identity via the primary sponsor directory `SEC-ONB`.",
            metadata=meta,
        )

    def test_load_config_defaults(self):
        """Task 1: Verify config loading defaults and environment resolution."""
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = load_vector_db_config(env_path=Path("/non_existent_env_file"), in_memory=True)
            self.assertEqual(cfg.collection_name, "clientvault_knowledge_base")
            self.assertEqual(cfg.embedding_dimension, 1536)
            self.assertEqual(cfg.embedding_model, "text-embedding-3-small")
            self.assertEqual(cfg.distance_metric, "cosine")
            self.assertTrue(cfg.in_memory)

    def test_database_reachability(self):
        """Task 1: Confirm database reachability check returns healthy status."""
        health = self.manager.check_reachability()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertTrue(health["reachable"])
        self.assertIsNotNone(health.get("heartbeat_ns"))
        self.assertEqual(health["collection_name"], self.col_name)
        self.assertEqual(health["record_count"], 0)

    def test_collection_sizing_and_metadata(self):
        """Task 2: Confirm collection has correct vector dimension and cosine metric."""
        col = self.manager.collection
        self.assertEqual(col.name, self.col_name)
        self.assertIsNotNone(col.metadata)
        self.assertEqual(col.metadata.get("dimension"), 1536)
        self.assertEqual(col.metadata.get("hnsw:space"), "cosine")
        self.assertEqual(col.metadata.get("embedding_model"), "text-embedding-3-small")

    def test_record_validation_and_dimension_mismatch(self):
        """Task 2 & 3: Ensure invalid records and dimension mismatches are rejected."""
        # 1. Dimension mismatch
        wrong_dim_rec = self._create_sample_record(dimension=512)
        with self.assertRaises(ValueError) as ctx:
            self.manager.insert_record(wrong_dim_rec)
        self.assertIn("Vector dimension mismatch", str(ctx.exception))

        # 2. Empty record ID
        empty_id_rec = self._create_sample_record(record_id="")
        with self.assertRaises(ValueError) as ctx:
            self.manager.insert_record(empty_id_rec)
        self.assertIn("Record ID cannot be empty", str(ctx.exception))

        # 3. Missing client ID (PRD rule)
        missing_client_rec = self._create_sample_record(client_id="")
        with self.assertRaises(ValueError) as ctx:
            self.manager.insert_record(missing_client_rec)
        self.assertIn("missing required metadata: 'client_id'", str(ctx.exception))

    def test_insert_and_readback_exact_match(self):
        """Task 4: Insert test record and read back verifying ID, vector, text, and metadata."""
        sample_record = self._create_sample_record("acme_onboarding#tok_001")
        inserted_id = self.manager.insert_record(sample_record)
        self.assertEqual(inserted_id, "acme_onboarding#tok_001")

        # Verify collection count increased
        self.assertEqual(self.manager.count(), 1)

        # Read back
        readback = self.manager.read_record("acme_onboarding#tok_001")
        self.assertIsNotNone(readback)
        self.assertEqual(readback.record_id, "acme_onboarding#tok_001")
        self.assertEqual(len(readback.vector), 1536)
        self.assertEqual(readback.document_text, sample_record.document_text)

        # Verify metadata
        self.assertEqual(readback.metadata.source_document, "acme_onboarding.md")
        self.assertEqual(readback.metadata.document_id, "acme_onboarding")
        self.assertEqual(readback.metadata.chunk_index, 1)
        self.assertEqual(readback.metadata.section, "Step 3.1: Sponsor Verification")
        self.assertEqual(readback.metadata.page, 2)
        self.assertEqual(readback.metadata.client_id, "ACME-001")
        self.assertEqual(readback.metadata.token_count, 85)

        # Check preview serialization
        preview = readback.to_preview_dict()
        self.assertEqual(preview["record_id"], "acme_onboarding#tok_001")
        self.assertEqual(preview["vector_dimension"], 1536)
        self.assertEqual(len(preview["vector_sample"]["head"]), 5)
        self.assertEqual(len(preview["vector_sample"]["tail"]), 3)

    def test_read_nonexistent_record(self):
        """Task 4: Verify reading a non-existent ID gracefully returns None."""
        missing = self.manager.read_record("non_existent_id_999")
        self.assertIsNone(missing)

    def test_persistent_disk_reconnection(self):
        """Task 1 & 4: Verify persistent client saves to disk and reloads on reconnection."""
        disk_config = VectorDBConfig(
            persist_directory=self.persist_path / "chroma_test_db",
            collection_name="disk_collection",
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            distance_metric="cosine",
            in_memory=False,
        )
        # Session 1: Insert record
        manager_1 = VectorDatabaseManager(disk_config)
        rec = self._create_sample_record("disk_rec_001")
        manager_1.insert_record(rec)
        self.assertEqual(manager_1.count(), 1)

        # Session 2: Connect new manager instance to same directory
        manager_2 = VectorDatabaseManager(disk_config)
        self.assertEqual(manager_2.count(), 1)
        readback = manager_2.read_record("disk_rec_001")
        self.assertIsNotNone(readback)
        self.assertEqual(readback.record_id, "disk_rec_001")
        self.assertEqual(readback.metadata.client_id, "ACME-001")

    def test_end_to_end_demonstration_runner(self):
        """Task 5: Verify demonstration runner executes cleanly and saves log."""
        test_log_path = self.persist_path / "test_readback.log"
        record, summary, report_text = run_vector_db_demonstration(
            config=self.config,
            output_log_file=test_log_path,
            force_mock=True,
        )
        self.assertTrue(summary["all_checks_passed"])
        self.assertEqual(summary["dimension"], 1536)
        self.assertTrue(test_log_path.exists())
        self.assertGreater(test_log_path.stat().st_size, 500)
        self.assertIn("STATUS: PASSED", report_text)


if __name__ == "__main__":
    unittest.main()
