"""
ClientVault — Structured JSON Output Parsing & Schema Validation

Scenario:
The RAG assistant must return machine-readable, schema-validated JSON containing
both the verified factual answer and its granular citation metadata. Free-form
prose introduces parse failures and prevents downstream automation.

This module implements:
- Task 1: Prompt engineering for structured JSON output with response_format={"type": "json_object"}.
- Task 2: Robust parsing of model JSON strings into typed Python dictionaries and Pydantic models.
- Task 3: Graceful error handling and repair heuristics for malformed JSON strings without crashing.
- Task 4: Strict schema validation enforcing required fields (answer, source, confidence, client_id)
          with rejection or automatic fallback recovery when essential fields are missing.
- Task 5: End-to-end execution harness generating verifiable logs across successful, malformed,
          repaired, and missing-field scenarios.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ValidationError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.StructuredOutput: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.StructuredOutput")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Task 4 & Pydantic Schema Definition
# ---------------------------------------------------------------------------

class SourceCitation(BaseModel):
    """Granular source traceability schema conforming to PRD v1.2 §18.1."""
    document_id: str = Field(description="Unique document code (e.g. KB-ONB-001)")
    section: str = Field(description="Runbook or procedure section (e.g. Section 3.2)")
    page: Optional[Union[int, str]] = Field(default=None, description="Page number where procedure appears")


class AssistantStructuredResponse(BaseModel):
    """Strict structured response schema required for downstream pipeline ingestion."""
    client_id: str = Field(description="Identifier for client isolation (e.g. ACME-001)")
    answer: str = Field(description="Factual, grounded procedural instructions")
    source: SourceCitation = Field(description="Granular source attribution object")
    confidence: float = Field(ge=0.0, le=1.0, description="Verification confidence score (0.0 to 1.0)")
    status: str = Field(default="VERIFIED", description="Verification status: VERIFIED, PARTIAL, or INSUFFICIENT_EVIDENCE")


# ---------------------------------------------------------------------------
# Task 1: Prompt Construction for Defined JSON Structure
# ---------------------------------------------------------------------------

STRUCTURED_SYSTEM_PROMPT = """You are the Client Support Knowledge Assistant for ClientVault.
Your job is to provide factual, grounded operational procedures strictly from retrieved evidence.

CRITICAL INSTRUCTION:
You must ALWAYS respond with a single, valid JSON object conforming exactly to this JSON schema:
{
  "client_id": "string (e.g. ACME-001)",
  "answer": "string (procedural steps)",
  "source": {
    "document_id": "string",
    "section": "string",
    "page": "integer or string"
  },
  "confidence": 1.0,
  "status": "VERIFIED"
}

