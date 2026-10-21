"""
ClientVault — Retrieval Text Cleaning & Normalization Pipeline

Scenario:
Raw extracted documents from diverse formats (PDFs, HTML exports, Markdown, and text)
often harbor repetitive noise: recurring page headers and footers ("Page X of Y"),
breadcrumb navigation text, broken line wraps, unescaped HTML entities, runaway blank lines,
and non-standard Unicode encoding quirks. If embedded uncleaned, vector retrieval will
frequently match on irrelevant boilerplate or junk tokens.

This module implements:
- Task 1: Boilerplate removal (repeated headers, footers, pagination "Page X of Y", navigation breadcrumbs,
          and copyright notices).
- Task 2: Normalization of whitespace, broken hard-wrapped lines, hyphenated line wraps, and Unicode
          artifacts via standard Unicode NFKC normalization.
- Task 3: Uniform batch cleaning pipeline across all documents in a corpus while preserving
          source attribution, metadata, and structural content.
- Task 4: Detailed before-and-after metric reporting (character counts, line reductions, and diff views)
          demonstrating the exact effect of the cleaning pipeline.
- Task 5: End-to-end execution harness generating verifiable audit logs (`cleaning_pipeline_output.log`).
"""

import argparse
import logging
import re
import unicodedata
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.document_loader import Document, DocumentLoader

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.TextCleaner: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.TextCleaner")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CORPUS_DIR = PROJECT_ROOT / "data" / "sample_corpus"


# ---------------------------------------------------------------------------
# Task 1 & 2: Cleaning Rules & Regex Patterns
# ---------------------------------------------------------------------------

LINE_BOILERPLATE_PATTERNS = [
    # Page numbers and pagination lines
    re.compile(r"^\s*[-—=_\s]*\bPage\s+\d+(?:\s*(?:of|/)\s*\d+)?\b.*$", re.IGNORECASE),
    re.compile(r"^\s*[-—=\s]*\[?\s*Page\s+\d+\s*\]?[-—=\s]*$", re.IGNORECASE),
    re.compile(r"^\s*[-—=]+\s*Page\s+\d+\b.*$", re.IGNORECASE),
    # Breadcrumbs / Navigation headers
    re.compile(r"^\s*\[?\s*(?:Home|Navigation|Menu|Breadcrumb)\s*\]?\s*(?:>|/|\|).*$", re.IGNORECASE),
    re.compile(r"^\s*\[NAVIGATION:.*?\].*$", re.IGNORECASE),
    # Confidentiality / Copyright / Document headers
    re.compile(r"^\s*[-—=_\s]*\b(?:CONFIDENTIAL|STRICTLY CONFIDENTIAL|INTERNAL USE ONLY|ALL RIGHTS RESERVED)\b.*$", re.IGNORECASE),
    re.compile(r"^\s*Notice:\s*Copyright\b.*$", re.IGNORECASE),
    re.compile(r"^\s*[-—=_\s]*Document Header:.*$", re.IGNORECASE),
    # Standalone divider rules
    re.compile(r"^\s*[=\-_*]{4,}\s*$"),
]


def normalize_unicode_and_encoding(text: str) -> str:
    """
    Normalizes encoding artifacts and Unicode characters using NFKC.
    Replaces smart quotes, non-breaking spaces, em-dashes, and stray control characters.
    """
    if not text:
        return ""

    # Step 1: Unicode NFKC decomposition followed by canonical composition
    text = unicodedata.normalize("NFKC", text)

    # Step 2: Replace curly/smart quotes and special punctuation with ASCII equivalents
    replacements = {
        "\u2018": "'",   # Left single quote
        "\u2019": "'",   # Right single quote
        "\u201c": '"',   # Left double quote
        "\u201d": '"',   # Right double quote
        "\u2026": "...", # Ellipsis
        "\u00a0": " ",   # Non-breaking space
        "\u200b": "",    # Zero-width space
        "\ufeff": "",    # Byte order mark
        "\u2013": "-",   # En-dash
        "\u2014": " - ", # Em-dash
    }
    for old_char, new_char in replacements.items():
        text = text.replace(old_char, new_char)

    return text


