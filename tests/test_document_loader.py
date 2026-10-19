"""
Automated Unit Tests for Multi-Format Document Loader and Intake Engine
"""

import tempfile
import unittest
from pathlib import Path
from src.document_loader import (
    DocumentLoader,
    extract_text_from_txt,
    extract_text_from_md,
    extract_text_from_html,
    Document,
)


class TestDocumentLoader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)
        self.loader = DocumentLoader(base_dir=self.dir_path)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_load_markdown_document(self):
        md_file = self.dir_path / "runbook.md"
        md_file.write_text("# Title\n\nSection 1 instructions.", encoding="utf-8")

        doc = self.loader.load_single_file(md_file)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.source_id, "runbook")
        self.assertEqual(doc.file_format, "md")
        self.assertIn("Section 1 instructions", doc.content)
        self.assertEqual(doc.char_count, len(doc.content))

    def test_load_txt_document(self):
        txt_file = self.dir_path / "sla.txt"
        txt_file.write_text("SLA Target: 99.9% uptime.", encoding="utf-8")

        doc = self.loader.load_single_file(txt_file)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.source_id, "sla")
        self.assertEqual(doc.file_format, "txt")
        self.assertIn("99.9%", doc.content)

    def test_load_html_document(self):
        html_file = self.dir_path / "portal.html"
        html_file.write_text(
            "<html><head><title>Test</title></head><body><h1>Header</h1><p>Procedure step.</p></body></html>",
            encoding="utf-8",
        )

        doc = self.loader.load_single_file(html_file)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.file_format, "html")
        self.assertIn("Header", doc.content)
        self.assertIn("Procedure step.", doc.content)
        self.assertNotIn("<h1>", doc.content)

    def test_missing_file_handled_gracefully(self):
        missing_file = self.dir_path / "does_not_exist.txt"
        doc = self.loader.load_single_file(missing_file)
        self.assertIsNone(doc)

    def test_unsupported_file_skipped_without_crash(self):
        unsupported = self.dir_path / "payload.exe"
        unsupported.write_bytes(b"\x00\x01\x02\x03")

        doc = self.loader.load_single_file(unsupported)
        self.assertIsNone(doc)

    def test_empty_file_skipped_without_crash(self):
        empty_file = self.dir_path / "empty.txt"
        empty_file.write_text("   \n\t  ", encoding="utf-8")

        doc = self.loader.load_single_file(empty_file)
        self.assertIsNone(doc)

    def test_directory_batch_intake(self):
        f1 = self.dir_path / "doc1.txt"
        f1.write_text("Document 1 content.", encoding="utf-8")
        f2 = self.dir_path / "doc2.md"
        f2.write_text("Document 2 content.", encoding="utf-8")
        f3 = self.dir_path / "invalid.bin"
        f3.write_bytes(b"bad binary")

        docs, skipped = self.loader.load_directory(self.dir_path)
        self.assertEqual(len(docs), 2)
        self.assertEqual(len(skipped), 1)
        self.assertIn("invalid.bin", skipped)


if __name__ == "__main__":
    unittest.main()
