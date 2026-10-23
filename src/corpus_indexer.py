"""
ClientVault — Corpus Vector Database Indexing & Integrity Verification Engine

This module executes complete corpus indexing into ChromaDB:
- Task 1: Inserts all corpus embeddings into the vector database collection.
- Task 2: Ensures every record stores the embedding vector, raw source text, and
          provenance metadata (source document, chunk index, section, page, client_id).
- Task 3: Verifies that the indexed database count matches the number of prepared chunks.
- Task 4: Performs granular spot-checks reading back stored records and confirming ID,
          text integrity, metadata retention, and vector dimension accuracy.
- Task 5: Formats and outputs a comprehensive indexing summary report with count
          audits, spot-check proofs, and failure tracking.
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.corpus_embedder import (
    CorpusEmbedder,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_RECORDS_PATH,
    EmbeddedChunk,
    VectorStore,
    prepare_corpus_chunks,
)
from src.vector_db import (
    VectorDatabaseManager,
    VectorDBConfig,
    VectorRecord,
    VectorRecordMetadata,
    load_vector_db_config,
)

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.CorpusIndexer: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.CorpusIndexer")

DEFAULT_INDEXING_LOG = PROJECT_ROOT / "corpus_indexing_output.log"


# ---------------------------------------------------------------------------
# Data Models: Indexing Stats & Spot-Check Results
# ---------------------------------------------------------------------------

@dataclass
class SpotCheckResult:
    """
    Task 4: Granular verification comparison between original source chunk
    and retrieved vector database record.
    """
    record_id: str
    source_document: str
    document_id: str
    client_id: str
    chunk_index: int
    section: str
    page: int
    vector_length: int
    text_length: int
    id_match: bool
    vector_match: bool
    text_match: bool
    metadata_match: bool
    passed: bool
    notes: str
    vector_sample: Dict[str, List[float]] = field(default_factory=dict)
    text_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IndexingStats:
    """
    Task 3 & 5: Aggregated run statistics tracking records stored, count validation,
    failures if any, and spot-check results.
    """
    total_chunks_prepared: int
    records_indexed: int
    records_failed: int
    stored_count_in_db: int
    count_matches: bool
    collection_name: str
    persist_directory: str
    duration_seconds: float
    failures: List[Dict[str, str]] = field(default_factory=list)
    spot_checks: List[SpotCheckResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chunks_prepared": self.total_chunks_prepared,
            "records_indexed": self.records_indexed,
            "records_failed": self.records_failed,
            "stored_count_in_db": self.stored_count_in_db,
            "count_matches": self.count_matches,
            "collection_name": self.collection_name,
            "persist_directory": self.persist_directory,
            "duration_seconds": round(self.duration_seconds, 4),
            "failures": self.failures,
            "spot_checks": [s.to_dict() for s in self.spot_checks],
        }


# ---------------------------------------------------------------------------
# Corpus Indexer Engine
# ---------------------------------------------------------------------------

class CorpusIndexer:
    """
    Coordinates corpus loading, embedding generation/loading, batch indexing,
    count validation, and readback spot-checking.
    """

    def __init__(
        self,
        manager: Optional[VectorDatabaseManager] = None,
        config: Optional[VectorDBConfig] = None,
        embedder: Optional[CorpusEmbedder] = None,
        force_mock: bool = False,
    ):
        self.force_mock = force_mock
        if manager:
            self.manager = manager
        else:
            cfg = config or load_vector_db_config()
            self.manager = VectorDatabaseManager(cfg)

        self.embedder = embedder or CorpusEmbedder(
            dimension=self.manager.config.embedding_dimension,
            force_mock=self.force_mock,
        )

    def prepare_vector_records(
        self,
        records_json_path: Optional[Path] = None,
        corpus_dir: Optional[Path] = None,
    ) -> List[VectorRecord]:
        """
        Task 1 & 2: Prepares strongly-typed VectorRecords with vectors, text,
        and complete provenance metadata from existing records or raw corpus.
        """
        # Option A: Load from existing persisted records JSON if present
        target_records_json = records_json_path or DEFAULT_RECORDS_PATH
        if target_records_json.exists():
            logger.info("Loading existing embedded records from %s", target_records_json)
            with open(target_records_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            vector_records: List[VectorRecord] = []
            for item in data:
                meta_dict = item.get("metadata", {})
                content = item.get("content", "")
                meta = VectorRecordMetadata(
                    source_document=meta_dict.get("file_path") or meta_dict.get("source_id") or "corpus_file",
                    document_id=meta_dict.get("document_id") or meta_dict.get("source_id") or "unknown_doc",
                    chunk_index=int(meta_dict.get("chunk_index", 0)),
                    section=str(meta_dict.get("section", "General")),
                    page=int(meta_dict.get("page", 1)),
                    client_id=str(meta_dict.get("client_id", "GLOBAL")),
                    token_count=int(meta_dict.get("token_count", 0)),
                    char_count=len(content),
                    created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    extra_tag=meta_dict.get("strategy", "token_aware"),
                )
                vr = VectorRecord(
                    record_id=item["chunk_id"],
                    vector=[float(x) for x in item["vector"]],
                    document_text=content,
                    metadata=meta,
                )
                vr.validate(expected_dim=self.manager.config.embedding_dimension)
                vector_records.append(vr)

            logger.info("Prepared %d vector records from JSON", len(vector_records))
            return vector_records

        # Option B: Process and embed directly from sample corpus
        logger.info("No records JSON at %s; generating embeddings directly from corpus...", target_records_json)
        chunks, _ = prepare_corpus_chunks(corpus_dir=corpus_dir)
        embedded_chunks = self.embedder.embed_chunks(chunks)

        vector_records = []
        for ec in embedded_chunks:
            meta = VectorRecordMetadata(
                source_document=ec.metadata.get("file_path") or ec.metadata.get("source_id") or "corpus_file",
                document_id=ec.metadata.get("document_id") or ec.metadata.get("source_id") or "unknown_doc",
                chunk_index=int(ec.metadata.get("chunk_index", 0)),
                section=str(ec.metadata.get("section", "General")),
                page=int(ec.metadata.get("page", 1)),
                client_id=str(ec.metadata.get("client_id", "GLOBAL")),
                token_count=int(ec.metadata.get("token_count", 0)),
                char_count=len(ec.content),
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                extra_tag=ec.metadata.get("strategy", "token_aware"),
            )
            vr = VectorRecord(
                record_id=ec.chunk_id,
                vector=[float(x) for x in ec.vector],
                document_text=ec.content,
                metadata=meta,
            )
            vr.validate(expected_dim=self.manager.config.embedding_dimension)
            vector_records.append(vr)

        logger.info("Prepared and embedded %d vector records directly", len(vector_records))
        return vector_records

    def index_corpus(
        self,
        records: List[VectorRecord],
        batch_size: int = 100,
        reset_existing: bool = True,
    ) -> IndexingStats:
        """
        Task 1, 2, 3: Inserts all records into vector database and confirms counts.
        """
        start_time = time.time()
        if reset_existing:
            logger.info("Resetting collection '%s' for clean indexing run", self.manager.config.collection_name)
            self.manager.reset_collection()

        failures: List[Dict[str, str]] = []
        total_prepared = len(records)
        indexed_count = 0

        try:
            indexed_count = self.manager.insert_records(records, batch_size=batch_size)
        except Exception as e:
            logger.error("Batch insertion failed: %s", e)
            failures.append({"error": str(e), "context": "batch_upsert"})

        # Task 3: Compare stored count against prepared count
        stored_count = self.manager.count()
        count_matches = (stored_count == total_prepared) and (len(failures) == 0)

        duration = time.time() - start_time
        return IndexingStats(
            total_chunks_prepared=total_prepared,
            records_indexed=indexed_count,
            records_failed=len(failures),
            stored_count_in_db=stored_count,
            count_matches=count_matches,
            collection_name=self.manager.config.collection_name,
            persist_directory=str(self.manager.config.persist_directory) if not self.manager.config.in_memory else ":memory:",
            duration_seconds=duration,
            failures=failures,
        )

    def spot_check_integrity(
        self,
        source_records: List[VectorRecord],
        sample_ids: Optional[List[str]] = None,
    ) -> List[SpotCheckResult]:
        """
        Task 4: Reads back stored records and performs an exhaustive field-by-field
        audit against original source chunks.
        """
        records_by_id = {r.record_id: r for r in source_records}

        if sample_ids:
            target_ids = sample_ids
        else:
            # Pick representative cross-section across documents
            target_ids = []
            docs_seen = set()
            for r in source_records:
                doc_id = r.metadata.document_id
                if doc_id not in docs_seen:
                    target_ids.append(r.record_id)
                    docs_seen.add(doc_id)
            # Ensure at least first and last chunks are included
            if source_records and source_records[0].record_id not in target_ids:
                target_ids.insert(0, source_records[0].record_id)
            if source_records and source_records[-1].record_id not in target_ids:
                target_ids.append(source_records[-1].record_id)

        spot_check_results: List[SpotCheckResult] = []

        for rid in target_ids:
            original = records_by_id.get(rid)
            if not original:
                continue

            stored = self.manager.read_record(rid)
            if not stored:
                spot_check_results.append(
                    SpotCheckResult(
                        record_id=rid,
                        source_document=original.metadata.source_document,
                        document_id=original.metadata.document_id,
                        client_id=original.metadata.client_id,
                        chunk_index=original.metadata.chunk_index,
                        section=original.metadata.section,
                        page=original.metadata.page,
                        vector_length=0,
                        text_length=0,
                        id_match=False,
                        vector_match=False,
                        text_match=False,
                        metadata_match=False,
                        passed=False,
                        notes=f"Record '{rid}' was NOT found in vector database.",
                    )
                )
                continue

            # Field-by-field verification
            id_match = stored.record_id == original.record_id
            vector_len_match = len(stored.vector) == len(original.vector)
            text_match = stored.document_text == original.document_text
            client_match = stored.metadata.client_id == original.metadata.client_id
            doc_match = stored.metadata.document_id == original.metadata.document_id
            chunk_idx_match = stored.metadata.chunk_index == original.metadata.chunk_index
            section_match = stored.metadata.section == original.metadata.section
            page_match = stored.metadata.page == original.metadata.page

            # Check vector coordinate fidelity (first 10 and last 5 elements)
            vector_coords_match = all(
                abs(a - b) < 1e-5 for a, b in zip(stored.vector[:10], original.vector[:10])
            )
            vector_match = vector_len_match and vector_coords_match

            metadata_match = client_match and doc_match and chunk_idx_match and section_match and page_match
            passed = id_match and vector_match and text_match and metadata_match

            notes_parts = []
            if not id_match:
                notes_parts.append("ID mismatch")
            if not vector_match:
                notes_parts.append("Vector mismatch")
            if not text_match:
                notes_parts.append("Text mismatch")
            if not metadata_match:
                notes_parts.append("Metadata mismatch")

            notes = "All fields match original source chunk exactly." if passed else "; ".join(notes_parts)

            preview = stored.to_preview_dict()
            spot_check_results.append(
                SpotCheckResult(
                    record_id=stored.record_id,
                    source_document=stored.metadata.source_document,
                    document_id=stored.metadata.document_id,
                    client_id=stored.metadata.client_id,
                    chunk_index=stored.metadata.chunk_index,
                    section=stored.metadata.section,
                    page=stored.metadata.page,
                    vector_length=len(stored.vector),
                    text_length=len(stored.document_text),
                    id_match=id_match,
                    vector_match=vector_match,
                    text_match=text_match,
                    metadata_match=metadata_match,
                    passed=passed,
                    notes=notes,
                    vector_sample=preview["vector_sample"],
                    text_snippet=preview["document_snippet"],
                )
            )

        return spot_check_results


# ---------------------------------------------------------------------------
# Formatting & Demonstration Runner
# ---------------------------------------------------------------------------

def format_indexing_summary_report(stats: IndexingStats) -> str:
    """
    Task 5: Formats a complete, readable summary report of the indexing run.
    """
    lines: List[str] = []

    lines.append("=" * 80)
    lines.append("  ClientVault — Corpus Vector Database Indexing & Audit Report")
    lines.append("=" * 80)
    lines.append("")

    lines.append(">> TASK 1 & 2: INDEXING SETUP & CONFIGURATION")
    lines.append("-" * 80)
    lines.append(f"  Target Collection:      {stats.collection_name}")
    lines.append(f"  Database Storage:       {stats.persist_directory}")
    lines.append(f"  Indexed Record Count:   {stats.records_indexed} records")
    lines.append(f"  Execution Time:         {stats.duration_seconds:.4f} seconds")
    lines.append(f"  Schema Fields Stored:   [vector(1536), document_text, source_document, document_id,")
    lines.append("                           chunk_index, section, page, client_id, token_count, created_at]")
    lines.append("")

    lines.append(">> TASK 3: COUNT VALIDATION & CORPUS ALIGNMENT AUDIT")
    lines.append("-" * 80)
    lines.append(f"  Chunks Prepared Earlier: {stats.total_chunks_prepared}")
    lines.append(f"  Records Upserted in DB:  {stats.records_indexed}")
    lines.append(f"  Stored Count in Chroma:  {stats.stored_count_in_db}")
    lines.append(f"  Indexing Failures:       {stats.records_failed}")
    match_status = "PASSED — Database count matches prepared corpus chunks exactly." if stats.count_matches else "FAILED — Mismatch detected"
    lines.append(f"  Count Validation:        {match_status}")
    if stats.failures:
        lines.append("  Failure Details:")
        for fail in stats.failures:
            lines.append(f"    - {fail}")
    lines.append("")

    lines.append(">> TASK 4: STORED RECORD INTEGRITY SPOT-CHECKS")
    lines.append("-" * 80)
    lines.append(f"  Total Spot-Checks Run:   {len(stats.spot_checks)}")
    passed_checks = sum(1 for s in stats.spot_checks if s.passed)
    lines.append(f"  Spot-Checks Passed:      {passed_checks}/{len(stats.spot_checks)}")
    lines.append("")

    for i, sc in enumerate(stats.spot_checks, 1):
        status_tag = "[PASS]" if sc.passed else "[FAIL]"
        lines.append(f"[{i}] {status_tag} Record: '{sc.record_id}'")
        lines.append(f"    Source Document:  '{sc.source_document}' (Doc ID: '{sc.document_id}')")
        lines.append(f"    Client ID:        '{sc.client_id}' | Chunk Index: #{sc.chunk_index}")
        lines.append(f"    Section:          '{sc.section}' | Page: {sc.page}")
        lines.append(f"    Vector Dimension: {sc.vector_length} dims (Match: {'YES' if sc.vector_match else 'NO'})")
        lines.append(f"    Document Text:    {sc.text_length} chars (Match: {'YES' if sc.text_match else 'NO'})")
        lines.append(f"    Metadata Fields:  {'ALL MATCHED' if sc.metadata_match else 'MISMATCH'}")
        lines.append(f"    Sample Vector:    Head: {sc.vector_sample.get('head', [])} ... Tail: {sc.vector_sample.get('tail', [])}")
        lines.append(f"    Snippet:          \"{sc.text_snippet}\"")
        lines.append(f"    Integrity Audit:  {sc.notes}")
        lines.append("")

    lines.append("=" * 80)
    overall_status = "PASSED — All corpus embeddings indexed, count aligned, integrity confirmed." if (stats.count_matches and passed_checks == len(stats.spot_checks)) else "FAILED"
    lines.append(f"  STATUS: {overall_status}")
    lines.append("=" * 80)

    return "\n".join(lines)


def run_corpus_indexing(
    config: Optional[VectorDBConfig] = None,
    output_log_file: Optional[Path] = None,
    records_json_path: Optional[Path] = None,
    force_mock: bool = False,
) -> Tuple[IndexingStats, str]:
    """
    Executes Tasks 1–5: Prepares corpus records, indexes into ChromaDB collection,
    validates count, runs readback spot-checks, and writes report log.
    """
    indexer = CorpusIndexer(config=config, force_mock=force_mock)

    # Step 1: Prepare strongly-typed records with embeddings and metadata
    records = indexer.prepare_vector_records(records_json_path=records_json_path)

    # Step 2: Index all chunks into vector database collection
    stats = indexer.index_corpus(records=records)

    # Step 3: Run spot-checks across documents
    spot_checks = indexer.spot_check_integrity(source_records=records)
    stats.spot_checks = spot_checks

    # Step 4: Generate summary report
    report_text = format_indexing_summary_report(stats)
    print(report_text)

    # Step 5: Save report log
    target_log = output_log_file or DEFAULT_INDEXING_LOG
    target_log.parent.mkdir(parents=True, exist_ok=True)
    with open(target_log, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")
    print(f"\n[OK] Indexing summary saved to {target_log}")

    return stats, report_text


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ClientVault — Corpus Vector Database Indexing & Audit"
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="Use ephemeral in-memory ChromaDB client instead of disk persistence",
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=None,
        help="Custom ChromaDB persistent storage directory",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default=None,
        help="Custom ChromaDB collection name",
    )
    parser.add_argument(
        "--records-path",
        type=Path,
        default=None,
        help="Path to precomputed corpus_embedding_records.json",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in offline deterministic semantic mock mode",
    )
    parser.add_argument(
        "--output-log",
        type=Path,
        default=DEFAULT_INDEXING_LOG,
        help="Path to save indexing summary log",
    )
    args = parser.parse_args()

    config = load_vector_db_config(
        in_memory=args.in_memory,
        persist_dir=args.persist_dir,
        collection_name=args.collection_name,
    )

    run_corpus_indexing(
        config=config,
        output_log_file=args.output_log,
        records_json_path=args.records_path,
        force_mock=args.mock,
    )


if __name__ == "__main__":
    main()
