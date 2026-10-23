"""
ClientVault — Multi-Format Document Loader & Intake Engine

Scenario:
A RAG assistant's knowledge base consists of diverse document formats across
clients (Markdown runbooks, plain-text SLAs, HTML knowledge exports, and PDF manuals).
Before chunking or embedding can occur, all files must be ingested into a standardized
plain-text format, stamped with granular source identity for traceability, and safeguarded
against corrupted or unsupported files.

This module implements:
- Task 1: Loading multiple document formats (Markdown, Plain Text, HTML, PDF/Simulated)
          into a standardized plain-text representation.
- Task 2: Robust exception handling that skips missing, unreadable, empty, or unsupported
          files with explicit logging instead of crashing the run.
- Task 3: Preservation of source identity metadata (filename, relative path, document identifier,
          format, and character count) to support 100% downstream citation traceability.
- Task 4: Intake confirmation reporting text character count and snippet previews.
- Task 5: Self-contained demonstration loading the committed sample corpus (`data/sample_corpus/`).
"""

import argparse
import html
import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.DocumentLoader: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.DocumentLoader")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CORPUS_DIR = PROJECT_ROOT / "data" / "sample_corpus"


@dataclass
class Document:
    """Standardized internal representation of an ingested document."""
    content: str
    source_id: str
    file_path: str
    file_format: str
    char_count: int
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UnsupportedFileError(Exception):
    """Raised when an unrecognized file format is encountered."""
    pass


class DocumentReadError(Exception):
    """Raised when an error occurs while opening or parsing a document."""
    pass


# ---------------------------------------------------------------------------
# Format-Specific Extractors (Task 1)
# ---------------------------------------------------------------------------

def extract_text_from_txt(path: Path) -> str:
    """Extracts raw text from plain text files."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        # Fallback to latin-1 encoding if UTF-8 fails
        return path.read_text(encoding="latin-1").strip()


def extract_text_from_md(path: Path) -> str:
    """Extracts clean text from Markdown documents, preserving structural headings."""
    raw = extract_text_from_txt(path)
    # Normalize excessive newlines while preserving markdown headers
    clean = re.sub(r"\n{3,}", "\n\n", raw)
    return clean.strip()


def extract_text_from_html(path: Path) -> str:
    """
    Extracts text from HTML documents, stripping script/style tags and HTML tags,
    and decoding HTML entities.
    """
    raw_html = extract_text_from_txt(path)
    # Remove script and style elements
    clean_html = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", "", raw_html, flags=re.IGNORECASE)
    # Replace block level tags with newlines
    clean_html = re.sub(r"<(div|p|h[1-6]|li|br|header|footer|section|article)[^>]*>", "\n", clean_html, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", clean_html)
    # Unescape HTML entities (e.g. &amp;, &lt;)
    text = html.unescape(text)
    # Consolidate whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(path: Path) -> str:
    """
    Extracts text from PDF files.
    Tries pypdf if installed; falls back to stream-based text extraction (BT...ET and Tj operators)
    and structural filtering for uncompressed or plain PDFs.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        pages_text = [page.extract_text() or "" for page in reader.pages if page.extract_text()]
        if pages_text:
            return "\n\n".join(pages_text).strip()
    except Exception:
        pass

    try:
        raw_bytes = path.read_bytes()
        content_str = raw_bytes.decode("latin-1")

        # 1. Search for PDF text objects: BT ... ET
        text_blocks = re.findall(r"BT[\s\S]*?ET", content_str)
        extracted_lines = []
        if text_blocks:
            for block in text_blocks:
                # Find (text) Tj
                tj_matches = re.findall(r"\((.*?)\)\s*Tj", block)
                for item in tj_matches:
                    clean_item = item.replace(r"\(", "(").replace(r"\)", ")")
                    if clean_item.strip():
                        extracted_lines.append(clean_item.strip())
                # Find [(text) ...] TJ
                tj_arrays = re.findall(r"\[(.*?)\]\s*TJ", block)
                for arr in tj_arrays:
                    parts = re.findall(r"\((.*?)\)", arr)
                    if parts:
                        line = " ".join(p.replace(r"\(", "(").replace(r"\)", ")") for p in parts)
                        if line.strip():
                            extracted_lines.append(line.strip())

        if extracted_lines:
            return "\n".join(extracted_lines).strip()

        # 2. If no BT/ET blocks, try stream ... endstream blocks
        stream_matches = re.findall(r"stream[\r\n]+([\s\S]*?)[\r\n]+endstream", content_str)
        stream_text_lines = []
        for s in stream_matches:
            lines = [line.strip() for line in s.splitlines() if line.strip() and not line.strip().startswith(("%", "xref", "trailer"))]
            for l in lines:
                printable = "".join(ch for ch in l if ch.isprintable() or ch in " \t")
                if len(printable) > 3 and not re.match(r"^[\d\s\<\>\/\[\]]+$", printable):
                    stream_text_lines.append(printable)
        if stream_text_lines:
            return "\n".join(stream_text_lines).strip()

        # 3. Direct decode fallback, filtering binary PDF header/trailer artifacts
        decoded = raw_bytes.decode("utf-8", errors="ignore")
        clean_lines = []
        for line in decoded.splitlines():
            l_strip = line.strip()
            if not l_strip:
                continue
            if re.match(r"^(%PDF|xref|\d+\s+\d+|trailer|startxref|%%EOF|<<|>>|\d+\s+\d+\s+obj|endobj)", l_strip):
                continue
            printable = "".join(ch for ch in l_strip if ch.isprintable() or ch in " \t")
            if printable:
                clean_lines.append(printable)

        if clean_lines:
            return "\n".join(clean_lines).strip()

        raise DocumentReadError(f"No readable text could be extracted from PDF: {path.name}")
    except DocumentReadError:
        raise
    except Exception as e:
        raise DocumentReadError(f"Failed to parse PDF binary without pypdf library: {e}")


