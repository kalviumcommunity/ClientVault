"""Tests for conversational RAG (src/conversational_rag.py)."""

import unittest
from src.conversational_rag import (
    rewrite_followup,
    resolve_references,
    ConversationalRAG,
)


class TestRewriteFollowup(unittest.TestCase):
    def test_first_turn_no_history(self):
        r = rewrite_followup("What is the SLA?", force_mock=True)
        self.assertEqual(r.rewritten_query, "What is the SLA?")
        self.assertFalse(r.used_history)

    def test_followup_with_history_rewrites(self):
        history = [
            {"role": "user", "content": "What is the Sev-1 response time?"},
            {"role": "assistant", "content": "15 minutes."},
        ]
        r = rewrite_followup("What about the escalation contacts?",
                             history=history, force_mock=True)
        self.assertTrue(r.used_history)
        self.assertIn("escalation contacts", r.rewritten_query.lower())

    def test_empty_history(self):
        r = rewrite_followup("Hello?", force_mock=True)
        self.assertEqual(r.rewritten_query, "Hello?")
        self.assertFalse(r.used_history)


class TestResolveReferences(unittest.TestCase):
    def test_what_about_pattern(self):
        result = resolve_references(
            "What about the escalation contacts?",
            "What is the initial response time for a Severity 1 critical outage?"
        )
        self.assertIn("escalation contacts", result.lower())
        self.assertIn("severity", result.lower())

    def test_standalone_question_passes_through(self):
        result = resolve_references(
            "What is your name?",
            "What is the SLA?"
        )
        self.assertEqual(result, "What is your name?")


class TestConversationalRAGIntegration(unittest.TestCase):
    def test_turn_1_first_question(self):
        crag = ConversationalRAG(client_id="NEXUS-002", force_mock=True)
        turn = crag.ask("What is the Sev-1 response time?")
        self.assertEqual(turn.turn_number, 1)
        self.assertEqual(turn.original_question, "What is the Sev-1 response time?")
        self.assertFalse(turn.refusal)
        self.assertGreater(len(turn.retrieved_chunks), 0)

    def test_turn_2_followup_rewrites(self):
        crag = ConversationalRAG(client_id="NEXUS-002", force_mock=True)
        crag.ask("What is the Sev-1 response time?")
        turn2 = crag.ask("What about the escalation contacts?")
        self.assertEqual(turn2.turn_number, 2)
        self.assertIn("escalation", turn2.rewritten_query.lower())

    def test_empty_retrieval_refuses(self):
        crag = ConversationalRAG(client_id="DOESNOTEXIST", force_mock=True)
        turn = crag.ask("xyznonexistentquery")
        self.assertTrue(turn.refusal)

    def test_no_client_id(self):
        crag = ConversationalRAG(force_mock=True)
        turn = crag.ask("What is onboarding?")
        self.assertIsInstance(turn.answer, str)

    def test_history_tracking(self):
        crag = ConversationalRAG(force_mock=True)
        crag.ask("First question.")
        crag.ask("Second question.")
        conv = crag.get_conversation()
        self.assertEqual(len(conv.turns), 2)
        self.assertEqual(conv.turns[0].original_question, "First question.")
        self.assertEqual(conv.turns[1].original_question, "Second question.")


if __name__ == "__main__":
    unittest.main()
