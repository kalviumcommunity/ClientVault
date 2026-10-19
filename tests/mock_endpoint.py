"""
Mock OpenAI-Compatible HTTP Server for Local Testing & Verification

Provides a lightweight, zero-dependency HTTP server adhering to the
OpenAI /v1/chat/completions specification. Supports simulating:
- 200 OK (Standard chat completion with choices and token usage)
- 401 Unauthorized (Invalid API Key)
- 429 Too Many Requests (Rate limit / Quota exceeded)
"""

import http.server
import json
import time
import socket
from typing import Optional, Tuple


class MockOpenAIHandler(http.server.BaseHTTPRequestHandler):
    mode: str = "success"  # "success", "auth_error", "rate_limit"

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(content_len) if content_len > 0 else b""

        # Check path
        if not self.path.endswith("/chat/completions"):
            self.send_error(404, "Endpoint Not Found")
            return

        # Route simulation mode
        if self.mode == "auth_error":
            self._respond_401()
        elif self.mode == "rate_limit":
            self._respond_429()
        else:
            self._respond_200(body_raw)

    def _respond_200(self, body_raw: bytes):
        try:
            req_data = json.loads(body_raw.decode("utf-8")) if body_raw else {}
        except Exception:
            req_data = {}

        model = req_data.get("model", "gpt-4o-mini")
        messages = req_data.get("messages", [])
        last_user_msg = "Hello"
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        reply_content = (
            f"ClientVault Procedure Response: Received inquiry '{last_user_msg}'. "
            "Verified against approved client runbook KB-ONB-001 (Section 3.2, Page 4). "
            "All onboarding credentials require dual-operator verification."
        )

        response_payload = {
            "id": f"chatcmpl-mock-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply_content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 42,
                "completion_tokens": 36,
                "total_tokens": 78,
            },
        }

        res_bytes = json.dumps(response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(res_bytes)))
        self.end_headers()
        self.wfile.write(res_bytes)

    def _respond_401(self):
        error_payload = {
            "error": {
                "message": "Incorrect API key provided. You can find your API key at https://platform.openai.com/account/api-keys.",
                "type": "invalid_request_error",
                "param": None,
                "code": "invalid_api_key",
            }
        }
        res_bytes = json.dumps(error_payload).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(res_bytes)))
        self.end_headers()
        self.wfile.write(res_bytes)

    def _respond_429(self):
        error_payload = {
            "error": {
                "message": "You exceeded your current quota, please check your plan and billing details.",
                "type": "insufficient_quota",
                "param": None,
                "code": "insufficient_quota",
            }
        }
        res_bytes = json.dumps(error_payload).encode("utf-8")
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(res_bytes)))
        self.end_headers()
        self.wfile.write(res_bytes)

    def log_message(self, format, *args):
        # Silence default stderr logging to keep test output clean
        pass


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_mock_server(mode: str = "success") -> Tuple[http.server.HTTPServer, str]:
    """Starts a local mock OpenAI server and returns (server, base_url)."""
    port = find_free_port()
    MockOpenAIHandler.mode = mode
    server = http.server.HTTPServer(("127.0.0.1", port), MockOpenAIHandler)
    base_url = f"http://127.0.0.1:{port}/v1"
    return server, base_url
