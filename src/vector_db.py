"""
ClientVault — Vector Database Collection Setup & Record Persistence Engine

This module provides vector database management and semantic storage for ClientVault:
- Task 1: Initializes and confirms reachability of the vector database (ChromaDB)
          using environment configuration (.env) and local persistence directories.
- Task 2: Creates and configures a collection tailored with the exact vector dimension
          (1536 dims for text-embedding-3-small) and HNSW cosine distance metric.
- Task 3: Enforces a structured record schema storing the dense vector, raw source
          chunk text, and comprehensive provenance metadata (source_document,
          document_id, chunk_index, section, page, client_id, token_count).
- Task 4: Inserts and reads back a verified test record, validating ID, vector
          length, content integrity, and metadata retention.
- Task 5: Provides a verifiable CLI runner that generates and persists a complete
          readback verification summary report.
"""

import argparse
import datetime
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

from src.corpus_embedder import (
    CorpusEmbedder,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    load_embedding_config,
)

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.VectorDB: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.VectorDB")

DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_PERSIST_DIR = PROJECT_ROOT / "outputs" / "chroma_db"
DEFAULT_COLLECTION_NAME = "clientvault_knowledge_base"
DEFAULT_DISTANCE_METRIC = "cosine"
DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "vector_db_readback_output.log"


# ---------------------------------------------------------------------------
# Task 1: Configuration Management & Reachability
# ---------------------------------------------------------------------------

@dataclass
class VectorDBConfig:
    """
    Task 1: Vector database configuration loaded from environment or local defaults.
    """
    persist_directory: Path
    collection_name: str
    embedding_model: str
    embedding_dimension: int
    distance_metric: str = DEFAULT_DISTANCE_METRIC
    in_memory: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "persist_directory": str(self.persist_directory),
            "collection_name": self.collection_name,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "distance_metric": self.distance_metric,
            "in_memory": self.in_memory,
        }


def load_vector_db_config(
    env_path: Optional[Path] = None,
    in_memory: bool = False,
    persist_dir: Optional[Path] = None,
    collection_name: Optional[str] = None,
) -> VectorDBConfig:
    """
    Task 1: Reads vector database configuration from .env and environment variables.
    Never hardcodes paths or secrets directly.
    """
    target_env = env_path or DEFAULT_ENV_PATH
    if target_env.exists():
        load_dotenv(dotenv_path=target_env, override=False)
        logger.debug("Loaded environment variables from %s", target_env)

    # Resolve persist directory
    env_persist = os.getenv("CHROMA_PERSIST_DIRECTORY", "").strip()
    if persist_dir:
        resolved_dir = Path(persist_dir)
    elif env_persist:
        resolved_dir = Path(env_persist).resolve() if os.path.isabs(env_persist) else (PROJECT_ROOT / env_persist).resolve()
    else:
        resolved_dir = DEFAULT_PERSIST_DIR

    col_name = collection_name or os.getenv("CHROMA_COLLECTION_NAME", DEFAULT_COLLECTION_NAME).strip()
    model = os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()

    try:
        dim = int(os.getenv("EMBEDDING_DIMENSION", str(DEFAULT_EMBEDDING_DIM)))
    except ValueError:
        dim = DEFAULT_EMBEDDING_DIM

    return VectorDBConfig(
        persist_directory=resolved_dir,
        collection_name=col_name,
        embedding_model=model,
        embedding_dimension=dim,
        distance_metric=DEFAULT_DISTANCE_METRIC,
        in_memory=in_memory,
    )


# ---------------------------------------------------------------------------
# Task 3: Stored Record Schema
# ---------------------------------------------------------------------------

