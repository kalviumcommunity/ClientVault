"""Unit tests for Full Corpus Ingestion Pipeline & Completeness Validation (src/ingestion_pipeline.py)."""

import unittest
from pathlib import Path
from src.ingestion_pipeline import IngestionPipeline, IngestionRunResult, format_ingestion_summary


class TestIngestionPipeline(unittest.TestCase):
    """Test suite for full corpus ingestion pipeline and completeness reconciliation."""

    @classmethod
    def setUpClass(cls):
        cls.corpus_dir = Path("data/corpus")
        cls.pipeline = IngestionPipeline(
            chunk_size_tokens=250,
            chunk_overlap_tokens=50,
            model_encoding="cl100k_base"
        )
        cls.result = cls.pipeline.run(cls.corpus_dir)

    def test_task1_full_pipeline_ingestion_counts(self):
        """Task 1: Verify full pipeline processes all files in corpus directory."""
        self.assertEqual(self.result.total_source_files, 17)
        self.assertEqual(self.result.ingested_documents_count, 15)
        self.assertEqual(len(self.result.skipped_files), 2)
        self.assertGreater(self.result.total_chunks_created, 20)
        self.assertGreater(self.result.total_corpus_characters, 15000)
        self.assertGreater(self.result.total_corpus_tokens, 3500)

    def test_task2_client_and_format_breakdown(self):
        """Task 2: Verify ingestion summary accounts for all 3 clients and document formats."""
        # 3 clients x 5 docs
        clients = self.result.client_breakdown
        self.assertIn("ACME-001", clients)
        self.assertIn("NEXUS-002", clients)
        self.assertIn("VERTEX-003", clients)

        self.assertEqual(clients["ACME-001"]["documents"], 5)
        self.assertEqual(clients["NEXUS-002"]["documents"], 5)
        self.assertEqual(clients["VERTEX-003"]["documents"], 5)

        self.assertGreater(clients["ACME-001"]["chunks"], 0)
        self.assertGreater(clients["NEXUS-002"]["chunks"], 0)
        self.assertGreater(clients["VERTEX-003"]["chunks"], 0)

        formats = self.result.format_breakdown
        self.assertIn("md", formats)
        self.assertIn("txt", formats)
        self.assertIn("html", formats)
        self.assertEqual(sum(formats.values()), 15)

    def test_task3_completeness_reconciliation_math(self):
        """Task 3: Validate mathematical reconciliation proving no silent drops."""
        # Total Source Files == Ingested Documents + Recorded Failures
        reconciled_sum = self.result.ingested_documents_count + len(self.result.skipped_files)
        self.assertEqual(self.result.total_source_files, reconciled_sum)
        self.assertEqual(self.result.unaccounted_files_count, 0)
        self.assertTrue(self.result.is_reconciled)
        self.assertTrue(self.result.validation_passed)
        self.assertEqual(len(self.result.validation_errors), 0)

    def test_task3_skipped_file_records_clarity(self):
        """Task 3: Ensure skipped files contain explicit filenames, paths, and reasons."""
        skipped_names = {s.filename for s in self.result.skipped_files}
        self.assertIn("corrupt_unsupported.bin", skipped_names)
        self.assertIn("empty_draft_memo.txt", skipped_names)

        for s in self.result.skipped_files:
            self.assertGreater(len(s.reason), 10)
            self.assertIn(s.filename, s.file_path)
            if s.filename.endswith(".bin"):
                self.assertIn("UNSUPPORTED_FORMAT", s.reason)
            elif s.filename.startswith("empty_"):
                self.assertIn("EMPTY_FILE", s.reason)

    def test_task4_sample_chunks_inspection(self):
        """Task 4: Inspect sample chunks for metadata tagging, cleaned text, and boundaries."""
        samples = self.result.sample_chunks
        self.assertGreaterEqual(len(samples), 3)

        client_tags = {s["client_id"] for s in samples}
        # Should have representatives across clients
        self.assertGreaterEqual(len(client_tags), 2)

        for sc in samples:
            self.assertIn("chunk_id", sc)
            self.assertIn("source_id", sc)
            self.assertIn("client_id", sc)
            self.assertIn("document_code", sc)
            self.assertIn("section", sc)
            self.assertIn("page", sc)
            self.assertIn("char_span", sc)
            self.assertIn("citation", sc)
            self.assertIn("content_preview", sc)
            self.assertGreater(sc["token_count"], 0)
            self.assertGreater(sc["char_count"], 0)
            self.assertIn("[Source:", sc["citation"])

    def test_chunk_metadata_integrity_across_corpus(self):
        """Verify that 100% of generated chunks possess valid fields and provenance."""
        for c in self.result.chunks:
            self.assertTrue(c.content.strip())
            self.assertGreater(c.metadata.token_count, 0)
            self.assertGreater(c.metadata.char_count, 0)
            self.assertTrue(c.metadata.source_id)
            self.assertTrue(c.metadata.section)
            self.assertGreaterEqual(c.metadata.page, 1)
            self.assertGreaterEqual(c.metadata.chunk_index, 0)
            self.assertEqual(c.metadata.total_chunks, len([
                chk for chk in self.result.chunks
                if chk.metadata.source_id == c.metadata.source_id
            ]))

    def test_unaccounted_drop_detection(self):
        """Verify that if a file is unaccounted for, validation fails immediately."""
        tampered_result = IngestionRunResult(
            corpus_directory="mock_dir",
            total_source_files=10,
            ingested_documents_count=8,
            total_chunks_created=16,
            total_corpus_characters=10000,
            total_corpus_tokens=2500,
            skipped_files=[],  # 0 skipped recorded, but 10 != 8 + 0
            client_breakdown={},
            format_breakdown={},
            is_reconciled=False,
            unaccounted_files_count=2,
            validation_passed=False,
            validation_errors=["Reconciliation Mismatch: 10 != 8 + 0 [Discrepancy: 2]"],
            sample_chunks=[],
        )
        self.assertFalse(tampered_result.is_reconciled)
        self.assertFalse(tampered_result.validation_passed)
        self.assertEqual(tampered_result.unaccounted_files_count, 2)

    def test_format_ingestion_summary_text(self):
        """Task 5: Test that formatted summary report contains all audit sections."""
        summary = format_ingestion_summary(self.result)
        self.assertIn("CLIENTVAULT — FULL CORPUS INGESTION RUN", summary)
        self.assertIn("TASK 2 — INGESTION BREAKDOWN BY CLIENT ACCOUNT", summary)
        self.assertIn("TASK 3 — COMPLETENESS VALIDATION & RECONCILIATION AUDIT", summary)
        self.assertIn("TASK 4 — SAMPLE CHUNKS INSPECTION", summary)
        self.assertIn("Mathematical Reconciliation : PASSED", summary)
        self.assertIn("100% VERIFIED", summary)


if __name__ == "__main__":
    unittest.main()
