"""
Automated Unit Tests for ClientVault Chat Completion Client

Tests:
1. Environment configuration loading and fallback safety (Task 1)
2. Successful chat completion request execution and text extraction (Task 2)
3. Request and response payload logging & token usage extraction (Task 3)
4. Clean human-readable error reporting for HTTP 401 (auth) and 429 (rate limit) (Task 4)
5. Connection error handling when endpoint is unreachable (Task 4)
"""

import unittest
import threading
import os
from pathlib import Path
from unittest.mock import patch

from tests.mock_endpoint import start_mock_server
from src.chat_completion import (
    load_llm_config,
    create_client,
    send_chat_completion,
    setup_logging,
)


class TestChatCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure logging in test mode
        setup_logging(level="WARNING")

    def test_task1_load_config_from_env(self):
        """Verify Task 1: Client reads base_url, api_key, model from environment."""
        with patch.dict(os.environ, {
            "OPENAI_BASE_URL": "http://127.0.0.1:11434/v1",
            "OPENAI_API_KEY": "test-env-key-12345",
            "OPENAI_CHAT_MODEL": "llama3.2:latest",
        }):
            config = load_llm_config()
            self.assertEqual(config["base_url"], "http://127.0.0.1:11434/v1")
            self.assertEqual(config["api_key"], "test-env-key-12345")
            self.assertEqual(config["model"], "llama3.2:latest")

    def test_task2_and_task3_successful_call_and_payload_extraction(self):
        """Verify Task 2 & Task 3: 200 OK response with choices[0].message.content & token metrics."""
        server, base_url = start_mock_server(mode="success")
        t = threading.Thread(target=server.handle_request)
        t.start()

        try:
            config = {
                "base_url": base_url,
                "api_key": "mock-test-key",
                "model": "gpt-4o-mini",
                "is_local_endpoint": True,
            }
            messages = [
                {"role": "system", "content": "You are a helpful support assistant."},
                {"role": "user", "content": "How do I reset password for ACME-001?"},
            ]

            result = send_chat_completion(messages=messages, config=config)

            # Assertions for Task 2
            self.assertTrue(result["success"])
            self.assertIsNotNone(result["content"])
            self.assertIn("ClientVault Procedure Response", result["content"])
            self.assertIn("dual-operator verification", result["content"])

            # Assertions for Task 3
            self.assertIsNotNone(result["usage"])
            self.assertEqual(result["usage"]["prompt_tokens"], 42)
            self.assertEqual(result["usage"]["completion_tokens"], 36)
            self.assertEqual(result["usage"]["total_tokens"], 78)
            self.assertIsNone(result["error"])

        finally:
            server.server_close()
            t.join()

    def test_task4_handle_401_authentication_error(self):
        """Verify Task 4: Catch 401 auth error and return clear human-readable message."""
        server, base_url = start_mock_server(mode="auth_error")
        t = threading.Thread(target=server.handle_request)
        t.start()

        try:
            config = {
                "base_url": base_url,
                "api_key": "invalid-expired-key",
                "model": "gpt-4o-mini",
                "is_local_endpoint": True,
            }
            messages = [{"role": "user", "content": "Test auth failure"}]

            result = send_chat_completion(messages=messages, config=config)

            self.assertFalse(result["success"])
            self.assertIsNone(result["content"])
            self.assertEqual(result["error_type"], "AuthenticationError")
            self.assertIn("AUTHENTICATION FAILED (HTTP 401)", result["error"])
            self.assertIn("Check 'OPENAI_API_KEY' in your .env file", result["error"])

        finally:
            server.server_close()
            t.join()

    def test_task4_handle_429_rate_limit_error(self):
        """Verify Task 4: Catch 429 rate limit error and return clear human-readable message."""
        server, base_url = start_mock_server(mode="rate_limit")
        t = threading.Thread(target=server.handle_request)
        t.start()

        try:
            config = {
                "base_url": base_url,
                "api_key": "valid-key-over-quota",
                "model": "gpt-4o-mini",
                "is_local_endpoint": True,
            }
            client = create_client(base_url=base_url, api_key="valid-key-over-quota", max_retries=0)
            messages = [{"role": "user", "content": "Test rate limit failure"}]

            result = send_chat_completion(messages=messages, config=config, client=client)

            self.assertFalse(result["success"])
            self.assertIsNone(result["content"])
            self.assertEqual(result["error_type"], "RateLimitError")
            self.assertIn("RATE LIMIT EXCEEDED (HTTP 429)", result["error"])
            self.assertIn("Verify account quota/billing at your provider", result["error"])

        finally:
            server.server_close()
            t.join()

    def test_task4_handle_connection_error(self):
        """Verify Task 4: Catch APIConnectionError when endpoint is unreachable."""
        # Port 59999 is intentionally unreachable
        config = {
            "base_url": "http://127.0.0.1:59999/v1",
            "api_key": "any-key",
            "model": "gpt-4o-mini",
            "is_local_endpoint": True,
        }
        client = create_client(base_url=config["base_url"], api_key=config["api_key"], max_retries=0, timeout=1.0)
        messages = [{"role": "user", "content": "Test unreachable host"}]

        result = send_chat_completion(messages=messages, config=config, client=client)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "APIConnectionError")
        self.assertIn("CONNECTION ERROR", result["error"])


if __name__ == "__main__":
    unittest.main()