@dataclass
class VectorRecordMetadata:
    """
    Task 3: Retrieval provenance metadata schema.
    ChromaDB requires metadata values to be primitive types: str, int, float, bool.
    """
    source_document: str
    document_id: str
    chunk_index: int
    section: str
    page: int
    client_id: str
    token_count: int
    char_count: int
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    extra_tag: Optional[str] = None

    def to_chroma_dict(self) -> Dict[str, Union[str, int, float, bool]]:
        """Converts metadata to Chroma-compliant flat dictionary."""
        data: Dict[str, Union[str, int, float, bool]] = {
            "source_document": str(self.source_document),
            "document_id": str(self.document_id),
            "chunk_index": int(self.chunk_index),
            "section": str(self.section),
            "page": int(self.page),
            "client_id": str(self.client_id),
            "token_count": int(self.token_count),
            "char_count": int(self.char_count),
            "created_at": str(self.created_at),
        }
        if self.extra_tag is not None:
            data["extra_tag"] = str(self.extra_tag)
        return data

    @classmethod
    def from_chroma_dict(cls, data: Dict[str, Any]) -> "VectorRecordMetadata":
        """Instantiates metadata from stored Chroma dictionary."""
        return cls(
            source_document=str(data.get("source_document", "unknown")),
            document_id=str(data.get("document_id", "unknown")),
            chunk_index=int(data.get("chunk_index", 0)),
            section=str(data.get("section", "")),
            page=int(data.get("page", 1)),
            client_id=str(data.get("client_id", "GLOBAL")),
            token_count=int(data.get("token_count", 0)),
            char_count=int(data.get("char_count", 0)),
            created_at=str(data.get("created_at", "")),
            extra_tag=data.get("extra_tag"),
        )


@dataclass
class VectorRecord:
    """
    Task 3: Stored record schema encapsulating vector, source text, and metadata.
    """
    record_id: str
    vector: List[float]
    document_text: str
    metadata: VectorRecordMetadata

    def validate(self, expected_dim: Optional[int] = None) -> None:
        """Validates record integrity, dimension shape, and required fields."""
        if not self.record_id or not self.record_id.strip():
            raise ValueError("Record ID cannot be empty.")
        if not self.document_text or not self.document_text.strip():
            raise ValueError(f"Record '{self.record_id}' document text cannot be empty.")
        if not self.vector or len(self.vector) == 0:
            raise ValueError(f"Record '{self.record_id}' vector cannot be empty.")
        if expected_dim is not None and len(self.vector) != expected_dim:
            raise ValueError(
                f"Vector dimension mismatch for record '{self.record_id}': "
                f"expected {expected_dim}, got {len(self.vector)}"
            )
        if not self.metadata.client_id or not self.metadata.client_id.strip():
            raise ValueError(f"Record '{self.record_id}' missing required metadata: 'client_id'")

    def to_preview_dict(self, head_dims: int = 5, tail_dims: int = 3) -> Dict[str, Any]:
        """Provides a clean summary for verification reporting."""
        head_vals = [round(float(v), 4) for v in self.vector[:head_dims]]
        tail_vals = [round(float(v), 4) for v in self.vector[-tail_dims:]] if tail_dims > 0 else []
        snippet = self.document_text[:140].replace("\n", " ") + ("..." if len(self.document_text) > 140 else "")
        return {
            "record_id": self.record_id,
            "vector_dimension": len(self.vector),
            "vector_sample": {"head": head_vals, "tail": tail_vals},
            "document_snippet": snippet,
            "metadata": self.metadata.to_chroma_dict(),
        }


# ---------------------------------------------------------------------------
# Task 1 & 2 & 4: Vector Database Manager
# ---------------------------------------------------------------------------

