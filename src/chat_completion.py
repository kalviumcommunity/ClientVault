"""
ClientVault — Single Chat Completion Client with Logging and Resilient Error Handling

This module provides a production-grade chat completion runner for OpenAI-compatible
APIs (e.g., OpenAI, Ollama, vLLM, LocalAI) satisfying:
- Task 1: Environment-driven configuration (.env, never hard-coded credentials)
- Task 2: Request execution and response output (choices[0].message.content)
- Task 3: Comprehensive payload logging (outgoing messages, incoming reply, token usage)
- Task 4: Explicit, human-readable error handling for 401 (auth) and 429 (rate limits)
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import argparse

from dotenv import load_dotenv
import openai
from openai import (
    OpenAI,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    APIStatusError,
    OpenAIError,
)

# Project paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = ROOT_DIR / ".env"
DEFAULT_PROMPT_PATH = ROOT_DIR / "prompts" / "system_prompt.txt"

# Configure logger
logger = logging.getLogger("ClientVault.ChatCompletion")


def setup_logging(level: str = "INFO", log_file: Optional[Path] = None) -> logging.Logger:
    """Configures structured console and optional file logging."""
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional File Handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def load_llm_config(env_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Task 1: Load client configuration strictly from environment variables or .env file.
    Never hard-codes URLs, keys, or model identifiers.
    """
    target_env = env_path or DEFAULT_ENV_PATH
    if target_env.exists():
        load_dotenv(dotenv_path=target_env, override=False)
        logger.debug("Loaded configuration from %s", target_env)
    else:
        logger.debug("No .env file found at %s (using system environment variables)", target_env)

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini").strip()

    # For local OpenAI-compatible endpoints (Ollama, LocalAI, mock servers),
    # an empty API key is often allowed by the server, but the OpenAI SDK requires
    # a non-empty string. Fallback safely if pointing to localhost/127.0.0.1.
    is_local_endpoint = "localhost" in base_url or "127.0.0.1" in base_url
    if not api_key and is_local_endpoint:
        api_key = "local-endpoint-dummy-key"

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "is_local_endpoint": is_local_endpoint,
    }


def create_client(base_url: str, api_key: str, max_retries: int = 1, timeout: float = 30.0) -> OpenAI:
    """Instantiate and configure the OpenAI-compatible client."""
    return OpenAI(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        max_retries=max_retries,
        timeout=timeout,
    )


def load_default_system_prompt() -> str:
    """Load default grounding system prompt from prompts/system_prompt.txt if available."""
    if DEFAULT_PROMPT_PATH.exists():
        try:
            return DEFAULT_PROMPT_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return (
        "You are the Client Support Knowledge Assistant. "
        "Retrieve and explain client-specific operational procedures strictly based on provided evidence."
    )


def log_request_payload(model: str, messages: List[Dict[str, str]], base_url: str) -> None:
    """Task 3: Log outgoing request messages and target endpoint safely."""
    logger.info("---------- OUTGOING LLM REQUEST ----------")
    logger.info("Target Endpoint: %s", base_url)
    logger.info("Selected Model:  %s", model)
    logger.info("Messages Payload:\n%s", json.dumps(messages, indent=2))
    logger.info("------------------------------------------")


def log_response_payload(response: Any) -> None:
    """Task 3: Log incoming response payload and token usage."""
    logger.info("---------- INCOMING LLM RESPONSE ----------")
    logger.info("Response ID:     %s", getattr(response, "id", "N/A"))
    logger.info("Reported Model:  %s", getattr(response, "model", "N/A"))

    choice = response.choices[0] if response.choices else None
    if choice:
        logger.info("Finish Reason:   %s", getattr(choice, "finish_reason", "unknown"))
        logger.info("Role:            %s", getattr(choice.message, "role", "assistant"))
        logger.info("Response Content:\n%s", getattr(choice.message, "content", ""))

    usage = getattr(response, "usage", None)
    if usage:
        logger.info("Token Usage:")
        logger.info("  Prompt Tokens:     %d", getattr(usage, "prompt_tokens", 0))
        logger.info("  Completion Tokens: %d", getattr(usage, "completion_tokens", 0))
        logger.info("  Total Tokens:      %d", getattr(usage, "total_tokens", 0))
    else:
        logger.info("Token Usage: N/A (usage metrics not reported by endpoint)")
    logger.info("-------------------------------------------")


