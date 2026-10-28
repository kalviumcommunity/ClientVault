"""
ClientVault — Document Upload & Indexing Endpoint (FastAPI)

POST /documents — accepts multipart file uploads, validates them,
processes through ingestion pipeline (parse, clean, chunk, embed, index),
and returns indexing results. Newly indexed chunks are immediately
available to /query without restart.
"""

import json
import logging
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Depends
from pydantic import BaseModel, Field

from dotenv import load_dotenv

from src.ingestion_pipeline import IngestionPipeline, IngestionRunResult
from src.corpus_embedder import CorpusEmbedder, DEFAULT_EMBEDDING_DIM
from src.corpus_indexer import CorpusIndexer, IndexingStats
from src.vector_db import VectorDatabaseManager, VectorDBConfig, load_vector_db_config
from src.document_loader import SUPPORTED_EXTENSIONS

load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("ClientVault.DocUpload")

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_SIZE = int(os.getenv("RAG_API_MAX_UPLOAD_SIZE", "10_485_760"))  # 10 MB default
UPLOAD_DIR = Path(os.getenv("RAG_API_UPLOAD_DIR", str(PROJECT_ROOT / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FORCE_MOCK = os.getenv("RAG_API_FORCE_MOCK", "true").lower() in ("true", "1", "yes")
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "250"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "50"))


SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class DocumentUploadResponse(BaseModel):
    status: str  # "indexed" | "partial" | "rejected"
    filename: str
    safe_filename: str
    document_id: str
    chunks_created: int
    chunks_indexed: int
    errors: List[str] = []
    notes: str = ""


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------

def validate_upload(file: UploadFile) -> Optional[str]:
    """Returns error message string if invalid, None if valid."""
    if not file.filename:
        return "No filename provided"

    # Sanitize filename
    if not SAFE_FILENAME_RE.match(file.filename):
        return f"Unsafe filename: {file.filename}"

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return f"Unsupported format '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"

    return None


async def save_upload(file: UploadFile) -> Path:
    """Save uploaded file to uploads/ with unique prefix to avoid overwrites."""
    safe_name = file.filename
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = UPLOAD_DIR / unique_name
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content)} bytes). Max: {MAX_UPLOAD_SIZE} bytes",
        )

    dest.write_bytes(content)
    return dest


# ---------------------------------------------------------------------------
# Ingest and index
# ---------------------------------------------------------------------------

def process_and_index(file_path: Path, client_id: str = "UPLOAD") -> DocumentUploadResponse:
    """Run ingestion pipeline, embed, and index into vector DB."""
    errors: List[str] = []
    clean_filename = file_path.name.split("_", 1)[-1]  # strip UUID prefix

    # 1. Run ingestion pipeline (load, clean, chunk)
    pipeline = IngestionPipeline(
        chunk_size_tokens=CHUNK_SIZE_TOKENS,
        chunk_overlap_tokens=CHUNK_OVERLAP_TOKENS,
    )

    # Ingest from single upload file using a temp corpus dir
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / clean_filename
        tmp_path.write_bytes(file_path.read_bytes())

        result = pipeline.run(tmpdir)
        chunks = result.chunks

        if not chunks:
            errors.append("No chunks generated from document")
            # Clean up tmp file
            file_path.unlink(missing_ok=True)
            return DocumentUploadResponse(
                status="rejected",
                filename=clean_filename,
                safe_filename=clean_filename,
                document_id="",
                chunks_created=0,
                chunks_indexed=0,
                errors=errors,
                notes="Document could not be parsed or had no extractable content.",
            )

        # 2. Embed chunks
        embedder = CorpusEmbedder(dimension=DEFAULT_EMBEDDING_DIM, force_mock=FORCE_MOCK)
        embedded = embedder.embed_chunks(chunks)

        # 3. Index into Vector DB
        config = load_vector_db_config()
        manager = VectorDatabaseManager(config)
        indexer = CorpusIndexer(manager=manager, embedder=embedder, force_mock=FORCE_MOCK)

        # Convert to VectorRecords and index (append to existing collection)
        from src.vector_db import VectorRecord, VectorRecordMetadata
        import datetime

        records: List[VectorRecord] = []
        for ec in embedded:
            meta = VectorRecordMetadata(
                source_document=ec.metadata.get("file_path") or ec.metadata.get("source_id") or clean_filename,
                document_id=ec.metadata.get("document_id") or ec.metadata.get("source_id") or clean_filename,
                chunk_index=int(ec.metadata.get("chunk_index", 0)),
                section=str(ec.metadata.get("section", "General")),
                page=int(ec.metadata.get("page", 1)),
                client_id=client_id,
                token_count=int(ec.metadata.get("token_count", 0)),
                char_count=len(ec.content),
            )
            vr = VectorRecord(
                record_id=ec.chunk_id,
                vector=[float(x) for x in ec.vector],
                document_text=ec.content,
                metadata=meta,
            )
            vr.validate(expected_dim=config.embedding_dimension)
            records.append(vr)

        stats = indexer.index_corpus(records, reset_existing=False)
        indexed_ok = stats.records_indexed

    # Clean up upload
    file_path.unlink(missing_ok=True)

    status = "indexed" if indexed_ok == len(records) else "partial"
    if indexed_ok == 0:
        status = "rejected"
        errors.append("Zero chunks successfully indexed")

    doc_id = chunks[0].metadata.document_id if chunks else clean_filename

    return DocumentUploadResponse(
        status=status,
        filename=clean_filename,
        safe_filename=clean_filename,
        document_id=doc_id,
        chunks_created=len(chunks),
        chunks_indexed=indexed_ok,
        errors=errors,
        notes=f"Document processed with client_id='{client_id}'. New chunks available immediately via /query.",
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload a document, validate, ingest, and index into the vector store."""

    # Validate
    error = validate_upload(file)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # Save
    try:
        saved_path = await save_upload(file)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to save upload")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # Process
    try:
        result = process_and_index(saved_path)
        return result
    except Exception as e:
        logger.exception("Failed to process upload")
        # Clean up on failure
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Internal error during document processing")