class VectorDatabaseManager:
    """
    Manages ChromaDB client connection, collection lifecycle, record insertion,
    and retrieval operations.
    """

    def __init__(self, config: Optional[VectorDBConfig] = None):
        self.config = config or load_vector_db_config()
        self.client = self._init_client()
        self.collection = self._init_collection()

    def _init_client(self) -> chromadb.api.client.Client:
        """Task 1: Initializes persistent or in-memory Chroma client."""
        if self.config.in_memory:
            logger.info("Initializing ChromaDB EphemeralClient (In-Memory)")
            return chromadb.EphemeralClient()
        else:
            self.config.persist_directory.mkdir(parents=True, exist_ok=True)
            logger.info("Initializing ChromaDB PersistentClient at %s", self.config.persist_directory)
            return chromadb.PersistentClient(path=str(self.config.persist_directory))

    def _init_collection(self) -> chromadb.Collection:
        """
        Task 2: Creates or retrieves the correctly sized collection with HNSW
        cosine space and explicit dimension metadata.
        """
        col_metadata = {
            "hnsw:space": self.config.distance_metric,
            "dimension": self.config.embedding_dimension,
            "embedding_model": self.config.embedding_model,
            "description": "ClientVault client-isolated retrieval collection",
        }
        logger.info(
            "Configuring collection '%s' (dim=%d, metric='%s')",
            self.config.collection_name,
            self.config.embedding_dimension,
            self.config.distance_metric,
        )
        return self.client.get_or_create_collection(
            name=self.config.collection_name,
            metadata=col_metadata,
        )

    def check_reachability(self) -> Dict[str, Any]:
        """
        Task 1: Proves database is reachable and operational.
        """
        try:
            # Heartbeat check
            hb = self.client.heartbeat()
            count = self.collection.count()
            return {
                "status": "HEALTHY",
                "reachable": True,
                "heartbeat_ns": hb,
                "persist_directory": str(self.config.persist_directory) if not self.config.in_memory else ":memory:",
                "collection_name": self.config.collection_name,
                "record_count": count,
                "in_memory": self.config.in_memory,
            }
        except Exception as e:
            logger.error("ChromaDB reachability check failed: %s", e)
            return {
                "status": "UNREACHABLE",
                "reachable": False,
                "error": str(e),
            }

    def insert_record(self, record: VectorRecord) -> str:
        """
        Task 3 & 4: Validates and inserts a single VectorRecord into collection.
        """
        record.validate(expected_dim=self.config.embedding_dimension)

        self.collection.upsert(
            ids=[record.record_id],
            embeddings=[record.vector],
            documents=[record.document_text],
            metadatas=[record.metadata.to_chroma_dict()],
        )
        logger.debug("Successfully upserted record '%s'", record.record_id)
        return record.record_id

    def insert_records(self, records: List[VectorRecord], batch_size: int = 100) -> int:
        """
        Task 1 & 2: Validates and batch-upserts multiple VectorRecords into the collection.
        """
        if not records:
            return 0

        # Validate all records upfront
        for rec in records:
            rec.validate(expected_dim=self.config.embedding_dimension)

        total_upserted = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            self.collection.upsert(
                ids=[r.record_id for r in batch],
                embeddings=[r.vector for r in batch],
                documents=[r.document_text for r in batch],
                metadatas=[r.metadata.to_chroma_dict() for r in batch],
            )
            total_upserted += len(batch)
            logger.debug("Batch upserted %d/%d records", total_upserted, len(records))

        logger.info("Successfully indexed %d records into collection '%s'", total_upserted, self.config.collection_name)
        return total_upserted

    def read_record(self, record_id: str) -> Optional[VectorRecord]:
        """
        Task 4: Reads back a record by ID and reconstructs the strongly-typed VectorRecord.
        """
        res = self.collection.get(
            ids=[record_id],
            include=["embeddings", "documents", "metadatas"],
        )

        ids = res.get("ids", [])
        if not ids:
            return None

        # Chroma returns lists of items for matched IDs
        doc_text = res["documents"][0] if res.get("documents") else ""
        raw_embedding = res["embeddings"][0] if res.get("embeddings") is not None and len(res["embeddings"]) > 0 else []
        vector = [float(x) for x in raw_embedding] if hasattr(raw_embedding, "__iter__") else []
        raw_meta = res["metadatas"][0] if res.get("metadatas") else {}

        meta = VectorRecordMetadata.from_chroma_dict(raw_meta)
        return VectorRecord(
            record_id=ids[0],
            vector=vector,
            document_text=doc_text,
            metadata=meta,
        )

    def count(self) -> int:
        """Returns total records currently stored in collection."""
        return self.collection.count()

    def delete_record(self, record_id: str) -> None:
        """Deletes a record from the collection."""
        self.collection.delete(ids=[record_id])

    def reset_collection(self) -> None:
        """Clears and recreates collection for clean benchmarking."""
        self.client.delete_collection(name=self.config.collection_name)
        self.collection = self._init_collection()


# ---------------------------------------------------------------------------
# Task 4 & 5: Readback Verification & Benchmark Demonstration
# ---------------------------------------------------------------------------

