"""
Unit tests for context injection and prompt augmentation (src/context_injector.py).
"""

import unittest
from pathlib import Path
from src.filtered_retriever import FilteredRetrievedChunk
from src.context_injector import (
    format_source_marker,
    assemble_context_budgeted,
    build_augmented_prompt,
    INSUFFICIENT_EVIDENCE_INSTRUCTION,
)


def _stub_chunk(chunk_id: str, content: str, client_id: str = "TEST-000",
                document_id: str = "test_doc", section: str = "S1",
                page: int = 1) -> FilteredRetrievedChunk:
    return FilteredRetrievedChunk(
        rank=1, chunk_id=chunk_id, content=content,
        vector_score=0.9, keyword_score=0.8, hybrid_score=0.85,
        matched_terms=[], matched_identifiers=[],
        source_document=document_id, document_id=document_id,
        chunk_index=0, section=section, page=page,
        client_id=client_id, token_count=50,
        metadata={"client_id": client_id},
    )


class TestFormatSourceMarker(unittest.TestCase):
    def test_basic_format(self):
        c = _stub_chunk("acme_onboarding#tok_000", "content")
        marker = format_source_marker(1, c)
        self.assertEqual(marker, "[1] acme_onboarding#tok_000")

    def test_multi_digit_index(self):
        c = _stub_chunk("doc#chunk_099", "content")
        marker = format_source_marker(42, c)
        self.assertEqual(marker, "[42] doc#chunk_099")

    def test_chunk_without_hash(self):
        c = _stub_chunk("simple_id", "content")
        marker = format_source_marker(1, c)
        self.assertIn("[1]", marker)


class TestAssembleContextBudgeted(unittest.TestCase):
    def test_empty_chunks_returns_insufficient(self):
        result = assemble_context_budgeted([], max_context_tokens=1000, reserve_tokens=200)
        self.assertTrue(result.insufficient_evidence)
        self.assertTrue(result.fully_empty)
        self.assertEqual(result.context_text, "")

    def test_single_chunk_fits(self):
        chunks = [_stub_chunk("doc#tok_000", "Hello world.")]
        result = assemble_context_budgeted(chunks, max_context_tokens=1000, reserve_tokens=200)
        self.assertFalse(result.insufficient_evidence)
        self.assertFalse(result.truncated)
        self.assertIn("Hello world.", result.context_text)
        self.assertEqual(len(result.sources_included), 1)
        self.assertEqual(len(result.sources_excluded), 0)

    def test_multiple_chunks_fit(self):
        chunks = [
            _stub_chunk("a#tok_000", "Chunk A", document_id="a"),
            _stub_chunk("b#tok_000", "Chunk B", document_id="b"),
        ]
        result = assemble_context_budgeted(chunks, max_context_tokens=2000, reserve_tokens=200)
        self.assertFalse(result.truncated)
        self.assertEqual(len(result.sources_included), 2)

    def test_truncation_when_over_budget(self):
        # Use very small budget to force truncation
        long_text = "word " * 200
        chunks = [
            _stub_chunk("a#tok_000", "Short chunk", document_id="a"),
            _stub_chunk("b#tok_001", long_text, document_id="b"),
            _stub_chunk("c#tok_002", "Another short", document_id="c"),
        ]
        result = assemble_context_budgeted(chunks, max_context_tokens=50, reserve_tokens=20)
        # At least one chunk should be excluded
        self.assertTrue(result.truncated or result.fully_empty)

    def test_negative_budget_reserves_nothing(self):
        chunks = [_stub_chunk("doc#tok_000", "Hello")]
        result = assemble_context_budgeted(chunks, max_context_tokens=10, reserve_tokens=100)
        # Reserve > max means nothing fits
        self.assertTrue(result.insufficient_evidence)

    def test_source_markers_in_context_text(self):
        chunks = [
            _stub_chunk("alpha#tok_000", "Content A", document_id="alpha"),
            _stub_chunk("beta#tok_001", "Content B", document_id="beta"),
        ]
        result = assemble_context_budgeted(chunks, max_context_tokens=2000, reserve_tokens=200)
        self.assertIn("[1] alpha#tok_000", result.context_text)
        self.assertIn("[2] beta#tok_001", result.context_text)


class TestBuildAugmentedPrompt(unittest.TestCase):
    def test_empty_context_includes_fallback(self):
        ctx = assemble_context_budgeted([], max_context_tokens=1000, reserve_tokens=200)
        prompt = build_augmented_prompt("test query", ctx, client_id="TEST-001")
        self.assertTrue(prompt.insufficient_evidence)
        self.assertIn(INSUFFICIENT_EVIDENCE_INSTRUCTION, prompt.full_prompt)

    def test_normal_context_in_sources(self):
        chunks = [_stub_chunk("doc#tok_000", "Relevant info.", client_id="ACME-001")]
        ctx = assemble_context_budgeted(chunks)
        prompt = build_augmented_prompt("What is the process?",
                                        ctx, client_id="ACME-001",
                                        document_id="doc", section="S1", page=1)
        self.assertFalse(prompt.insufficient_evidence)
        self.assertEqual(len(prompt.sources_included), 1)
        self.assertIn("Relevant info.", prompt.full_prompt)
        self.assertIn("[1] doc#tok_000", prompt.full_prompt)

    def test_context_token_count_reported(self):
        chunks = [_stub_chunk("doc#tok_000", "Token test content here.")]
        ctx = assemble_context_budgeted(chunks)
        prompt = build_augmented_prompt("query", ctx, client_id="T")
        self.assertGreater(prompt.context_token_count, 0)


if __name__ == "__main__":
    unittest.main()
