"""Tests for source citation (src/source_citation.py)."""

import unittest
from pathlib import Path

from src.source_citation import (
    build_citation_map,
    inject_citations,
    verify_citations,
    build_cited_answer,
    INSUFFICIENT_EVIDENCE_INSTRUCTION,
)
from src.filtered_retriever import FilteredRetrievedChunk


def _stub(chunk_id, content, cid="T", did="d", sec="S1", p=1, score=0.85):
    return FilteredRetrievedChunk(
        rank=1, chunk_id=chunk_id, content=content,
        vector_score=score, keyword_score=score - 0.1, hybrid_score=score,
        matched_terms=[], matched_identifiers=[],
        source_document=did, document_id=did,
        chunk_index=0, section=sec, page=p,
        client_id=cid, token_count=50,
        metadata={"client_id": cid, "document_id": did},
    )


class TestBuildCitationMap(unittest.TestCase):
    def test_empty_chunks(self):
        m = build_citation_map([])
        self.assertEqual(m, {})

    def test_single_chunk(self):
        m = build_citation_map([_stub("doc#tok_000", "content", did="doc")])
        self.assertIn("[1]", m)
        self.assertEqual(m["[1]"].chunk_id, "doc#tok_000")
        self.assertEqual(m["[1]"].document_id, "doc")

    def test_multiple_chunks_get_stable_markers(self):
        chunks = [
            _stub("a#tok_000", "A", did="a"),
            _stub("b#tok_001", "B", did="b"),
        ]
        m = build_citation_map(chunks)
        self.assertEqual(m["[1]"].chunk_id, "a#tok_000")
        self.assertEqual(m["[2]"].chunk_id, "b#tok_001")

    def test_metadata_in_mapping(self):
        c = _stub("doc#tok_000", "text", cid="NEXUS-002", did="nexus_sla",
                  sec="Classifications", p=3, score=0.92)
        m = build_citation_map([c])
        s = m["[1]"]
        self.assertEqual(s.client_id, "NEXUS-002")
        self.assertEqual(s.section, "Classifications")
        self.assertEqual(s.page, 3)
        self.assertEqual(s.score, 0.92)


class TestInjectCitations(unittest.TestCase):
    def test_no_existing_markers_appends_appendix(self):
        m = build_citation_map([_stub("a#tok_000", "A", did="a")])
        result = inject_citations("Hello world.", m)
        self.assertIn("Hello world.", result)
        self.assertIn("[1]", result)
        self.assertIn("a#tok", result)

    def test_existing_markers_preserved(self):
        m = build_citation_map([
            _stub("a#tok_000", "A", did="a"),
            _stub("b#tok_001", "B", did="b"),
        ])
        result = inject_citations("See [2] for details.", m)
        self.assertIn("See [2] for details.", result)

    def test_fabricated_marker_warning(self):
        m = build_citation_map([_stub("a#tok_000", "A", did="a")])
        result = inject_citations("See [99] for details.", m)
        self.assertIn("[WARNING", result)
        self.assertIn("[99]", result)

    def test_empty_map_returns_original(self):
        result = inject_citations("Hello.", {})
        self.assertEqual(result, "Hello.")

    def test_appendix_lists_all_sources(self):
        chunks = [
            _stub("a#tok_000", "A", did="a", sec="Intro", p=1),
            _stub("b#tok_001", "B", did="b", sec="Body", p=5),
        ]
        m = build_citation_map(chunks)
        result = inject_citations("Answer.", m)
        self.assertIn("[1]", result)
        self.assertIn("[2]", result)
        self.assertIn("Intro", result)
        self.assertIn("Body", result)


class TestVerifyCitations(unittest.TestCase):
    def test_valid_markers(self):
        m = build_citation_map([_stub("a#tok_000", "A", did="a")])
        verifications, fake = verify_citations("See [1].", m)
        self.assertEqual(len(verifications), 1)
        self.assertTrue(verifications[0].exists_in_retrieved)
        self.assertTrue(verifications[0].matches_metadata)
        self.assertEqual(fake, [])

    def test_fabricated_marker_detected(self):
        m = build_citation_map([_stub("a#tok_000", "A", did="a")])
        verifications, fake = verify_citations("See [1] and [999].", m)
        self.assertEqual(len(verifications), 2)
        self.assertIn("[999]", fake)

    def test_no_markers(self):
        verifications, fake = verify_citations("No citations.", {})
        self.assertEqual(verifications, [])
        self.assertEqual(fake, [])


class TestBuildCitedAnswerIntegration(unittest.TestCase):
    def test_full_pipeline(self):
        result = build_cited_answer(
            query="What is the Sev-1 SLA?",
            client_id="NEXUS-002",
            k=3, force_mock=True,
        )
        self.assertFalse(result.insufficient_evidence)
        self.assertGreater(result.total_sources, 0)
        self.assertIn("[1]", result.answer)

    def test_empty_retrieval(self):
        result = build_cited_answer(
            query="nonexistent",
            client_id="DOESNOTEXIST",
            k=3, force_mock=True,
        )
        self.assertTrue(result.insufficient_evidence or result.total_sources == 0)

    def test_no_client_id(self):
        result = build_cited_answer(
            query="What is onboarding?",
            force_mock=True,
        )
        self.assertIsInstance(result.answer, str)

    def test_fabricated_none_in_clean_run(self):
        result = build_cited_answer(
            query="What is the Sev-1 SLA?",
            client_id="NEXUS-002",
            k=3, force_mock=True,
        )
        self.assertEqual(result.fabricated_markers_detected, [])

    def test_all_citations_verified(self):
        result = build_cited_answer(
            query="What is the Sev-1 SLA?",
            client_id="NEXUS-002",
            k=3, force_mock=True,
        )
        for v in result.verification_results:
            self.assertTrue(v.exists_in_retrieved,
                            f"{v.marker} should exist in retrieved chunks")


if __name__ == "__main__":
    unittest.main()
