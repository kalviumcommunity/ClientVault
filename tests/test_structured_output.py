"""
Automated Unit Tests for Structured Output Parsing and Schema Validation
"""

import json
import unittest
from src.structured_output import (
    extract_and_repair_json,
    validate_structured_payload,
    process_model_json_output,
    AssistantStructuredResponse,
)


class TestStructuredOutput(unittest.TestCase):
    def test_clean_json_parsing(self):
        raw = json.dumps({
            "client_id": "ACME-001",
            "answer": "Perform identity check via verified domain.",
            "source": {
                "document_id": "KB-ONB-001",
                "section": "Section 3.2",
                "page": 4
            },
            "confidence": 0.99,
            "status": "VERIFIED"
        })
        data, err, was_repaired = extract_and_repair_json(raw)
        self.assertIsNone(err)
        self.assertFalse(was_repaired)
        self.assertEqual(data["client_id"], "ACME-001")

        is_valid, validated, val_errors = validate_structured_payload(data)
        self.assertTrue(is_valid)
        self.assertEqual(len(val_errors), 0)
        self.assertIsInstance(validated, AssistantStructuredResponse)
        self.assertEqual(validated.source.document_id, "KB-ONB-001")

    def test_markdown_fence_repair(self):
        raw = "```json\n{\"client_id\": \"NEXUS-002\", \"answer\": \"Check runbook.\", \"source\": {\"document_id\": \"KB-RUN-01\", \"section\": \"1.0\"}, \"confidence\": 0.9}\n```"
        data, err, was_repaired = extract_and_repair_json(raw)
        self.assertIsNone(err)
        self.assertTrue(was_repaired)
        self.assertEqual(data["client_id"], "NEXUS-002")

    def test_trailing_comma_repair(self):
        raw = "{\n  \"client_id\": \"TEST-01\",\n  \"answer\": \"Step 1\",\n  \"source\": {\"document_id\": \"DOC-1\", \"section\": \"Sec 1\",},\n  \"confidence\": 0.85,\n}"
        data, err, was_repaired = extract_and_repair_json(raw)
        self.assertIsNone(err)
        self.assertTrue(was_repaired)
        self.assertEqual(data["source"]["document_id"], "DOC-1")

    def test_missing_required_fields_rejected_and_recovered(self):
        # Missing source and confidence
        raw = json.dumps({
            "client_id": "ACME-001",
            "answer": "Unverified procedure with no citation."
        })
        result = process_model_json_output(raw, allow_recovery=True)
        self.assertFalse(result["success"])
        self.assertTrue(result["recovered"])
        self.assertIn("Missing required field", result["error"])
        # Should return safe fallback
        self.assertEqual(result["data"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["data"]["confidence"], 0.0)

    def test_corrupted_json_handled_without_crash(self):
        raw = "<<<UNPARSEABLE GARBAGE TEXT>>>"
        result = process_model_json_output(raw, allow_recovery=True)
        self.assertFalse(result["success"])
        self.assertTrue(result["recovered"])
        self.assertIn("JSON Parse Failure", result["error"])
        self.assertEqual(result["data"]["status"], "INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