RULES:
1. Do not enclose the JSON in markdown code blocks like ```json ... ``` if response_format json_object is enabled.
2. If evidence is insufficient, set "status": "INSUFFICIENT_EVIDENCE", "confidence": 0.0, and state "INSUFFICIENT EVIDENCE" in the answer.
3. Every required field ("client_id", "answer", "source", "confidence") must be present.
"""

FALLBACK_RECOVERY_RESPONSE = {
    "client_id": "UNKNOWN",
    "answer": "INSUFFICIENT EVIDENCE: Structured output validation failed or required fields could not be verified.",
    "source": {
        "document_id": "NONE",
        "section": "N/A",
        "page": "N/A",
    },
    "confidence": 0.0,
    "status": "INSUFFICIENT_EVIDENCE",
}


# ---------------------------------------------------------------------------
# Task 2 & Task 3: JSON Parsing and Graceful Error Handling / Repair
# ---------------------------------------------------------------------------

def extract_and_repair_json(raw_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    """
    Parses a raw text string into a dictionary.
    Handles:
    - Clean JSON directly
    - Markdown-wrapped JSON (```json ... ```)
    - Trailing commas or common syntax aberrations via regex repair
    - Unrecoverable syntax errors (reported clearly without throwing exceptions)

    Returns:
        (parsed_dict, error_message, was_repaired)
    """
    if not raw_text or not raw_text.strip():
        return None, "Empty response body received from model", False

    clean_text = raw_text.strip()

    # Step 1: Attempt standard json.loads
    try:
        data = json.loads(clean_text)
        if isinstance(data, dict):
            return data, None, False
        return None, f"Expected JSON object (dict), received {type(data).__name__}", False
    except json.JSONDecodeError as direct_err:
        pass

    # Step 2: Attempt extraction from markdown code fences
    fence_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    fence_match = re.search(fence_pattern, clean_text)
    if fence_match:
        fenced_content = fence_match.group(1).strip()
        try:
            data = json.loads(fenced_content)
            if isinstance(data, dict):
                return data, None, True  # Repaired from markdown
        except json.JSONDecodeError:
            clean_text = fenced_content  # Continue to repair heuristics on extracted text

    # Step 3: Heuristic Repair for common LLM syntax flaws (trailing commas, unclosed brackets)
    repaired_text = clean_text

    # Remove trailing commas before closing braces/brackets: e.g. { "a": 1, } -> { "a": 1 }
    repaired_text = re.sub(r",\s*([\]}])", r"\1", repaired_text)

    # Strip any dangling comma at the end of the text if truncated
    repaired_text = re.sub(r",\s*$", "", repaired_text)

    # Check if a closing brace was cut off at the end
    if repaired_text.startswith("{") and not repaired_text.endswith("}"):
        # If odd number of unescaped quotes exist, close quote
        if repaired_text.count('"') % 2 != 0:
            repaired_text += '"'
        repaired_text += "\n}"

    # Remove trailing commas again if one was exposed before the new closing brace
    repaired_text = re.sub(r",\s*([\]}])", r"\1", repaired_text)

    try:
        data = json.loads(repaired_text)
        if isinstance(data, dict):
            return data, None, True
    except json.JSONDecodeError as second_err:
        # Unrecoverable syntax error — Report clearly without crashing
        err_msg = (
            f"JSON Parse Failure: Invalid syntax at line {second_err.lineno}, column {second_err.colno}. "
            f"Error: {second_err.msg}. Snippet: {clean_text[:80]!r}"
        )
        return None, err_msg, False


# ---------------------------------------------------------------------------
# Task 4: Schema & Required Field Validation
# ---------------------------------------------------------------------------

def validate_structured_payload(
    payload: Dict[str, Any],
    allow_recovery: bool = True
) -> Tuple[bool, Optional[AssistantStructuredResponse], List[str]]:
    """
    Validates that all required fields and subfields are present and correctly typed.
    
    Required fields:
    - 'client_id' (str)
    - 'answer' (str)
    - 'source' (dict with document_id and section)
    - 'confidence' (float between 0.0 and 1.0)

    Returns:
        (is_valid, validated_model_or_fallback, validation_errors)
    """
    errors: List[str] = []

    # 1. Check top-level required fields explicitly
    required_keys = ["client_id", "answer", "source", "confidence"]
    for key in required_keys:
        if key not in payload:
            errors.append(f"Missing required field: '{key}'")
        elif payload[key] is None:
            errors.append(f"Required field '{key}' cannot be null")

    # 2. Check source sub-fields if source exists
    if "source" in payload and isinstance(payload["source"], dict):
        if not payload["source"].get("document_id"):
            errors.append("Missing required source subfield: 'source.document_id'")
        if not payload["source"].get("section"):
            errors.append("Missing required source subfield: 'source.section'")
    elif "source" in payload and not isinstance(payload["source"], dict):
        errors.append(f"Field 'source' must be an object/dict, got {type(payload['source']).__name__}")

    # 3. Pydantic validation for deep type enforcement
    if not errors:
        try:
            validated_obj = AssistantStructuredResponse(**payload)
            return True, validated_obj, []
        except ValidationError as pydantic_err:
            for err in pydantic_err.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"Field '{loc}': {err['msg']}")

    # Recovery handling
    if allow_recovery:
        fallback = AssistantStructuredResponse(**FALLBACK_RECOVERY_RESPONSE)
        return False, fallback, errors
    return False, None, errors


# ---------------------------------------------------------------------------
# Pipeline Wrapper: Parse + Validate
# ---------------------------------------------------------------------------

def process_model_json_output(
    raw_response: str,
    allow_recovery: bool = True
) -> Dict[str, Any]:
    """
    High-level processor that takes raw LLM output, parses JSON, handles errors,
    and runs schema validation.
    """
    parsed_dict, parse_err, was_repaired = extract_and_repair_json(raw_response)

    if parse_err:
        logger.warning("Malformed JSON detected: %s", parse_err)
        if allow_recovery:
            fallback = AssistantStructuredResponse(**FALLBACK_RECOVERY_RESPONSE)
            return {
                "success": False,
                "data": fallback.model_dump(),
                "error": parse_err,
                "repaired": False,
                "recovered": True,
            }
        return {
            "success": False,
            "data": None,
            "error": parse_err,
            "repaired": False,
            "recovered": False,
        }

    is_valid, validated_obj, val_errors = validate_structured_payload(
        parsed_dict, allow_recovery=allow_recovery
    )

    if not is_valid:
        logger.warning("Schema validation failed: %s", "; ".join(val_errors))
        return {
            "success": False,
            "data": validated_obj.model_dump() if validated_obj else None,
            "error": f"Schema Validation Error: {'; '.join(val_errors)}",
            "repaired": was_repaired,
            "recovered": allow_recovery,
        }

    return {
        "success": True,
        "data": validated_obj.model_dump(),
        "error": None,
        "repaired": was_repaired,
        "recovered": False,
    }


# ---------------------------------------------------------------------------
# Task 5: Experiment Execution Harness & Comparison Generator
# ---------------------------------------------------------------------------

def run_structured_output_experiments(use_mock: bool = True) -> str:
    """
    Executes and records comparison outputs across 4 distinct test scenarios:
    1. Valid Model JSON response (Clean)
    2. Model response wrapped in Markdown code fences (Auto-extracted)
    3. Malformed JSON with trailing commas and missing quote/brace (Repaired & Recovered)
    4. Missing required fields (Rejected & Safely Fallbacked)
    """
    logs: List[str] = []

    def emit(line: str = ""):
        logs.append(line)
        print(line)

    emit("=" * 75)
    emit("  ClientVault — Structured JSON Output Parsing & Schema Validation")
    emit("  Mode: " + ("Self-Contained Mock & Test Scenarios" if use_mock else "Live API Endpoint"))
    emit("=" * 75)
    emit()

    test_cases = [
        {
            "name": "Scenario 1: Perfectly Formatted Clean JSON (Golden Path)",
            "description": "Model returns standard JSON complying with schema and response_format",
            "raw_input": json.dumps({
                "client_id": "ACME-001",
                "answer": "To verify client onboarding credentials, verify the sponsor's corporate email domain (@acme-logistics.com), enforce dual-operator approval, and restrict access to Staging VPC sandbox for 48 hours.",
                "source": {
                    "document_id": "KB-ONB-001",
                    "section": "Section 3.2",
                    "page": 4
                },
                "confidence": 0.98,
                "status": "VERIFIED"
            }, indent=2),
        },
        {
            "name": "Scenario 2: JSON Wrapped in Markdown Fences (Common LLM Behavior)",
            "description": "Model encloses JSON in ```json markdown fence despite prompt instructions",
            "raw_input": (
                "Here is the verified procedural information:\n\n"
                "```json\n"
                "{\n"
                '  "client_id": "NEXUS-002",\n'
                '  "answer": "Rotate Tier-1 API credentials via the Security Portal after receiving Slack verification from the Account Lead.",\n'
                '  "source": {\n'
                '    "document_id": "KB-SEC-004",\n'
                '    "section": "Section 5.1",\n'
                '    "page": 12\n'
                "  },\n"
                '  "confidence": 0.95,\n'
                '  "status": "VERIFIED"\n'
                "}\n"
                "```\n"
                "Please let me know if you need more details."
            ),
        },
        {
            "name": "Scenario 3: Malformed JSON with Trailing Commas & Cutoff Brace (Heuristic Repair)",
            "description": "Syntax errors (trailing comma, unclosed bracket) repaired automatically",
            "raw_input": (
                "{\n"
                '  "client_id": "VERTEX-003",\n'
                '  "answer": "Execute database failover following SOP-DB-007 after triggering PagerDuty incident.",\n'
                '  "source": {\n'
                '    "document_id": "KB-OPS-009",\n'
                '    "section": "Section 2.4",\n'
                '    "page": 8,\n'  # Trailing comma
                "  },\n"             # Trailing comma
                '  "confidence": 0.92,\n'
                '  "status": "VERIFIED",\n'  # Trailing comma
                # Missing closing brace '}' simulated
            ),
        },
        {
            "name": "Scenario 4: Missing Required Fields (Strict Validation & Fallback Recovery)",
            "description": "Model omits required 'source' and 'confidence' fields; system catches and recovers",
            "raw_input": json.dumps({
                "client_id": "ACME-001",
                "answer": "Bypass 2FA for the client technician using master emergency tokens.",
                # Missing 'source'
                # Missing 'confidence'
            }, indent=2),
        },
        {
            "name": "Scenario 5: Unrecoverable Corrupted String (Graceful Non-Crashing Handling)",
            "description": "Garbage non-JSON string; caught cleanly without throwing an unhandled exception",
            "raw_input": "FATAL: Connection dropped during streaming. Could not complete response <<<INVALID>>>",
        },
    ]

    for tc in test_cases:
        emit("-" * 75)
        emit(f">> {tc['name']}")
        emit(f"   Description: {tc['description']}")
        emit("   Raw Model Output:")
        for line in tc["raw_input"].splitlines():
            emit(f"     | {line}")
        emit()

        result = process_model_json_output(tc["raw_input"], allow_recovery=True)

        emit(f"   Parse & Validation Result:")
        emit(f"     * Overall Success: {result['success']}")
        emit(f"     * Repaired from Malformed: {result['repaired']}")
        emit(f"     * Recovered via Fallback: {result['recovered']}")
        if result["error"]:
            emit(f"     * Error Reported: {result['error']}")
        emit(f"     * Usable Object Content:")
        emit(json.dumps(result["data"], indent=7))
        emit()

    emit("=" * 75)
    emit("  GROUNDED ASSISTANT RECOMMENDATION: JSON STRUCTURED OUTPUT")
    emit("=" * 75)
    emit("1. Parameter Configuration:")
    emit("   - Set response_format={'type': 'json_object'} where supported to constrain token sampling.")
    emit("   - Set temperature=0.0 to eliminate stochastic JSON syntax deviations.")
    emit("2. Double-Layer Protection:")
    emit("   - Layer 1 (Parsing): Extract markdown fences and strip trailing commas to prevent runtime crashes.")
    emit("   - Layer 2 (Schema): Validate required keys ('answer', 'source') via Pydantic before downstream use.")
    emit("3. Deterministic Safety Recovery:")
    emit("   - When required fields are missing, return explicit INSUFFICIENT_EVIDENCE fallback rather than partial data.")
    emit("=" * 75)

    return "\n".join(logs)


def main():
    parser = argparse.ArgumentParser(description="ClientVault Structured JSON Output & Validation Runner")
    parser.add_argument("--mock", action="store_true", default=True, help="Run self-contained test scenarios")
    parser.add_argument("--output-file", type=str, default=None, help="Save comparison trace to output file")
    args = parser.parse_args()

    output = run_structured_output_experiments(use_mock=args.mock)

    if args.output_file:
        out_path = Path(args.output_file)
        out_path.write_text(output, encoding="utf-8")
        print(f"\n[OK] Comparison results saved to {out_path.resolve()}")


if __name__ == "__main__":
    main()
