"""
Automated Unit Tests for Retrieval Text Cleaning and Normalization Pipeline
"""

import unittest
from src.document_loader import Document
from src.text_cleaner import (
    clean_text,
    clean_document,
    clean_corpus,
    normalize_unicode_and_encoding,
    remove_boilerplate,
    normalize_whitespace_and_wraps,
)


class TestTextCleaner(unittest.TestCase):
    def test_unicode_normalization(self):
        # Curly quotes, em-dashes, non-breaking spaces
        raw = "User\u2019s procedure \u201cSetup\u201d \u2014 step\u00a01."
        cleaned = normalize_unicode_and_encoding(raw)
        self.assertEqual(cleaned, "User's procedure \"Setup\"  -  step 1.")

    def test_boilerplate_removal(self):
        raw = (
            "[Home] > [Portal] > [Docs]\n"
            "Page 1 of 5 — CONFIDENTIAL\n"
            "This is actual runbook content.\n"
            "===============================\n"
            "Notice: Copyright 2026 ACME Corp."
        )
        cleaned, stripped_count = remove_boilerplate(raw)
        self.assertIn("This is actual runbook content.", cleaned)
        self.assertNotIn("Page 1 of 5", cleaned)
        self.assertNotIn("[Home]", cleaned)
        self.assertNotIn("Notice: Copyright", cleaned)
        self.assertGreaterEqual(stripped_count, 3)

    def test_whitespace_and_line_wrap_normalization(self):
        raw = (
            "This is a hyphen-\n"
            "ated line wrap that should be healed.\n\n\n\n\n"
            "And    runaway     spaces    collapsed.   \n\n\n"
        )
        cleaned = normalize_whitespace_and_wraps(raw)
        self.assertIn("hyphenated line wrap", cleaned)
        self.assertNotIn("runaway     spaces", cleaned)
        # Check runaway blank lines collapsed
        self.assertNotIn("\n\n\n", cleaned)

    def test_clean_document_preserves_identity_and_metadata(self):
        doc = Document(
            content="Page 1 of 2\nRunbook Content\n\n\nPage 2 of 2",
            source_id="test_doc",
            file_path="data/test_doc.txt",
            file_format="txt",
            char_count=45,
            metadata={"orig_key": "orig_val"},
        )

        cleaned_doc, metrics = clean_document(doc)
        self.assertEqual(cleaned_doc.source_id, "test_doc")
        self.assertEqual(cleaned_doc.file_path, "data/test_doc.txt")
        self.assertEqual(cleaned_doc.metadata["orig_key"], "orig_val")
        self.assertTrue(cleaned_doc.metadata["is_cleaned"])
        self.assertEqual(cleaned_doc.content, "Runbook Content")
        self.assertEqual(metrics.source_id, "test_doc")
        self.assertGreater(metrics.char_reduction, 0)

    def test_clean_corpus_uniformity(self):
        docs = [
            Document(content="Doc 1\nPage 1 of 1", source_id="d1", file_path="d1.txt", file_format="txt", char_count=17, metadata={}),
            Document(content="Doc 2\n[Home] > [Portal]", source_id="d2", file_path="d2.txt", file_format="txt", char_count=23, metadata={}),
        ]
        cleaned_docs, metrics = clean_corpus(docs)
        self.assertEqual(len(cleaned_docs), 2)
        self.assertEqual(cleaned_docs[0].content, "Doc 1")
        self.assertEqual(cleaned_docs[1].content, "Doc 2")


if __name__ == "__main__":
    unittest.main()