def remove_boilerplate(text: str) -> Tuple[str, int]:
    """
    Task 1: Strips recurring headers, footers, pagination, and navigation breadcrumbs.
    Processes line-by-line to cleanly remove entire boilerplate lines rather than
    leaving dangling words.
    """
    cleaned_lines: List[str] = []
    total_stripped = 0

    for line in text.splitlines():
        is_boilerplate = False
        for pat in LINE_BOILERPLATE_PATTERNS:
            if pat.match(line):
                is_boilerplate = True
                total_stripped += 1
                break

        if not is_boilerplate:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines), total_stripped


def normalize_whitespace_and_wraps(text: str) -> str:
    """
    Task 2: Normalizes whitespace, repairs broken hyphenated line-wraps,
    and collapses runaway empty lines.
    """
    # 1. Repair hyphenated word wraps at line boundaries (e.g. "confer-\nence" -> "conference")
    repaired = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)

    # 2. Fix trailing spaces on each line
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in repaired.splitlines()]

    # 3. Collapse multiple blank lines down to a clean paragraph separator (maximum 2 newlines)
    result_lines: List[str] = []
    consecutive_empty = 0

    for line in lines:
        if not line:
            consecutive_empty += 1
            if consecutive_empty <= 1 and result_lines:
                result_lines.append("")
        else:
            consecutive_empty = 0
            result_lines.append(line)

    return "\n".join(result_lines).strip()


# ---------------------------------------------------------------------------
# Task 3: Unified Text Cleaning Pipeline
# ---------------------------------------------------------------------------

@dataclass
class CleaningMetrics:
    """Detailed before-and-after audit metrics for a single cleaned document."""
    source_id: str
    original_char_count: int
    cleaned_char_count: int
    char_reduction: int
    char_reduction_pct: float
    original_line_count: int
    cleaned_line_count: int
    boilerplate_removed_count: int


def clean_text(raw_text: str) -> Tuple[str, int]:
    """
    Executes full multi-stage cleaning pipeline on raw string input:
    1. Unicode & Encoding Normalization
    2. Header, Footer & Boilerplate Stripping
    3. Whitespace & Line-Wrap Normalization
    """
    # Stage 1: Unicode NFKC and character normalization
    text_norm = normalize_unicode_and_encoding(raw_text)

    # Stage 2: Boilerplate removal
    text_no_boilerplate, stripped_count = remove_boilerplate(text_norm)

    # Stage 3: Whitespace and layout normalization
    final_text = normalize_whitespace_and_wraps(text_no_boilerplate)

    return final_text, stripped_count


def clean_document(doc: Document) -> Tuple[Document, CleaningMetrics]:
    """
    Task 3: Cleans an ingested Document while preserving source identity and metadata.
    """
    cleaned_content, stripped_count = clean_text(doc.content)

    orig_len = len(doc.content)
    clean_len = len(cleaned_content)
    reduction = orig_len - clean_len
    reduction_pct = round((reduction / orig_len * 100), 2) if orig_len > 0 else 0.0

    orig_lines = len(doc.content.splitlines())
    clean_lines = len(cleaned_content.splitlines())

    metrics = CleaningMetrics(
        source_id=doc.source_id,
        original_char_count=orig_len,
        cleaned_char_count=clean_len,
        char_reduction=reduction,
        char_reduction_pct=reduction_pct,
        original_line_count=orig_lines,
        cleaned_line_count=clean_lines,
        boilerplate_removed_count=stripped_count,
    )

    cleaned_metadata = dict(doc.metadata)
    cleaned_metadata["is_cleaned"] = True
    cleaned_metadata["cleaning_reduction_pct"] = reduction_pct

    cleaned_doc = Document(
        content=cleaned_content,
        source_id=doc.source_id,
        file_path=doc.file_path,
        file_format=doc.file_format,
        char_count=clean_len,
        metadata=cleaned_metadata,
    )

    return cleaned_doc, metrics


def clean_corpus(documents: List[Document]) -> Tuple[List[Document], List[CleaningMetrics]]:
    """
    Task 3: Applies text cleaning consistently across an entire corpus of loaded documents.
    """
    cleaned_docs: List[Document] = []
    all_metrics: List[CleaningMetrics] = []

    for d in documents:
        cd, m = clean_document(d)
        cleaned_docs.append(cd)
        all_metrics.append(m)

    return cleaned_docs, all_metrics


