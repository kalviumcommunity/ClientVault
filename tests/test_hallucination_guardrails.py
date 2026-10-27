"""Tests for hallucination guardrails (src/hallucination_guardrails.py)."""

import unittest
from src.filtered_retriever import FilteredRetrievedChunk
from src.hallucination_guardrails import (
    assess_retrieval,
    guarded_generate,
    REFUSAL_MESSAGE,
    DEFAULT_RELEVANCE_THRESHOLD,
    MIN_CHUNKS_ABOVE_THRESHOLD,
)


def _stub(chunk_id: str, score: float, did: str = "d", sec: str = "S1",
          p: int = 1, cid: str = "T") -> FilteredRetrievedChunk:
    return FilteredRetrievedChunk(
        rank=1, chunk_id=chunk_id, content="x",
        vector_score=score, keyword_score=score - 0.1, hybrid_score=score,
        matched_terms=[], matched_identifiers=[],
        source_document=did, document_id=did,
        chunk_index=0, section=sec, page=p,
        client_id=cid, token_count=10,
        metadata={"client_id": cid},
    )


class TestAssessRetrieval(unittest.TestCase):
    def test_empty_chunks_refuses(self):
        a = assess_retrieval([])
        self.assertFalse(a.passes_guard)
        self.assertIn("No chunks", a.refusal_reason)

    def test_high_scores_pass(self):
        chunks = [_stub("a#tok", 0.85), _stub("b#tok", 0.72)]
        a = assess_retrieval(chunks, threshold=0.60)
        self.assertTrue(a.passes_guard)
        self.assertIsNone(a.refusal_reason)
        self.assertEqual(a.chunks_above_threshold, 2)

    def test_low_scores_refuse(self):
        chunks = [_stub("a#tok", 0.45), _stub("b#tok", 0.32)]
        a = assess_retrieval(chunks, threshold=0.60)
        self.assertFalse(a.passes_guard)
        self.assertEqual(a.chunks_above_threshold, 0)

    def test_mixed_scores_partial(self):
        chunks = [_stub("a#tok", 0.85), _stub("b#tok", 0.35)]
        a = assess_retrieval(chunks, threshold=0.60)
        self.assertTrue(a.passes_guard)
        self.assertEqual(a.chunks_above_threshold, 1)

    def test_min_chunks_requirement(self):
        chunks = [_stub("a#tok", 0.85)]
        a = assess_retrieval(chunks, threshold=0.60, min_chunks=2)
        self.assertFalse(a.passes_guard)
        self.assertIn("Only 1/1 chunks", a.refusal_reason)

    def test_highest_lowest_scores(self):
        chunks = [_stub("a#tok", 0.95), _stub("b#tok", 0.45)]
        a = assess_retrieval(chunks, threshold=0.40)
        self.assertEqual(a.highest_score, 0.95)
        self.assertEqual(a.lowest_score, 0.45)

    def test_threshold_boundary_at_exact_value(self):
        chunks = [_stub("a#tok", 0.60)]
        a = assess_retrieval(chunks, threshold=0.60)
        self.assertTrue(a.passes_guard)


class TestGuardedGenerateIntegration(unittest.TestCase):
    def test_strong_context_passes(self):
        r = guarded_generate("Sev-1 SLA?", client_id="NEXUS-002",
                             threshold=0.50, force_mock=True)
        self.assertTrue(r.passed_guard)
        self.assertIsNone(r.refusal_reason)

    def test_empty_retrieval_refuses(self):
        r = guarded_generate("xyznonexistent", client_id="DOESNOTEXIST",
                             threshold=0.50, force_mock=True)
        self.assertFalse(r.passed_guard)
        self.assertEqual(r.answer, REFUSAL_MESSAGE)

    def test_refusal_has_no_generation(self):
        r = guarded_generate("non existent query here please",
                             threshold=0.99, force_mock=True)
        self.assertFalse(r.passed_guard)
        self.assertEqual(r.answer, REFUSAL_MESSAGE)

    def test_no_client_id(self):
        r = guarded_generate("What is the process?", force_mock=True)
        self.assertIsInstance(r.answer, str)

    def test_sources_included_in_result(self):
        r = guarded_generate("Sev-1 SLA?", client_id="NEXUS-002",
                             threshold=0.50, force_mock=True)
        self.assertGreater(len(r.sources), 0)

    def test_custom_threshold(self):
        r = guarded_generate("Sev-1 SLA?", client_id="NEXUS-002",
                             threshold=0.99, force_mock=True)
        # High threshold should refuse even with good chunks
        self.assertFalse(r.passed_guard)


if __name__ == "__main__":
    unittest.main()
