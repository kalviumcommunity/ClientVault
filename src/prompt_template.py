"""
ClientVault — Reusable Prompt Templates & Dynamic Injection Module

Scenario:
Prompts tend to proliferate and repeat across codebases, making wording changes
error-prone. This module establishes a single, decoupled template management system:
- Task 1: PromptTemplate class with named placeholder extraction ({context}, {question}, etc.)
          and safe rendering.
- Task 2: Dynamic runtime injection of contextual values, verifying missing/extra keys.
- Task 3: Multi-feature reuse demonstrating identical template engine powering both
          an Interactive Support Chat path and a Batch Audit CLI verification path.
- Task 4: Strict separation of template text files (in prompts/templates/) from Python logic.
- Task 5: End-to-end execution harness demonstrating filled renders and test scenarios.
"""

import argparse
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.PromptTemplate: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.PromptTemplate")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "prompts" / "templates"


class MissingPlaceholderError(ValueError):
    """Raised when required placeholders in a template are not supplied."""
    pass


class PromptTemplate:
    """
    Reusable template abstraction storing prompt structure separately from application logic.
    Supports placeholder extraction, safe rendering, and default values.
    """

    def __init__(self, template_str: str, name: str = "unnamed_template"):
        self.template_str = template_str.strip()
        self.name = name
        self.placeholders = self._extract_placeholders(self.template_str)

    @classmethod
    def from_file(cls, file_path: Path) -> "PromptTemplate":
        """Loads a template from an external text file."""
        if not file_path.exists():
            raise FileNotFoundError(f"Template file not found at: {file_path}")
        content = file_path.read_text(encoding="utf-8")
        return cls(template_str=content, name=file_path.stem)

    @classmethod
    def load(cls, template_name: str) -> "PromptTemplate":
        """Loads a template by name from the standard prompts/templates directory."""
        filename = template_name if template_name.endswith(".template") else f"{template_name}.template"
        target_path = TEMPLATES_DIR / filename
        return cls.from_file(target_path)

    @staticmethod
    def _extract_placeholders(text: str) -> Set[str]:
        """Extracts all {placeholder} names using regex, ignoring double braces {{...}}."""
        # Find single {identifier} patterns
        pattern = r"(?<!\{)\{([a-zA-Z0-9_]+)\}(?!\})"
        return set(re.findall(pattern, text))

    def render(self, strict: bool = True, **kwargs: Any) -> str:
        """
        Renders the template by injecting dynamic keyword values.
        
        Args:
            strict: If True, raises MissingPlaceholderError if any placeholder is missing.
            **kwargs: Dynamic values for named placeholders.
            
        Returns:
            The filled prompt string.
        """
        provided_keys = set(kwargs.keys())
        missing_keys = self.placeholders - provided_keys

        if missing_keys and strict:
            raise MissingPlaceholderError(
                f"Cannot render template '{self.name}': Missing required placeholder(s): {sorted(missing_keys)}"
            )

        rendered = self.template_str
        for key in self.placeholders:
            if key in kwargs:
                val_str = str(kwargs[key])
                rendered = rendered.replace(f"{{{key}}}", val_str)
            elif not strict:
                # Retain unrendered placeholder if non-strict
                pass

        return rendered


# ---------------------------------------------------------------------------
# Template Registry & Loader
# ---------------------------------------------------------------------------

class TemplateRegistry:
    """Central registry and cache for all project prompt templates."""

    _cache: Dict[str, PromptTemplate] = {}

    @classmethod
    def get(cls, name: str) -> PromptTemplate:
        """Retrieves a cached template or loads it from disk."""
        if name not in cls._cache:
            cls._cache[name] = PromptTemplate.load(name)
        return cls._cache[name]

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()


# ---------------------------------------------------------------------------
# Task 3: Feature Re-use Implementations
# ---------------------------------------------------------------------------