# ---------------------------------------------------------------------------
# Task 4 & 5: Before / After Demonstration Runner & Log Generator
# ---------------------------------------------------------------------------

def run_cleaning_demonstration(corpus_dir: Optional[Path] = None) -> str:
    """Loads sample corpus, executes cleaning pipeline, and generates before/after report."""
    target_dir = corpus_dir or SAMPLE_CORPUS_DIR
    loader = DocumentLoader(base_dir=PROJECT_ROOT)
    raw_docs, skipped = loader.load_directory(target_dir)

    logs: List[str] = []

    def emit(line: str = ""):
        logs.append(line)
        print(line)

    emit("=" * 75)
    emit("  ClientVault — Retrieval Text Cleaning & Normalization Pipeline")
    emit(f"  Target Corpus: {target_dir.resolve()}")
    emit("=" * 75)
    emit()

    cleaned_docs, metrics_list = clean_corpus(raw_docs)

    emit("---------------------------------------------------------------------------")
    emit(">> CORPUS CLEANING METRICS SUMMARY (Task 3 & 4 Verification)")
    emit("---------------------------------------------------------------------------")
    emit(f"{'Source ID':<18} | {'Orig Chars':<10} | {'Clean Chars':<11} | {'Reduction':<9} | {'Lines (Pre->Post)':<16} | {'Boilerplate Items'}")
    emit("-" * 88)
    for m in metrics_list:
        lines_str = f"{m.original_line_count} -> {m.cleaned_line_count}"
        reduction_str = f"-{m.char_reduction} ({m.char_reduction_pct}%)"
        emit(f"{m.source_id:<18} | {m.original_char_count:<10} | {m.cleaned_char_count:<11} | {reduction_str:<9} | {lines_str:<16} | {m.boilerplate_removed_count} removed")
    emit()

    # Task 4: Detailed Before / After Demonstrations
    emit("=" * 75)
    emit(">> DETAILED BEFORE & AFTER EVIDENCE (Task 4)")
    emit("=" * 75)

    for raw, cleaned, m in zip(raw_docs, cleaned_docs, metrics_list):
        emit("-" * 75)
        emit(f">> DOCUMENT: {raw.source_id} ({raw.file_path})")
        emit(f"   Boilerplate Patterns Stripped: {m.boilerplate_removed_count}")
        emit(f"   Length: {m.original_char_count} chars -> {m.cleaned_char_count} chars (-{m.char_reduction_pct}%)")
        emit("-" * 75)
        emit()

        emit("   [BEFORE CLEANING - RAW EXTRACTED EXCERPT]")
        for l in raw.content.splitlines()[:12]:
            emit(f"     | {l}")
        if len(raw.content.splitlines()) > 12:
            emit("     | ... [remaining raw lines omitted for brevity] ...")
        emit()

        emit("   [AFTER CLEANING - RETRIEVAL READY EXCERPT]")
        for l in cleaned.content.splitlines()[:12]:
            emit(f"     | {l}")
        if len(cleaned.content.splitlines()) > 12:
            emit("     | ... [clean content continues] ...")
        emit()

    emit("=" * 75)
    emit("  STATUS: All corpus documents cleaned and normalized consistently.")
    emit("=" * 75)

    return "\n".join(logs)


def main():
    parser = argparse.ArgumentParser(description="ClientVault Retrieval Text Cleaning Runner")
    parser.add_argument("--corpus-dir", type=str, default=str(SAMPLE_CORPUS_DIR), help="Path to corpus directory")
    parser.add_argument("--output-file", type=str, default=None, help="Save cleaning comparison to log file")
    args = parser.parse_args()

    out_content = run_cleaning_demonstration(Path(args.corpus_dir))

    if args.output_file:
        out_path = Path(args.output_file)
        out_path.write_text(out_content, encoding="utf-8")
        print(f"\n[OK] Cleaning report saved to {out_path.resolve()}")


if __name__ == "__main__":
    main()
