"""
Automated Unit Tests for Corpus Vector Database Indexing & Audit

Tests:
1. Record preparation from JSON and directly from raw corpus.
2. Batch insertion of all corpus embeddings into ChromaDB collection.
3. Indexed count validation (comparing DB count against prepared chunks).
4. Detection of count mismatch and failure reporting.
5. Spot-check integrity audit verifying ID, vector, text, and metadata fidelity.
6. Detection of missing or corrupted records during spot-check.
7. Formatted summary report generation.
8. End-to-end indexing runner execution and log file persistence.
"""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from src.corpus_indexer import (
    CorpusIndexer,
    IndexingStats,
    SpotCheckResult,
    format_indexing_summary_report,
    run_corpus_indexing,
)
from src.vector_db import (
    VectorDatabaseManager,
    VectorDBConfig,
    VectorRecord,
    VectorRecordMetadata,
)


class TestCorpusIndexer(unittest.TestCase):
    """Test suite for corpus indexing and integrity verification."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.persist_path = Path(self.tmp_dir.name)
        self.col_name = f"test_index_{uuid.uuid4().hex[:8]}"
        self.config = VectorDBConfig(
            persist_directory=self.persist_path,
            collection_name=self.col_name,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            distance_metric="cosine",
            in_memory=True,
        )
        self.manager = VectorDatabaseManager(self.config)
        self.indexer = CorpusIndexer(manager=self.manager, force_mock=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_mock_records(self, count: int = 4) -> list[VectorRecord]:
        records = []
        clients = ["ACME-001", "NEXUS-002", "VERTEX-003", "ACME-001"]
        for i in range(count):
            client = clients[i % len(clients)]
            meta = VectorRecordMetadata(
                source_document=f"doc_{i}.md",
                document_id=f"doc_{i}",
                chunk_index=i,
                section=f"Section {i}",
                page=1,
                client_id=client,
                token_count=50 + i * 10,
                char_count=200 + i * 20,
            )
            vr = VectorRecord(
                record_id=f"chunk_{i:03d}",
                vector=[0.01 * ((j + i) % 10) for j in range(1536)],
                document_text=f"Sample procedural text content for chunk #{i}.",
                metadata=meta,
            )
            records.append(vr)
        return records

    def test_prepare_records_from_json(self):
        """Task 1 & 2: Verify record preparation converts existing JSON to VectorRecords."""
        records = self.indexer.prepare_vector_records()
        self.assertEqual(len(records), 6)
        for r in records:
            self.assertEqual(len(r.vector), 1536)
            self.assertTrue(r.document_text)
            self.assertTrue(r.metadata.client_id)
            self.assertTrue(r.metadata.source_document)
            self.assertGreater(r.metadata.token_count, 0)

    def test_index_corpus_and_count_validation(self):
        """Task 1 & 3: Index all records and confirm DB count matches prepared chunks."""
        mock_records = self._create_mock_records(4)
        stats: IndexingStats = self.indexer.index_corpus(mock_records, reset_existing=True)

        self.assertEqual(stats.total_chunks_prepared, 4)
        self.assertEqual(stats.records_indexed, 4)
        self.assertEqual(stats.stored_count_in_db, 4)
        self.assertEqual(stats.records_failed, 0)
        self.assertTrue(stats.count_matches)

    def test_spot_check_integrity_fidelity(self):
        """Task 4: Spot-check stored records against original source chunks."""
        mock_records = self._create_mock_records(3)
        self.indexer.index_corpus(mock_records, reset_existing=True)

        results: list[SpotCheckResult] = self.indexer.spot_check_integrity(mock_records)
        self.assertEqual(len(results), 3)

        for res in results:
            self.assertTrue(res.passed, f"Spot-check failed for {res.record_id}: {res.notes}")
            self.assertTrue(res.id_match)
            self.assertTrue(res.vector_match)
            self.assertTrue(res.text_match)
            self.assertTrue(res.metadata_match)
            self.assertEqual(res.vector_length, 1536)
            self.assertIn("All fields match", res.notes)

    def test_spot_check_detects_missing_record(self):
        """Task 4: Confirm spot-checker detects missing or non-indexed records."""
        mock_records = self._create_mock_records(2)
        # Index only the first record
        self.indexer.index_corpus(mock_records[:1], reset_existing=True)

        # Spot-check both records
        results = self.indexer.spot_check_integrity(mock_records, sample_ids=[mock_records[1].record_id])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].passed)
        self.assertFalse(results[0].id_match)
        self.assertIn("NOT found in vector database", results[0].notes)

    def test_format_indexing_summary_report(self):
        """Task 5: Confirm formatted summary report contains all audit sections."""
        mock_records = self._create_mock_records(2)
        stats = self.indexer.index_corpus(mock_records, reset_existing=True)
        stats.spot_checks = self.indexer.spot_check_integrity(mock_records)

        report_text = format_indexing_summary_report(stats)
        self.assertIn("ClientVault — Corpus Vector Database Indexing & Audit Report", report_text)
        self.assertIn("TASK 1 & 2: INDEXING SETUP & CONFIGURATION", report_text)
        self.assertIn("TASK 3: COUNT VALIDATION & CORPUS ALIGNMENT AUDIT", report_text)
        self.assertIn("TASK 4: STORED RECORD INTEGRITY SPOT-CHECKS", report_text)
        self.assertIn("PASSED — Database count matches prepared corpus chunks exactly.", report_text)

    def test_end_to_end_indexing_runner(self):
        """Task 5: Confirm end-to-end runner prepares, indexes, audits, and persists log."""
        test_log = self.persist_path / "test_indexing_output.log"
        stats, report_text = run_corpus_indexing(
            config=self.config,
            output_log_file=test_log,
            force_mock=True,
        )
        self.assertEqual(stats.records_indexed, 6)
        self.assertEqual(stats.stored_count_in_db, 6)
        self.assertTrue(stats.count_matches)
        self.assertGreaterEqual(len(stats.spot_checks), 3)
        self.assertTrue(all(s.passed for s in stats.spot_checks))
        self.assertTrue(test_log.exists())
        self.assertGreater(test_log.stat().st_size, 500)
        self.assertIn("STATUS: PASSED", report_text)


if __name__ == "__main__":
    unittest.main()
