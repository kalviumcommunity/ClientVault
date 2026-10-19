"""
Automated Unit Tests for Reusable Prompt Templates and Dynamic Injection
"""

import unittest
from pathlib import Path
from src.prompt_template import (
    PromptTemplate,
    TemplateRegistry,
    MissingPlaceholderError,
    render_support_chat_messages,
    render_batch_cli_audit_message,
)


class TestPromptTemplate(unittest.TestCase):
    def setUp(self):
        TemplateRegistry.clear_cache()

    def test_placeholder_extraction(self):
        tmpl_str = "Hello {name}, your ticket {ticket_id} for client {client_id} is ready."
        template = PromptTemplate(tmpl_str, name="ticket_notification")
        self.assertEqual(template.placeholders, {"name", "ticket_id", "client_id"})

    def test_successful_rendering(self):
        tmpl_str = "Client: {client_id}, Question: {question}"
        template = PromptTemplate(tmpl_str, name="query_prompt")
        rendered = template.render(client_id="ACME-001", question="How to rotate keys?")
        self.assertEqual(rendered, "Client: ACME-001, Question: How to rotate keys?")

    def test_missing_placeholder_strict_error(self):
        tmpl_str = "Client: {client_id}, Question: {question}, Context: {context}"
        template = PromptTemplate(tmpl_str, name="strict_prompt")
        with self.assertRaises(MissingPlaceholderError) as ctx:
            template.render(client_id="ACME-001", question="How to rotate keys?")
        self.assertIn("Missing required placeholder", str(ctx.exception))
        self.assertIn("context", str(ctx.exception))

    def test_load_template_from_file_and_caching(self):
        template = TemplateRegistry.get("user_retrieval")
        self.assertIn("context", template.placeholders)
        self.assertIn("question", template.placeholders)
        self.assertIn("client_id", template.placeholders)

        # Test caching identity
        template_again = TemplateRegistry.get("user_retrieval")
        self.assertIs(template, template_again)

    def test_feature1_support_chat_rendering(self):
        messages = render_support_chat_messages(
            client_id="ACME-001",
            clearance_level="Tier-1",
            document_id="KB-ONB-001",
            section="Section 3.2",
            page=4,
            context="Dual-operator approval mandatory.",
            question="What is the onboarding procedure?",
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("ACME-001", messages[0]["content"])
        self.assertIn("Tier-1", messages[0]["content"])
        self.assertIn("Dual-operator approval mandatory.", messages[1]["content"])
        self.assertIn("[Source: KB-ONB-001, Section: Section 3.2, Page: 4]", messages[1]["content"])

    def test_feature2_batch_cli_audit_rendering(self):
        msg = render_batch_cli_audit_message(
            client_id="NEXUS-002",
            batch_id="BATCH-001",
            document_id="SOP-01",
            context="Secret rotation required.",
            question="Was secret rotated?",
        )
        self.assertEqual(msg["role"], "user")
        self.assertIn("BATCH-001", msg["content"])
        self.assertIn("NEXUS-002", msg["content"])
        self.assertIn("SOP-01", msg["content"])


if __name__ == "__main__":
    unittest.main()