def run_vector_db_demonstration(
    config: Optional[VectorDBConfig] = None,
    output_log_file: Optional[Path] = None,
    force_mock: bool = False,
) -> Tuple[VectorRecord, Dict[str, Any], str]:
    """
    Executes Tasks 1–5: Connects to vector database, creates collection,
    inserts test record, reads it back, verifies field equality, and logs report.
    """
    cfg = config or load_vector_db_config()
    manager = VectorDatabaseManager(cfg)

    logs: List[str] = []

    def emit(line: str = ""):
        logs.append(line)
        print(line)

    emit("=" * 80)
    emit("  ClientVault — Vector Database Collection Setup & Readback Audit")
    emit("=" * 80)
    emit()

    # Task 1: Confirm reachability
    emit(">> TASK 1: VECTOR DATABASE REACHABILITY & CONFIGURATION")
    emit("-" * 80)
    health = manager.check_reachability()
    emit(f"  Database Engine:        ChromaDB (v{chromadb.__version__})")
    emit(f"  Reachability Status:    {health['status']} (Heartbeat: {health.get('heartbeat_ns')})")
    emit(f"  Storage Mode:           {'In-Memory (Ephemeral)' if cfg.in_memory else 'Local Disk Persistence'}")
    emit(f"  Persist Directory:      {cfg.persist_directory}")
    masked_env_path = str(DEFAULT_ENV_PATH.relative_to(PROJECT_ROOT)) if DEFAULT_ENV_PATH.exists() else "System Env"
    emit(f"  Configuration Source:   Environment ({masked_env_path})")
    emit()

    # Task 2: Collection configuration
    emit(">> TASK 2: COLLECTION CREATION & VECTOR DIMENSION SIZING")
    emit("-" * 80)
    emit(f"  Collection Name:        {cfg.collection_name}")
    emit(f"  Target Dimension:       {cfg.embedding_dimension} dimensions (text-embedding-3-small)")
    emit(f"  Distance Metric:        {cfg.distance_metric} (HNSW Cosine Space)")
    emit(f"  Collection Metadata:    {manager.collection.metadata}")
    emit(f"  Initial Record Count:   {manager.count()} records")
    emit()

    # Task 3: Design record schema & generate realistic embedding
    emit(">> TASK 3: STORED RECORD SCHEMA & PAYLOAD PREPARATION")
    emit("-" * 80)
    test_record_id = "acme_onboarding#tok_001_test"
    test_document_text = (
        "Notice: Copyright (c) 2026 ACME Logistics Inc. All Rights Reserved. "
        "Page 2 of 4 — CONFIDENTIAL — ACME LOGISTICS INC. "
        "## 3. Provisioning Procedure\n"
        "### Step 3.1: Sponsor Verification\n"
        "Before generating credentials, verify identity via the primary sponsor directory `SEC-ONB`."
    )
    test_meta = VectorRecordMetadata(
        source_document="acme_onboarding.md",
        document_id="acme_onboarding",
        chunk_index=1,
        section="Step 3.1: Sponsor Verification",
        page=2,
        client_id="ACME-001",
        token_count=64,
        char_count=len(test_document_text),
        extra_tag="test_readback_verification",
    )

    # Generate authentic vector using embedder
    embedder = CorpusEmbedder(dimension=cfg.embedding_dimension, force_mock=force_mock)
    vectors = embedder.embed_texts([test_document_text])
    test_vector = vectors[0]

    record_to_insert = VectorRecord(
        record_id=test_record_id,
        vector=test_vector,
        document_text=test_document_text,
        metadata=test_meta,
    )

    emit(f"  Record ID:              '{record_to_insert.record_id}'")
    emit(f"  Document Text Length:   {len(record_to_insert.document_text)} characters")
    emit(f"  Generated Vector Dim:   {len(record_to_insert.vector)} dimensions")
    emit(f"  Metadata Fields Schema: {list(record_to_insert.metadata.to_chroma_dict().keys())}")
    emit()

    # Task 4: Insert and read back record
    emit(">> TASK 4: INSERTION & READBACK VERIFICATION")
    emit("-" * 80)
    inserted_id = manager.insert_record(record_to_insert)
    emit(f"  [INSERT] Upserted record '{inserted_id}' into collection '{cfg.collection_name}'.")

    readback_record = manager.read_record(inserted_id)
    if readback_record is None:
        raise RuntimeError(f"Failed to read back record '{inserted_id}' from ChromaDB.")

    # Verification assertions
    id_match = readback_record.record_id == test_record_id
    dim_match = len(readback_record.vector) == cfg.embedding_dimension
    text_match = readback_record.document_text == test_document_text
    client_match = readback_record.metadata.client_id == "ACME-001"
    doc_match = readback_record.metadata.document_id == "acme_onboarding"
    section_match = readback_record.metadata.section == "Step 3.1: Sponsor Verification"

    all_passed = id_match and dim_match and text_match and client_match and doc_match and section_match

    emit(f"  [READBACK] Successfully retrieved record '{readback_record.record_id}' from database.")
    emit()
    emit("  Verification Audit Checklist:")
    emit(f"    * Record ID Match:        {'PASSED' if id_match else 'FAILED'} ('{readback_record.record_id}')")
    emit(f"    * Vector Length Match:    {'PASSED' if dim_match else 'FAILED'} ({len(readback_record.vector)} dims == {cfg.embedding_dimension})")
    emit(f"    * Text Integrity Match:   {'PASSED' if text_match else 'FAILED'} ({len(readback_record.document_text)} chars exact match)")
    emit(f"    * Client ID Isolation:    {'PASSED' if client_match else 'FAILED'} (client_id='{readback_record.metadata.client_id}')")
    emit(f"    * Document Provenance:    {'PASSED' if doc_match else 'FAILED'} (document_id='{readback_record.metadata.document_id}')")
    emit(f"    * Section Retention:      {'PASSED' if section_match else 'FAILED'} (section='{readback_record.metadata.section}')")
    emit()

    preview = readback_record.to_preview_dict()
    emit(">> READBACK RECORD DETAILS")
    emit("-" * 80)
    emit(f"  ID:                     {preview['record_id']}")
    emit(f"  Vector Dimension:       {preview['vector_dimension']}")
    emit(f"  Sample Coordinates:     Head: {preview['vector_sample']['head']} ... Tail: {preview['vector_sample']['tail']}")
    emit(f"  Source Document:        {preview['metadata']['source_document']}")
    emit(f"  Document ID:            {preview['metadata']['document_id']}")
    emit(f"  Client ID:              {preview['metadata']['client_id']}")
    emit(f"  Chunk Index:            {preview['metadata']['chunk_index']}")
    emit(f"  Section:                {preview['metadata']['section']}")
    emit(f"  Page:                   {preview['metadata']['page']}")
    emit(f"  Token Count:            {preview['metadata']['token_count']}")
    emit(f"  Created At:             {preview['metadata']['created_at']}")
    emit(f"  Document Snippet:       \"{preview['document_snippet']}\"")
    emit()

    emit("=" * 80)
    status_str = "PASSED — Vector database reachable, collection configured, record verified." if all_passed else "FAILED"
    emit(f"  STATUS: {status_str}")
    emit("=" * 80)

    report_text = "\n".join(logs)

    # Persist output log
    target_log = output_log_file or DEFAULT_OUTPUT_LOG
    target_log.parent.mkdir(parents=True, exist_ok=True)
    with open(target_log, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")
    print(f"\n[OK] Vector DB readback summary saved to {target_log}")

    audit_summary = {
        "status": status_str,
        "health": health,
        "collection": cfg.collection_name,
        "dimension": cfg.embedding_dimension,
        "record_id": readback_record.record_id,
        "vector_dim": len(readback_record.vector),
        "all_checks_passed": all_passed,
    }

    return readback_record, audit_summary, report_text


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ClientVault — Vector Database Collection Setup & Readback Audit"
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="Use ChromaDB EphemeralClient (In-Memory) instead of persistent disk storage",
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=None,
        help="Custom directory path for ChromaDB persistent storage",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default=DEFAULT_COLLECTION_NAME,
        help="Custom Chroma collection name",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock embeddings for offline verification",
    )
    parser.add_argument(
        "--output-log",
        type=Path,
        default=DEFAULT_OUTPUT_LOG,
        help="Path to save readback audit output log",
    )
    args = parser.parse_args()

    config = load_vector_db_config(
        in_memory=args.in_memory,
        persist_dir=args.persist_dir,
        collection_name=args.collection_name,
    )

    run_vector_db_demonstration(
        config=config,
        output_log_file=args.output_log,
        force_mock=args.mock,
    )


if __name__ == "__main__":
    main()