def send_chat_completion(
    messages: List[Dict[str, str]],
    config: Optional[Dict[str, Any]] = None,
    client: Optional[OpenAI] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    stop: Optional[List[str]] = None,
    top_p: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Executes a chat completion call against the configured OpenAI-compatible API.

    Returns a structured dictionary:
    {
        "success": bool,
        "content": Optional[str],
        "usage": Optional[Dict[str, int]],
        "model": str,
        "error": Optional[str],
        "error_type": Optional[str]
    }
    """
    cfg = config or load_llm_config()
    base_url = cfg["base_url"]
    api_key = cfg["api_key"]
    model = cfg["model"]

    # Pre-flight check for missing API key on external OpenAI endpoint
    if not api_key and not cfg.get("is_local_endpoint"):
        msg = (
            "Authentication Error (Missing API Key): OPENAI_API_KEY is not configured in .env. "
            "Please add your API key or configure a local endpoint (such as Ollama or mock server)."
        )
        logger.error(msg)
        return {
            "success": False,
            "content": None,
            "usage": None,
            "model": model,
            "error": msg,
            "error_type": "AuthenticationError",
        }

    # Initialize client if not provided
    active_client = client or create_client(base_url=base_url, api_key=api_key)

    # Task 3: Log outgoing request payload
    log_request_payload(model=model, messages=messages, base_url=base_url)

    # Build kwargs
    call_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        call_kwargs["max_tokens"] = max_tokens
    if stop is not None:
        call_kwargs["stop"] = stop
    if top_p is not None:
        call_kwargs["top_p"] = top_p

    try:
        # Task 2: Send request
        response = active_client.chat.completions.create(**call_kwargs)


        # Task 3: Log incoming response payload
        log_response_payload(response)

        # Task 2: Extract model text reply
        content = ""
        if response.choices and response.choices[0].message:
            content = response.choices[0].message.content or ""

        usage_dict = None
        if getattr(response, "usage", None):
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return {
            "success": True,
            "content": content,
            "usage": usage_dict,
            "model": getattr(response, "model", model),
            "error": None,
            "error_type": None,
        }

    # Task 4: Catch and report common failures with human-readable messages
    except AuthenticationError as e:
        error_msg = (
            f"[AUTHENTICATION FAILED (HTTP 401)] The provided API key is invalid or unauthorized.\n"
            f"  Server Message: {e.message}\n"
            f"  Action Required: Check 'OPENAI_API_KEY' in your .env file and ensure it is valid."
        )
        logger.error(error_msg)
        return {
            "success": False,
            "content": None,
            "usage": None,
            "model": model,
            "error": error_msg,
            "error_type": "AuthenticationError",
        }

    except RateLimitError as e:
        error_msg = (
            f"[RATE LIMIT EXCEEDED (HTTP 429)] Request limit or account quota has been exceeded.\n"
            f"  Server Message: {e.message}\n"
            f"  Action Required: Verify account quota/billing at your provider or back off and retry later."
        )
        logger.error(error_msg)
        return {
            "success": False,
            "content": None,
            "usage": None,
            "model": model,
            "error": error_msg,
            "error_type": "RateLimitError",
        }

    except APIConnectionError as e:
        error_msg = (
            f"[CONNECTION ERROR] Failed to establish connection to endpoint '{base_url}'.\n"
            f"  Details: {e.message}\n"
            f"  Action Required: Check internet connectivity or verify local LLM server (e.g. Ollama) is active."
        )
        logger.error(error_msg)
        return {
            "success": False,
            "content": None,
            "usage": None,
            "model": model,
            "error": error_msg,
            "error_type": "APIConnectionError",
        }

    except APIStatusError as e:
        error_msg = (
            f"[API ERROR (HTTP {e.status_code})] The server responded with an error status.\n"
            f"  Details: {e.message}\n"
            f"  Action Required: Review request parameters or endpoint documentation."
        )
        logger.error(error_msg)
        return {
            "success": False,
            "content": None,
            "usage": None,
            "model": model,
            "error": error_msg,
            "error_type": "APIStatusError",
        }

    except OpenAIError as e:
        error_msg = (
            f"[OPENAI SDK ERROR] An unexpected client error occurred.\n"
            f"  Details: {str(e)}"
        )
        logger.error(error_msg)
        return {
            "success": False,
            "content": None,
            "usage": None,
            "model": model,
            "error": error_msg,
            "error_type": "OpenAIError",
        }

    except Exception as e:
        error_msg = f"[UNEXPECTED ERROR] {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "content": None,
            "usage": None,
            "model": model,
            "error": error_msg,
            "error_type": "UnexpectedError",
        }


def run_standalone(
    user_prompt: str = "Explain the standard client onboarding verification procedure.",
    system_prompt: Optional[str] = None,
    env_path: Optional[Path] = None,
    log_file: Optional[Path] = None,
) -> int:
    """Executes the standard workflow and prints the model's text reply."""
    setup_logging(level="INFO", log_file=log_file)
    config = load_llm_config(env_path=env_path)

    sys_content = system_prompt or load_default_system_prompt()
    messages = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": user_prompt},
    ]

    print("\n" + "=" * 65)
    print("  ClientVault — Single Chat Completion Client")
    print(f"  Endpoint: {config['base_url']}")
    print(f"  Model:    {config['model']}")
    print("=" * 65 + "\n")

    result = send_chat_completion(messages=messages, config=config)

    print("\n" + "=" * 65)
    if result["success"]:
        print("  STATUS: CALL SUCCESSFUL")
        print("=" * 65)
        # Task 2: Print the model's text reply
        print("\n--- MODEL REPLY ---")
        print(result["content"])
        print("-------------------\n")
        if result["usage"]:
            print(f"Tokens Used: {result['usage']['total_tokens']} "
                  f"(Prompt: {result['usage']['prompt_tokens']}, "
                  f"Completion: {result['usage']['completion_tokens']})")
        return 0
    else:
        print("  STATUS: CALL FAILED")
        print("=" * 65)
        print("\n--- ERROR SUMMARY ---")
        print(result["error"])
        print("---------------------\n")
        return 1