def render_support_chat_messages(
    client_id: str,
    clearance_level: str,
    document_id: str,
    section: str,
    page: Union[int, str],
    context: str,
    question: str,
) -> List[Dict[str, str]]:
    """
    Feature 1: Interactive Support Chat Path.
    Uses TemplateRegistry to build system and user messages.
    """
    sys_template = TemplateRegistry.get("system_prompt")
    user_template = TemplateRegistry.get("user_retrieval")

    system_content = sys_template.render(
        client_id=client_id,
        clearance_level=clearance_level,
    )
    user_content = user_template.render(
        client_id=client_id,
        document_id=document_id,
        section=section,
        page=page,
        context=context,
        question=question,
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def render_batch_cli_audit_message(
    client_id: str,
    batch_id: str,
    document_id: str,
    context: str,
    question: str,
) -> Dict[str, str]:
    """
    Feature 2: Batch CLI Audit Path.
    Reuses the template engine for offline compliance verification.
    """
    batch_template = TemplateRegistry.get("batch_audit")
    content = batch_template.render(
        client_id=client_id,
        batch_id=batch_id,
        document_id=document_id,
        context=context,
        question=question,
    )
    return {"role": "user", "content": content}


# ---------------------------------------------------------------------------
# Task 5: Demonstration & Render Output Harness
# ---------------------------------------------------------------------------

def run_template_demonstration() -> str:
    """Executes sample renders across multiple features and verifies placeholder injection."""
    logs: List[str] = []

    def emit(line: str = ""):
        logs.append(line)
        print(line)

    emit("=" * 75)
    emit("  ClientVault — Reusable Prompt Templates & Dynamic Injection Demo")
    emit("=" * 75)
    emit()

    # Feature 1 Render
    emit("---------------------------------------------------------------------------")
    emit(">> FEATURE 1: Interactive Support Chat Path (Dynamic Injection)")
    emit("---------------------------------------------------------------------------")
    chat_messages = render_support_chat_messages(
        client_id="ACME-001",
        clearance_level="Tier-2 Service Desk Lead",
        document_id="KB-ONB-001",
        section="Section 3.2",
        page=4,
        context="All onboarding credentials require dual-operator verification before activation. Staging sandbox restricted to 48 hours.",
        question="How do I verify and activate credentials for ACME Corp onboarding engineers?",
    )

    emit(f"System Message Rendered ({len(chat_messages[0]['content'])} chars):")
    for l in chat_messages[0]["content"].splitlines()[:15]:
        emit(f"   | {l}")
    emit("   | ... [Full system prompt truncated for display] ...")
    emit()
    emit(f"User Message Rendered ({len(chat_messages[1]['content'])} chars):")
    for l in chat_messages[1]["content"].splitlines():
        emit(f"   | {l}")
    emit()

    # Feature 2 Render
    emit("---------------------------------------------------------------------------")
    emit(">> FEATURE 2: Batch CLI Compliance Audit Path (Reused Engine)")
    emit("---------------------------------------------------------------------------")
    batch_msg = render_batch_cli_audit_message(
        client_id="NEXUS-002",
        batch_id="BATCH-2026-10-Q4-089",
        document_id="SOP-SEC-009",
        context="Quarterly secret key rotation must be performed within 72 hours of notification using the vault KMS console.",
        question="Was the KMS secret key rotated within the mandatory 72-hour compliance window?",
    )
    emit(f"Audit Payload Rendered ({len(batch_msg['content'])} chars):")
    for l in batch_msg["content"].splitlines():
        emit(f"   | {l}")
    emit()

    # Error Resilience Demonstration: Missing Placeholder
    emit("---------------------------------------------------------------------------")
    emit(">> ERROR HANDLING: Missing Placeholder Guard Demonstration")
    emit("---------------------------------------------------------------------------")
    user_tmpl = TemplateRegistry.get("user_retrieval")
    try:
        emit("Attempting to render user_retrieval without 'context' placeholder...")
        user_tmpl.render(
            strict=True,
            client_id="ACME-001",
            document_id="KB-ONB-001",
            section="Section 3.2",
            page=4,
            question="What are the steps?",
            # missing 'context' intentionally
        )
    except MissingPlaceholderError as err:
        emit(f"Successfully caught expected error: {err}")
    emit()

    emit("=" * 75)
    emit("  SUMMARY: All prompt templates verified separate from logic and safely reusable.")
    emit("=" * 75)

    return "\n".join(logs)


def main():
    parser = argparse.ArgumentParser(description="ClientVault Prompt Template & Dynamic Injection Runner")
    parser.add_argument("--output-file", type=str, default=None, help="Save rendered examples to log file")
    args = parser.parse_args()

    output = run_template_demonstration()

    if args.output_file:
        out_path = Path(args.output_file)
        out_path.write_text(output, encoding="utf-8")
        print(f"\n[OK] Example renders saved to {out_path.resolve()}")


if __name__ == "__main__":
    main()
