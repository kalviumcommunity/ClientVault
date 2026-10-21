"""Unit tests for Document Chunking Strategies and Evaluation Suite (src/chunker.py)."""

import unittest
from pathlib import Path
from src.chunker import (
    Chunk,
    FixedSizeChunker,
    ParagraphSemanticChunker,
    SentenceChunker,
    TokenAwareChunker,
    compute_chunk_stats,
    compare_strategies_on_document,
    count_tokens,
    demonstrate_boundary_context_preservation,
    get_model_budget_justification,
    trace_chunk_to_source,
)
from src.document_loader import Document, DocumentLoader


class TestChunker(unittest.TestCase):
    """Test suite for document chunking strategies."""

    def setUp(self):
        self.sample_text = (
            "# ACME Onboarding Guide\n"
            "This document details onboarding steps.\n\n"
            "## 1. Prerequisites\n"
            "Users must possess valid corporate credentials. Security clearance level 2 is required.\n\n"
            "## 2. Provisioning Steps\n"
            "Step 2.1: Verify user identity in Active Directory.\n"
            "Step 2.2: Obtain secondary sponsor sign-off.\n"
            "Step 2.3: Generate one-time activation token."
        )
        self.doc = Document(
            content=self.sample_text,
            source_id="test_doc",
            file_path="data/test_doc.md",
            file_format="md",
            char_count=len(self.sample_text),
            metadata={"client_id": "ACME"}
        )

    def test_fixed_size_chunking_bounds_and_overlap(self):
        """Test fixed-size chunker slices text and respects overlap."""
        chunk_size = 100
        chunk_overlap = 20
        chunker = FixedSizeChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = chunker.split_text(self.sample_text, document_id="doc1", source_id="test.md")

        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(c.char_count, chunk_size)
            self.assertIn("doc1", c.chunk_id)
            self.assertEqual(c.source_id, "test.md")
            self.assertGreater(c.token_count, 0)

        # Check overlap between first and second chunk
        c0 = chunks[0].content
        c1 = chunks[1].content
        # The end of c0 and start of c1 should share characters
        overlap_tail = c0[-chunk_overlap:]
        self.assertIn(overlap_tail, c1)

    def test_fixed_size_chunking_invalid_parameters(self):
        """Test invalid chunker parameters raise ValueError."""
        with self.assertRaises(ValueError):
            FixedSizeChunker(chunk_size=0)
        with self.assertRaises(ValueError):
            FixedSizeChunker(chunk_size=100, chunk_overlap=120)
        with self.assertRaises(ValueError):
            FixedSizeChunker(chunk_size=100, chunk_overlap=-5)

    def test_paragraph_semantic_chunking_preserves_headers(self):
        """Test paragraph chunker breaks cleanly on Markdown headers and preserves section titles."""
        chunker = ParagraphSemanticChunker(target_max_chars=180, min_chunk_chars=40)
        chunks = chunker.split_text(self.sample_text, document_id="doc_sem", source_id="sem.md")

        self.assertGreater(len(chunks), 1)
        sections = [c.section for c in chunks]
        # Should detect headings like 'ACME Onboarding Guide' or '1. Prerequisites'
        self.assertTrue(any("ACME" in s or "Prerequisites" in s for s in sections))
        for c in chunks:
            self.assertIn("sem.md", c.source_id)
            self.assertIn("doc_sem", c.chunk_id)

    def test_sentence_chunking_boundaries(self):
        """Test sentence chunker groups sentences and steps correctly."""
        chunker = SentenceChunker(sentences_per_chunk=2, sentence_overlap=1)
        chunks = chunker.split_text(self.sample_text, document_id="doc_sent", source_id="sent.md")

        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertGreater(c.char_count, 0)
            self.assertGreater(c.token_count, 0)

    def test_empty_text_returns_empty_list(self):
        """Test all chunkers handle empty string without throwing errors."""
        fixed = FixedSizeChunker().split_text("")
        para = ParagraphSemanticChunker().split_text("   \n\n  ")
        sent = SentenceChunker().split_text("")

        self.assertEqual(len(fixed), 0)
        self.assertEqual(len(para), 0)
        self.assertEqual(len(sent), 0)

    def test_compute_chunk_stats(self):
        """Test statistical aggregation calculation."""
        chunker = FixedSizeChunker(chunk_size=120, chunk_overlap=20)
        chunks = chunker.split_text(self.sample_text)
        stats = compute_chunk_stats("fixed_test", chunks)

        self.assertEqual(stats.total_chunks, len(chunks))
        self.assertGreater(stats.avg_chunk_chars, 0)
        self.assertGreater(stats.avg_chunk_tokens, 0)
        self.assertLessEqual(stats.min_chunk_chars, stats.max_chunk_chars)
        self.assertLessEqual(stats.min_chunk_tokens, stats.max_chunk_tokens)

    def test_compare_strategies_on_real_corpus_document(self):
        """Test multi-strategy comparison executes cleanly on sample corpus file."""
        loader = DocumentLoader()
        sample_path = Path("data/sample_corpus/acme_onboarding.md")
        if sample_path.exists():
            doc = loader.load_single_file(sample_path)
            self.assertIsNotNone(doc)
            comp = compare_strategies_on_document(doc)
            self.assertIn("fixed", comp)
            self.assertIn("paragraph_semantic", comp)
            self.assertIn("sentence", comp)
            self.assertGreater(comp["fixed"]["stats"].total_chunks, 0)
            self.assertGreater(comp["paragraph_semantic"]["stats"].total_chunks, 0)

    def test_chunk_metadata_schema_consistency(self):
        """Test all chunks receive complete and consistent metadata fields."""
        chunker = ParagraphSemanticChunker()
        chunks = chunker.split_document(self.doc)
        self.assertGreater(len(chunks), 0)

        for c in chunks:
            # Task 1: Store source identifier
            self.assertEqual(c.metadata.source_id, "test_doc")
            self.assertEqual(c.source_id, "test_doc")
            # Task 2: Attach additional metadata
            self.assertIsNotNone(c.metadata.section)
            self.assertGreaterEqual(c.metadata.page, 1)
            self.assertGreaterEqual(c.metadata.chunk_index, 0)
            self.assertEqual(c.metadata.total_chunks, len(chunks))
            self.assertGreaterEqual(c.metadata.start_char, 0)
            self.assertGreater(c.metadata.end_char, c.metadata.start_char)
            self.assertEqual(c.metadata.char_count, len(c.content))
            self.assertGreater(c.metadata.token_count, 0)
            self.assertEqual(c.metadata.file_path, "data/test_doc.md")
            self.assertEqual(c.metadata.file_format, "md")

            # Task 3: Consistent dictionary serialization
            d = c.to_dict()
            self.assertIn("chunk_id", d)
            self.assertIn("content", d)
            self.assertIn("metadata", d)
            m_dict = d["metadata"]
            for field_name in ["source_id", "document_id", "file_path", "section", "page", "chunk_index", "total_chunks", "start_char", "end_char", "char_count", "token_count"]:
                self.assertIn(field_name, m_dict)

    def test_trace_chunk_to_source_verification(self):
        """Task 4: Demonstrate that a retrieved chunk traces back to exact source text."""
        from src.chunker import trace_chunk_to_source
        chunker = ParagraphSemanticChunker()
        chunks = chunker.split_document(self.doc)
        target_chunk = chunks[1]  # Pick middle chunk

        trace = trace_chunk_to_source(target_chunk, self.sample_text)
        self.assertEqual(trace["source_id"], "test_doc")
        self.assertEqual(trace["file_path"], "data/test_doc.md")
        self.assertTrue(trace["is_contained_in_source"])
        self.assertTrue(trace["is_exact_span_match"])
        self.assertIn("Section:", trace["citation"])

    def test_token_aware_chunking_size_and_bounds(self):
        """Task 1: Test token-aware chunker sizes chunks strictly in tokens."""
        chunk_size_tokens = 30
        chunk_overlap_tokens = 5
        chunker = TokenAwareChunker(
            chunk_size_tokens=chunk_size_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
            model_encoding="cl100k_base"
        )
        chunks = chunker.split_text(self.sample_text, document_id="doc_tok", source_id="onb.md")

        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(c.token_count, chunk_size_tokens)
            self.assertIn("doc_tok", c.chunk_id)
            self.assertEqual(c.source_id, "onb.md")
            self.assertGreater(c.char_count, 0)
            self.assertEqual(c.strategy, "token_aware_overlap")

    def test_token_aware_chunking_invalid_parameters(self):
        """Task 1 & 2: Test invalid token parameters raise ValueError."""
        with self.assertRaises(ValueError):
            TokenAwareChunker(chunk_size_tokens=0)
        with self.assertRaises(ValueError):
            TokenAwareChunker(chunk_size_tokens=50, chunk_overlap_tokens=-1)
        with self.assertRaises(ValueError):
            TokenAwareChunker(chunk_size_tokens=50, chunk_overlap_tokens=60)
        with self.assertRaises(ValueError):
            TokenAwareChunker(chunk_size_tokens=50, chunk_overlap_tokens=50)

    def test_token_aware_controlled_overlap(self):
        """Task 2: Test adjacent chunks repeat exactly the last N tokens of the previous chunk."""
        chunk_size_tokens = 20
        chunk_overlap_tokens = 6
        chunker = TokenAwareChunker(
            chunk_size_tokens=chunk_size_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens
        )
        chunks = chunker.split_text(self.sample_text)
        self.assertGreater(len(chunks), 1)

        for i in range(len(chunks) - 1):
            toks_current = chunker.encode(chunks[i].content)
            toks_next = chunker.encode(chunks[i + 1].content)

            overlap_tail = toks_current[-chunk_overlap_tokens:]
            overlap_head = toks_next[:chunk_overlap_tokens]

            self.assertEqual(overlap_tail, overlap_head)
            decoded_tail = chunker.decode(overlap_tail)
            decoded_head = chunker.decode(overlap_head)
            self.assertEqual(decoded_tail, decoded_head)

    def test_token_aware_boundary_context_preservation(self):
        """Task 3: Demonstrate overlap preserves operational condition/action across chunk boundary."""
        demo = demonstrate_boundary_context_preservation(
            chunk_size_tokens=25,
            chunk_overlap_tokens=8
        )
        self.assertTrue(demo["without_overlap"]["condition_fractured"])
        self.assertTrue(demo["with_overlap"]["tokens_match_exactly"])
        self.assertTrue(demo["with_overlap"]["preserved_intact"])
        self.assertEqual(demo["with_overlap"]["shared_boundary_tokens"], 8)
        self.assertIn("exceeds 500ms for three consecutive", demo["with_overlap"]["shared_boundary_text"])

    def test_model_budget_justification_structure(self):
        """Task 4: Test architectural justification properties for target model."""
        just = get_model_budget_justification()
        self.assertEqual(just["target_model"], "gpt-4o-mini")
        self.assertEqual(just["context_window_tokens"], 128000)
        self.assertEqual(just["recommended_chunk_size_tokens"], 250)
        self.assertEqual(just["recommended_chunk_overlap_tokens"], 50)
        self.assertEqual(just["overlap_percentage"], 20.0)
        self.assertEqual(just["top_k_retrieval_chunks"], 5)
        self.assertLess(just["retrieved_context_tokens_budget"], 2000)
        self.assertGreaterEqual(len(just["justification_points"]), 4)

    def test_token_aware_traceability_and_metadata(self):
        """Task 5: Test token-aware chunks attach rich extra metadata and verify traceability."""
        chunker = TokenAwareChunker(chunk_size_tokens=35, chunk_overlap_tokens=10)
        chunks = chunker.split_document(self.doc)
        self.assertGreater(len(chunks), 0)

        c = chunks[0]
        self.assertIn("chunk_size_tokens", c.metadata.extra)
        self.assertIn("chunk_overlap_tokens", c.metadata.extra)
        self.assertIn("token_start_index", c.metadata.extra)
        self.assertIn("token_end_index", c.metadata.extra)

        trace = trace_chunk_to_source(c, self.sample_text)
        self.assertTrue(trace["is_exact_span_match"])
        self.assertTrue(trace["is_contained_in_source"])

    def test_token_aware_empty_text(self):
        """Test TokenAwareChunker returns empty list on empty or whitespace string."""
        chunker = TokenAwareChunker()
        self.assertEqual(chunker.split_text(""), [])
        self.assertEqual(chunker.split_text("   \n\n  "), [])


if __name__ == "__main__":
    unittest.main()