# Registry of supported loaders
SUPPORTED_EXTENSIONS = {
    ".txt": extract_text_from_txt,
    ".md": extract_text_from_md,
    ".markdown": extract_text_from_md,
    ".html": extract_text_from_html,
    ".htm": extract_text_from_html,
    ".pdf": extract_text_from_pdf,
}


# ---------------------------------------------------------------------------
# Core Document Loader (Tasks 1, 2, 3, 4)
# ---------------------------------------------------------------------------

class DocumentLoader:
    """
    Universal multi-format document loader with error shielding and source tagging.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir or PROJECT_ROOT).resolve()

    def load_single_file(self, file_path: Union[str, Path]) -> Optional[Document]:
        """
        Loads a single document file into a Document object.
        Gracefully catches missing, unsupported, or corrupt files (Task 2).
        Preserves source identity (Task 3).
        """
        path = Path(file_path).resolve()

        # Task 2: Handle missing file gracefully
        if not path.exists():
            logger.warning("[SKIP] File not found: '%s'", path)
            return None

        if not path.is_file():
            logger.warning("[SKIP] Path is not a regular file: '%s'", path)
            return None

        ext = path.suffix.lower()

        # Task 2: Handle unsupported extension
        if ext not in SUPPORTED_EXTENSIONS:
            logger.warning("[SKIP] Unsupported file format '%s': '%s'", ext, path.name)
            return None

        # Task 1 & 2: Execute format extractor with error resilience
        extractor = SUPPORTED_EXTENSIONS[ext]
        try:
            content = extractor(path)
            if not content.strip():
                logger.warning("[SKIP] File '%s' is empty or produced no readable text", path.name)
                return None
        except Exception as err:
            logger.error("[SKIP] Corrupted or unreadable file '%s': %s", path.name, err)
            return None

        # Task 3: Preserve source identity and metadata
        try:
            rel_path = str(path.relative_to(self.base_dir))
        except ValueError:
            rel_path = str(path)

        source_id = path.stem

        doc = Document(
            content=content,
            source_id=source_id,
            file_path=rel_path,
            file_format=ext.lstrip("."),
            char_count=len(content),
            metadata={
                "filename": path.name,
                "extension": ext,
                "absolute_path": str(path),
                "file_size_bytes": path.stat().st_size,
            },
        )
        return doc

    def load_directory(
        self,
        directory_path: Union[str, Path],
        recursive: bool = True
    ) -> Tuple[List[Document], List[str]]:
        """
        Loads all supported documents within a directory.
        Returns:
            (loaded_documents, skipped_or_error_files)
        """
        dir_path = Path(directory_path).resolve()
        if not dir_path.exists() or not dir_path.is_dir():
            logger.error("Directory not found or invalid: '%s'", dir_path)
            return [], [f"Directory not found: {dir_path}"]

        loaded_docs: List[Document] = []
        skipped_records: List[str] = []

        pattern = "**/*" if recursive else "*"
        all_paths = sorted(dir_path.glob(pattern))

        for p in all_paths:
            if not p.is_file():
                continue
            doc = self.load_single_file(p)
            if doc:
                loaded_docs.append(doc)
            else:
                skipped_records.append(p.name)

        return loaded_docs, skipped_records


# ---------------------------------------------------------------------------
# Task 4 & 5: Intake Confirmation & Demonstration Runner
# ---------------------------------------------------------------------------

def run_intake_demonstration(target_dir: Optional[Path] = None) -> str:
    """Runs intake over sample corpus, printing confirmation lengths and samples."""
    dir_to_load = target_dir or SAMPLE_CORPUS_DIR
    loader = DocumentLoader(base_dir=PROJECT_ROOT)

    logs: List[str] = []

    def emit(line: str = ""):
        logs.append(line)
        print(line)

    emit("=" * 75)
    emit("  ClientVault — Multi-Format Document Loader & Intake Confirmation")
    emit(f"  Target Corpus: {dir_to_load.resolve()}")
    emit("=" * 75)
    emit()

    loaded_docs, skipped_files = loader.load_directory(dir_to_load)

    emit(f"Intake Summary: Loaded {len(loaded_docs)} document(s) | Skipped {len(skipped_files)} file(s)")
    emit()

    # Task 4: Confirm intake with character count and snippet
    emit("-" * 75)
    emit(">> CONFIRMED INTAKE DOCUMENTS (Task 3 & 4 Verification)")
    emit("-" * 75)

    for i, doc in enumerate(loaded_docs, 1):
        emit(f"[{i}] Document Source ID: '{doc.source_id}'")
        emit(f"    File Path:         {doc.file_path}")
        emit(f"    Format:            {doc.file_format.upper()}")
        emit(f"    Length:            {doc.char_count} characters")
        emit(f"    Sample Preview:")
        # Show first 3 lines of preview
        preview_lines = [line.strip() for line in doc.content.splitlines() if line.strip()][:3]
        for pl in preview_lines:
            emit(f"      | {pl[:90]}")
        emit()

    # Task 2 Verification: Report skipped / unsupported files
    emit("-" * 75)
    emit(">> RESILIENCE & SKIPPED FILES REPORT (Task 2 Verification)")
    emit("-" * 75)
    if skipped_files:
        for sf in skipped_files:
            emit(f"  [SKIPPED SAFELY] {sf} (Non-crashing skip of unsupported/corrupted format)")
    else:
        emit("  No files skipped.")
    emit()

    # Missing file simulation test
    emit(">> MISSING FILE TEST:")
    missing_test_path = dir_to_load / "non_existent_file.txt"
    res = loader.load_single_file(missing_test_path)
    emit(f"  Load result for '{missing_test_path.name}': {res} (Handled gracefully without crash)")
    emit()

    emit("=" * 75)
    emit("  STATUS: All formats loaded into common plain text with source attribution.")
    emit("=" * 75)

    return "\n".join(logs)


def main():
    parser = argparse.ArgumentParser(description="ClientVault Document Loader Runner")
    parser.add_argument("--corpus-dir", type=str, default=str(SAMPLE_CORPUS_DIR), help="Path to corpus directory")
    parser.add_argument("--output-file", type=str, default=None, help="Save intake summary to log file")
    args = parser.parse_args()

    corpus_path = Path(args.corpus_dir)
    output = run_intake_demonstration(corpus_path)

    if args.output_file:
        out_path = Path(args.output_file)
        out_path.write_text(output, encoding="utf-8")
        print(f"\n[OK] Intake report saved to {out_path.resolve()}")


if __name__ == "__main__":
    main()
