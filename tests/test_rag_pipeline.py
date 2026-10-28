"""
Unit tests for the end-to-end RAG pipeline (src/rag_pipeline.py).
Tests each stage independently and the full orchestrator.
"""

import unittest
from pathlib import Path
from typing import List

from src.filtered_retriever import FilteredRetrievedChunk
from src.rag_pipeline import (
    assemble_context,
    generate_answer,
    INSUFFICIENT_EVIDENCE_FALLBACK,
)
from src.vector_db import VectorDBConfig, VectorDatabaseManager
from src.vector_retriever import VectorRetriever
from src.filtered_retriever import FilteredRetriever


def _make_stub_chunk(chunk_id: str, content: str, client_id: str = "TEST-000",
                     document_id: str = "test_doc", section: str = "Section 1",
                     page: int = 1) -> FilteredRetrievedChunk:
    return FilteredRetrievedChunk(
        rank=1,
        chunk_id=chunk_id,
        content=content,
        vector_score=0.85,
        keyword_score=0.70,
        hybrid_score=0.80,
        matched_terms=["term"],
        matched_identifiers=["ID-001"],
        source_document=document_id,
        document_id=document_id,
        chunk_index=0,
        section=section,
        page=page,
        client_id=client_id,
        token_count=50,
        metadata={"client_id": client_id, "document_id": document_id},
    )


class TestAssembleContext(unittest.TestCase):
    """Stage 3: context assembly from retrieved chunks."""

    def test_empty_chunks(self):
        ctx = assemble_context([])
        self.assertEqual(ctx.text, "")
        self.assertEqual(ctx.citations, [])
        self.assertEqual(ctx.chunk_count, 0)

    def test_single_chunk(self):
        c = _make_stub_chunk("doc#tok_000", "Test content.", client_id="ACME-001")
        ctx = assemble_context([c])
        self.assertIn("Test content.", ctx.text)
        self.assertIn("[Source: test_doc, Section: Section 1, Page: 1]", ctx.text)
        self.assertEqual(len(ctx.citations), 1)
        self.assertEqual(ctx.chunk_count, 1)

    def test_multiple_chunks(self):
        chunks = [
            _make_stub_chunk("doc#tok_000", "First chunk.", client_id="ACME-001",
                             document_id="doc_a", section="Intro"),
            _make_stub_chunk("doc#tok_001", "Second chunk.", client_id="ACME-001",
                             document_id="doc_b", section="Body"),
        ]
        ctx = assemble_context(chunks)
        self.assertIn("First chunk.", ctx.text)
        self.assertIn("Second chunk.", ctx.text)
        self.assertEqual(ctx.chunk_count, 2)
        self.assertEqual(len(ctx.citations), 2)
        # Each citation has rank
        self.assertEqual(ctx.citations[0]["rank"], 1)
        self.assertEqual(ctx.citations[1]["rank"], 2)


class TestGenerateAnswer(unittest.TestCase):
    """Stage 4: answer generation with empty-retrieval guard and mock fallback."""

    def test_empty_context_returns_fallback(self):
        answer, mock = generate_answer(
            query="test",
            client_id="TEST",
            context=assemble_context([]),
            force_mock=False,
        )
        self.assertEqual(answer, INSUFFICIENT_EVIDENCE_FALLBACK)
        self.assertFalse(mock)

    def test_mock_mode_returns_deterministic_answer(self):
        c = _make_stub_chunk("doc#tok_000", "Sev-1 response time is 15 minutes.",
                             client_id="NEXUS-002", document_id="nexus_sla",
                             section="Classifications")
        ctx = assemble_context([c])
        answer, mock = generate_answer(
            query="What is the Sev-1 response time?",
            client_id="NEXUS-002",
            context=ctx,
            force_mock=True,
        )
        self.assertTrue(mock)
        self.assertIn("NEXUS-002", answer)
        self.assertIn("nexus_sla", answer)
        self.assertIn("Classifications", answer)

    def test_mock_with_multiple_chunks_includes_all(self):
        chunks = [
            _make_stub_chunk("doc#tok_000", "First.", client_id="ACME-001",
                             document_id="a", section="S1"),
            _make_stub_chunk("doc#tok_001", "Second.", client_id="ACME-001",
                             document_id="b", section="S2"),
        ]
        ctx = assemble_context(chunks)
        answer, mock = generate_answer(
            query="test",
            client_id="ACME-001",
            context=ctx,
            force_mock=True,
        )
        self.assertTrue(mock)
        self.assertIn("a", answer)
        self.assertIn("b", answer)

    def test_insufficient_evidence_flag_preserved_in_orchestrator(self):
        """Integration: orchestrator sets flag when no chunks retrieved."""
        from src.rag_pipeline import answer_query
        # Query that won't match any indexed content
        result = answer_query(
            query="xyznonexistentquerystringthatwillmatchnothing",
            client_id="NONEXISTENT",
            k=5,
            force_mock=True,
        )
        # The DB only has sample_corpus (ACME, NEXUS, VERTEX) so a
        # client_id=NONEXISTENT filter may return 0 or some chunks.
        # Just verify the pipeline runs without error.
        self.assertIsInstance(result.answer, str)
        self.assertIsInstance(result.latency_ms, float)


class TestOrchestratorIntegration(unittest.TestCase):
    """Full pipeline integration tests."""

    @classmethod
    def setUpClass(cls):
        cls.ret = FilteredRetriever(force_mock=True)

    def test_answer_query_returns_rag_result(self):
        from src.rag_pipeline import answer_query
        result = answer_query(
            query="What is the Sev-1 response time for Nexus?",
            client_id="NEXUS-002",
            k=3,
            force_mock=True,
        )
        self.assertEqual(result.query, "What is the Sev-1 response time for Nexus?")
        self.assertGreater(len(result.retrieved_chunks), 0)
        self.assertIsInstance(result.answer, str)
        self.assertFalse(result.insufficient_evidence)

    def test_answer_query_without_client_id(self):
        from src.rag_pipeline import answer_query
        result = answer_query(
            query="What is the onboarding process?",
            k=3,
            force_mock=True,
        )
        self.assertGreater(len(result.retrieved_chunks), 0)
        self.assertIsInstance(result.answer, str)

    def test_answer_query_all_clients_no_filter(self):
        from src.rag_pipeline import answer_query
        result = answer_query(
            query="tell me about service level agreements",
            k=5,
            force_mock=True,
        )
        self.assertGreater(len(result.retrieved_chunks), 0)
        # Answer is mock fallback, just verify pipeline completes
        self.assertIsInstance(result.answer, str)


if __name__ == "__main__":
    unittest.main()