def run_mock_server_demo(
    user_prompt: str = "Explain the standard client onboarding verification procedure.",
    system_prompt: Optional[str] = None,
    test_errors: bool = False,
    log_file: Optional[Path] = None,
) -> int:
    """Runs a local, zero-dependency OpenAI-compatible mock server for verified offline demonstrations."""
    import http.server
    import socket
    import threading
    import time

    setup_logging(level="INFO", log_file=log_file)

    class EphemeralMockHandler(http.server.BaseHTTPRequestHandler):
        mode = "success"

        def do_POST(self):
            content_len = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(content_len) if content_len > 0 else b""

            if EphemeralMockHandler.mode == "auth_error":
                res = {
                    "error": {
                        "message": "Incorrect API key provided.",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                }
                status = 401
            elif EphemeralMockHandler.mode == "rate_limit":
                res = {
                    "error": {
                        "message": "Rate limit reached for requests (quota exceeded).",
                        "type": "requests",
                        "param": None,
                        "code": "rate_limit_exceeded",
                    }
                }
                status = 429
            else:
                try:
                    req_data = json.loads(body_raw.decode("utf-8")) if body_raw else {}
                except Exception:
                    req_data = {}
                messages = req_data.get("messages", [])
                last_msg = messages[-1]["content"] if messages else "N/A"

                res = {
                    "id": f"chatcmpl-localmock-{int(time.time())}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "gpt-4o-mini",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": (
                                "Standard Client Onboarding Verification (KB-ONB-001 §3.2, p.4):\n"
                                "1. Verify authorized client sponsor identity via verified primary domain email.\n"
                                "2. Enforce strict dual-operator approval before credential provisioning.\n"
                                "3. Restrict initial IAM role to staging sandbox with audit trail enabled."
                            ),
                        },
                        "finish_reason": "stop",
                    }],
                    "usage": {
                        "prompt_tokens": 38,
                        "completion_tokens": 54,
                        "total_tokens": 92,
                    },
                }
                status = 200

            res_bytes = json.dumps(res).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res_bytes)))
            self.end_headers()
            self.wfile.write(res_bytes)

        def log_message(self, format, *args):
            pass

    # Find free port and bind
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = http.server.HTTPServer(("127.0.0.1", port), EphemeralMockHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}/v1"
    config = {
        "base_url": base_url,
        "api_key": "mock-demonstration-key",
        "model": "gpt-4o-mini",
        "is_local_endpoint": True,
    }

    print("\n" + "=" * 65)
    print("  ClientVault — Chat Completion Verification (Mock Mode)")
    print(f"  Target Endpoint: {base_url} (Local OpenAI-compatible mock)")
    print(f"  Selected Model:  {config['model']}")
    print("=" * 65 + "\n")

    sys_content = system_prompt or load_default_system_prompt()
    messages = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": user_prompt},
    ]

    # 1. Execute Successful Call
    EphemeralMockHandler.mode = "success"
    result = send_chat_completion(messages=messages, config=config)

    print("\n" + "=" * 65)
    if result["success"]:
        print("  STATUS: CALL SUCCESSFUL (200 OK)")
        print("=" * 65)
        print("\n--- MODEL REPLY ---")
        print(result["content"])
        print("-------------------\n")
        if result["usage"]:
            print(f"Tokens Used: {result['usage']['total_tokens']} "
                  f"(Prompt: {result['usage']['prompt_tokens']}, "
                  f"Completion: {result['usage']['completion_tokens']})")
    else:
        print("  STATUS: CALL FAILED")
        print("=" * 65)
        print(result["error"])
        server.shutdown()
        return 1

    # 2. Optionally Demonstrate Error Resilience
    if test_errors:
        print("\n" + "=" * 65)
        print("  Demonstrating Error Handling (Task 4 Resilience)")
        print("=" * 65)

        print("\n[Scenario A: HTTP 401 Authentication Error Simulation]")
        EphemeralMockHandler.mode = "auth_error"
        send_chat_completion(messages=messages, config=config)

        print("\n[Scenario B: HTTP 429 Rate Limit Error Simulation]")
        EphemeralMockHandler.mode = "rate_limit"
        client = create_client(base_url=base_url, api_key="any", max_retries=0)
        send_chat_completion(messages=messages, config=config, client=client)

    server.shutdown()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="ClientVault Chat Completion Client — Single Call Verification"
    )
    parser.add_argument(
        "-m", "--message",
        default="Explain the standard client onboarding verification procedure.",
        help="User inquiry message to submit to the model",
    )
    parser.add_argument(
        "-s", "--system",
        default=None,
        help="Optional custom system prompt text",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to custom .env file",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Path to write execution logs",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run against a local OpenAI-compatible mock server (no API key or internet required)",
    )
    parser.add_argument(
        "--test-errors",
        action="store_true",
        help="Simulate and test 401 and 429 error handling in mock mode",
    )
    args = parser.parse_args()

    log_p = Path(args.log_file) if args.log_file else None

    if args.mock or args.test_errors:
        exit_code = run_mock_server_demo(
            user_prompt=args.message,
            system_prompt=args.system,
            test_errors=args.test_errors,
            log_file=log_p,
        )
    else:
        env_p = Path(args.env_file) if args.env_file else None
        exit_code = run_standalone(
            user_prompt=args.message,
            system_prompt=args.system,
            env_path=env_p,
            log_file=log_p,
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

