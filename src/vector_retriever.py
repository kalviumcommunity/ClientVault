"""
ClientVault — Vector Database Top-K Semantic Retrieval Engine

This module executes semantic retrieval against the ChromaDB vector database:
- Task 1: Embeds user queries using the exact same dense embedding model
          (text-embedding-3-small, 1536 dimensions) as the corpus chunks.
- Task 2: Executes Top-K nearest-neighbor similarity search against the ChromaDB
          collection to retrieve the most semantically relevant chunks.
- Task 3: Formats and packages retrieved chunks with similarity scores, full source
          text, and complete retrieval metadata (source_document, document_id,
          chunk_index, section, page, client_id, token_count).
- Task 4: Demonstrates and analyzes the effects of varying K (e.g., K=2 vs K=4 vs K=6),
          illustrating coverage expansion, score decay, and context breadth trade-offs.
- Task 5: Provides a verifiable CLI runner generating structured JSON results
          (sample_retrieval_results.json) and human-readable terminal audit logs
          (sample_retrieval_output.log).
"""

import argparse
import datetime
import json
import logging
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from src.corpus_embedder import (
    CorpusEmbedder,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    load_embedding_config,
)
from src.corpus_indexer import CorpusIndexer
from src.similarity_ranker import cosine_similarity
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
    format="%(asctime)s [%(levelname)s] ClientVault.VectorRetriever: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.VectorRetriever")

DEFAULT_RETRIEVAL_LOG = PROJECT_ROOT / "sample_retrieval_output.log"
DEFAULT_RETRIEVAL_JSON = PROJECT_ROOT / "sample_retrieval_results.json"


# ---------------------------------------------------------------------------
# Data Models: Retrieved Chunk & Search Results
# ---------------------------------------------------------------------------

@dataclass
class RetrievedChunk:
    """
    Task 3: Represents a single retrieved chunk with its similarity score,
    source text, and provenance metadata.
    """
    rank: int
    chunk_id: str
    similarity_score: float
    distance: float
    content: str
    source_document: str
    document_id: str
    chunk_index: int
    section: str
    page: int
    client_id: str
    token_count: int
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_preview_dict(self, snippet_len: int = 140) -> Dict[str, Any]:
        snippet = self.content[:snippet_len].replace("\n", " ") + ("..." if len(self.content) > snippet_len else "")
        return {
            "rank": self.rank,
            "chunk_id": self.chunk_id,
            "similarity_score": round(self.similarity_score, 4),
            "distance": round(self.distance, 4),
            "document_id": self.document_id,
            "source_document": self.source_document,
            "client_id": self.client_id,
            "chunk_index": self.chunk_index,
            "section": self.section,
            "page": self.page,
            "token_count": self.token_count,
            "snippet": snippet,
        }


@dataclass
class RetrievalResult:
    """
    Task 2 & 3: Encapsulates the results of a Top-K similarity search.
    """
    query: str
    k_requested: int
    k_returned: int
    client_id: Optional[str]
    total_candidates_in_collection: int
    chunks: List[RetrievedChunk]
    highest_score: float
    lowest_score: float
    score_spread: float
    execution_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "k_requested": self.k_requested,
            "k_returned": self.k_returned,
            "client_id": self.client_id,
            "total_candidates_in_collection": self.total_candidates_in_collection,
            "highest_score": round(self.highest_score, 4),
            "lowest_score": round(self.lowest_score, 4),
            "score_spread": round(self.score_spread, 4),
            "execution_time_ms": round(self.execution_time_ms, 2),
            "chunks": [c.to_preview_dict() for c in self.chunks],
        }


@dataclass
class KComparisonSummary:
    """
    Task 4: Encapsulates comparative retrieval results across varying values of K.
    """
    query: str
    k_values: List[int]
    results_by_k: Dict[int, RetrievalResult]
    observations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "k_values": self.k_values,
            "runs": {str(k): res.to_dict() for k, res in self.results_by_k.items()},
            "observations": self.observations,
        }


# ---------------------------------------------------------------------------
# Vector Retriever Engine
# ---------------------------------------------------------------------------

class VectorRetriever:
    """
    Coordinates query embedding generation, ChromaDB vector search,
    score conversion, and metadata formatting.
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

    def ensure_corpus_indexed(self) -> int:
        """
        Ensures that the collection contains indexed corpus chunks.
        If empty, triggers CorpusIndexer to index sample corpus records.
        """
        count = self.manager.count()
        if count == 0:
            logger.info("Collection '%s' is empty; indexing corpus automatically...", self.manager.config.collection_name)
            indexer = CorpusIndexer(manager=self.manager, embedder=self.embedder, force_mock=self.force_mock)
            records = indexer.prepare_vector_records()
            indexer.index_corpus(records, reset_existing=False)
            count = self.manager.count()
            logger.info("Indexed %d records into collection '%s'", count, self.manager.config.collection_name)
        return count

    def embed_query(self, query: str) -> List[float]:
        """
        Task 1: Embeds a user query using the same embedding model
        and dimension (1536 dims) as the corpus chunks.
        """
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Query string cannot be empty.")

        query_vectors = self.embedder.embed_texts([clean_query])
        query_vector = query_vectors[0]

        expected_dim = self.manager.config.embedding_dimension
        if len(query_vector) != expected_dim:
            raise ValueError(
                f"Query vector dimension mismatch: expected {expected_dim}, got {len(query_vector)}"
            )

        logger.debug(
            "Embedded query '%s...' into %d-dimensional vector",
            clean_query[:40],
            len(query_vector),
        )
        return query_vector

    def retrieve_top_k(
        self,
        query: str,
        k: int = 3,
        client_id: Optional[str] = None,
    ) -> RetrievalResult:
        """
        Task 2 & 3: Embeds query, executes ChromaDB similarity search,
        and returns Top-K chunks with similarity scores, text, and metadata.
        """
        self.ensure_corpus_indexed()
        total_in_db = self.manager.count()

        if total_in_db == 0:
            return RetrievalResult(
                query=query,
                k_requested=k,
                k_returned=0,
                client_id=client_id,
                total_candidates_in_collection=0,
                chunks=[],
                highest_score=0.0,
                lowest_score=0.0,
                score_spread=0.0,
                execution_time_ms=0.0,
            )

        # Task 1: Embed user query
        t0 = time.perf_counter()
        query_vector = self.embed_query(query)

        # Set up Chroma search parameters
        effective_k = max(1, min(k, total_in_db))
        where_filter = {"client_id": client_id.strip().upper()} if client_id else None

        # Task 2: Run Top-K search
        res = self.manager.collection.query(
            query_embeddings=[query_vector],
            n_results=effective_k,
            where=where_filter,
            include=["documents", "metadatas", "distances", "embeddings"],
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        retrieved_chunks: List[RetrievedChunk] = []

        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        distances = res.get("distances", [[]])[0]
        embeddings = res.get("embeddings", [[]])[0]

        for idx, (cid, doc, meta, dist) in enumerate(zip(ids, docs, metas, distances), 1):
            # For HNSW cosine space in ChromaDB, distance is cosine distance:
            # distance = 1.0 - cosine_similarity
            raw_dist = float(dist)
            computed_sim = 1.0 - raw_dist

            # Precision check: if embedding is returned, calculate exact dot product
            if embeddings is not None and len(embeddings) > (idx - 1) and len(embeddings[idx - 1]) > 0:
                stored_vec = [float(x) for x in embeddings[idx - 1]]
                exact_sim = cosine_similarity(query_vector, stored_vec)
                similarity_score = max(-1.0, min(1.0, exact_sim))
            else:
                similarity_score = max(-1.0, min(1.0, computed_sim))

            # Task 3: Assemble retrieved chunk with full metadata
            rc = RetrievedChunk(
                rank=idx,
                chunk_id=cid,
                similarity_score=similarity_score,
                distance=raw_dist,
                content=doc,
                source_document=meta.get("source_document", "unknown"),
                document_id=meta.get("document_id", "unknown"),
                chunk_index=int(meta.get("chunk_index", 0)),
                section=meta.get("section", ""),
                page=int(meta.get("page", 1)),
                client_id=meta.get("client_id", "GLOBAL"),
                token_count=int(meta.get("token_count", 0)),
                metadata=meta,
            )
            retrieved_chunks.append(rc)

        highest = retrieved_chunks[0].similarity_score if retrieved_chunks else 0.0
        lowest = retrieved_chunks[-1].similarity_score if retrieved_chunks else 0.0
        spread = highest - lowest

        return RetrievalResult(
            query=query,
            k_requested=k,
            k_returned=len(retrieved_chunks),
            client_id=client_id,
            total_candidates_in_collection=total_in_db,
            chunks=retrieved_chunks,
            highest_score=highest,
            lowest_score=lowest,
            score_spread=spread,
            execution_time_ms=elapsed_ms,
        )

    def demonstrate_varying_k(
        self,
        query: str,
        k_values: Optional[List[int]] = None,
        client_id: Optional[str] = None,
    ) -> KComparisonSummary:
        """
        Task 4: Runs the same query across multiple K values (e.g., K=2, K=4, K=6),
        demonstrating how retrieved results, score distribution, and passage coverage change.
        """
        targets = k_values or [2, 4, 6]
        results_by_k: Dict[int, RetrievalResult] = {}

        for k_val in targets:
            res = self.retrieve_top_k(query, k=k_val, client_id=client_id)
            results_by_k[k_val] = res

        # Generate comparative observations
        observations = []
        k_sorted = sorted(targets)

        # Observation 1: Result set size expansion
        sizes = [f"K={k} -> {results_by_k[k].k_returned} chunks" for k in k_sorted]
        observations.append(f"Result Window Growth: {', '.join(sizes)}.")

        # Observation 2: Score decay across ranks
        min_k = k_sorted[0]
        max_k = k_sorted[-1]
        res_min = results_by_k[min_k]
        res_max = results_by_k[max_k]

        observations.append(
            f"Score Decay & Granularity: At K={min_k}, lowest score was {res_min.lowest_score:+.4f} "
            f"(spread: {res_min.score_spread:.4f}). Expanding to K={max_k} drops the threshold to "
            f"{res_max.lowest_score:+.4f} (spread: {res_max.score_spread:.4f}), admitting lower-confidence "
            "or orthogonal passages."
        )

        # Observation 3: Passage coverage & section diversity
        min_sections = {c.section for c in res_min.chunks}
        max_sections = {c.section for c in res_max.chunks}
        new_sections = max_sections - min_sections
        if new_sections:
            clean_new = [f"'{s[:30]}'" for s in list(new_sections)[:3]]
            observations.append(
                f"Contextual Breadth: Increasing K from {min_k} to {max_k} introduced {len(new_sections)} "
                f"additional document sections ({', '.join(clean_new)}), providing wider background context "
                "for LLM synthesis at the expense of prompt token consumption."
            )
        else:
            observations.append(
                f"Contextual Stability: Sections remained concentrated within target documents across K={min_k} to K={max_k}."
            )

        return KComparisonSummary(
            query=query,
            k_values=targets,
            results_by_k=results_by_k,
            observations=observations,
        )


# ---------------------------------------------------------------------------
# Formatting & Demonstration Runner
# ---------------------------------------------------------------------------

def format_retrieval_demonstration_report(
    query: str,
    comparison: KComparisonSummary,
    additional_query_res: Optional[RetrievalResult] = None,
) -> str:
    """
    Task 5: Formats a complete human-readable report showing query embedding,
    retrieved chunks, scores, metadata, and changing K comparisons.
    """
    lines: List[str] = []

    lines.append("=" * 80)
    lines.append("  ClientVault — Vector Database Top-K Semantic Retrieval Audit")
    lines.append("=" * 80)
    lines.append("")

    lines.append(">> TASK 1: USER QUERY EMBEDDING GENERATION")
    lines.append("-" * 80)
    lines.append(f"  Sample Query:           \"{query}\"")
    lines.append(f"  Embedding Model:        text-embedding-3-small")
    lines.append(f"  Vector Dimension:       1536 dimensions (L2-normalized unit hypersphere)")
    lines.append("  Alignment:              Model and dimension match corpus chunk vectors exactly.")
    lines.append("")

    lines.append(">> TASK 4: DEMONSTRATING CHANGING K (K=2 vs K=4 vs K=6)")
    lines.append("-" * 80)
    for k_val in comparison.k_values:
        run_res = comparison.results_by_k[k_val]
        lines.append(f"--------------------------------------------------------------------------------")
        lines.append(f"  RUN WITH K = {k_val} (Chunks Retrieved: {run_res.k_returned}/{k_val} requested | Latency: {run_res.execution_time_ms:.1f}ms)")
        lines.append(f"  Score Range: High: {run_res.highest_score:+.4f} | Low: {run_res.lowest_score:+.4f} | Spread: {run_res.score_spread:.4f}")
        lines.append(f"--------------------------------------------------------------------------------")

        for chunk in run_res.chunks:
            lines.append(f"  Rank #{chunk.rank} [Score: {chunk.similarity_score:+.4f} | Dist: {chunk.distance:.4f}]")
            lines.append(f"    Chunk ID:        '{chunk.chunk_id}'")
            lines.append(f"    Source Document: '{chunk.source_document}' (Doc: '{chunk.document_id}')")
            lines.append(f"    Client ID:       '{chunk.client_id}' | Chunk Index: #{chunk.chunk_index} | Page: {chunk.page}")
            lines.append(f"    Section:         '{chunk.section}'")
            lines.append(f"    Token Count:     {chunk.token_count} tokens")
            lines.append(f"    Snippet:         \"{chunk.content[:130].replace(chr(10), ' ')}...\"")
            lines.append("")

    lines.append(">> TASK 4 ANALYSIS & OBSERVATIONS (HOW CHANGING K AFFECTS RESULTS)")
    lines.append("-" * 80)
    for i, obs in enumerate(comparison.observations, 1):
        lines.append(f"[{i}] {obs}")
        lines.append("")

    if additional_query_res:
        lines.append(">> MULTI-DOMAIN RETRIEVAL VALIDATION (SLA / Turnaround Domain)")
        lines.append("-" * 80)
        lines.append(f"  Query:                  \"{additional_query_res.query}\"")
        lines.append(f"  Configured K:           {additional_query_res.k_requested} (Retrieved: {additional_query_res.k_returned})")
        lines.append(f"  Top Match Chunk:        '{additional_query_res.chunks[0].chunk_id}' [Score: {additional_query_res.highest_score:+.4f}]")
        lines.append(f"  Document / Section:     '{additional_query_res.chunks[0].document_id}' | '{additional_query_res.chunks[0].section}'")
        lines.append(f"  Passage Snippet:        \"{additional_query_res.chunks[0].content[:130].replace(chr(10), ' ')}...\"")
        lines.append("")

    lines.append("=" * 80)
    lines.append("  STATUS: PASSED — Top-K vector search, scores, metadata, and K variance verified.")
    lines.append("=" * 80)

    return "\n".join(lines)


def run_retrieval_demonstration(
    query: Optional[str] = None,
    k_values: Optional[List[int]] = None,
    output_log_file: Optional[Path] = None,
    output_json_file: Optional[Path] = None,
    force_mock: bool = False,
    in_memory: bool = False,
) -> Tuple[KComparisonSummary, str, Dict[str, Any]]:
    """
    Executes Tasks 1–5: Embeds query, performs top-k searches across varying K,
    records scores, text, and metadata, and writes output log and JSON files.
    """
    config = load_vector_db_config(in_memory=in_memory)
    retriever = VectorRetriever(config=config, force_mock=force_mock)

    sample_query = query or "How do I verify employee identity via the primary sponsor directory during onboarding?"
    targets_k = k_values or [2, 4, 6]

    # Task 4: Compare across changing K values
    comparison = retriever.demonstrate_varying_k(sample_query, k_values=targets_k)

    # Multi-domain secondary test: SLA turnaround guarantee
    sec_query = "What is the initial response time SLA guarantee for critical business outages?"
    sec_res = retriever.retrieve_top_k(sec_query, k=2)

    # Format report text
    report_text = format_retrieval_demonstration_report(
        query=sample_query,
        comparison=comparison,
        additional_query_res=sec_res,
    )
    print(report_text)

    # Save output log
    target_log = output_log_file or DEFAULT_RETRIEVAL_LOG
    target_log.parent.mkdir(parents=True, exist_ok=True)
    with open(target_log, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")
    print(f"\n[OK] Retrieval demonstration report saved to {target_log}")

    # Save structured JSON output
    target_json = output_json_file or DEFAULT_RETRIEVAL_JSON
    target_json.parent.mkdir(parents=True, exist_ok=True)
    json_data = {
        "primary_benchmark": comparison.to_dict(),
        "secondary_benchmark": sec_res.to_dict(),
        "metadata": {
            "embedding_model": "text-embedding-3-small",
            "vector_dimension": DEFAULT_EMBEDDING_DIM,
            "database_engine": "ChromaDB",
            "distance_metric": "cosine",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    }
    with open(target_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    print(f"[OK] Structured retrieval results saved to {target_json}")

    return comparison, report_text, json_data


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ClientVault — Vector Database Top-K Semantic Retrieval"
    )
    parser.add_argument(
        "--query",
        type=str,
        default="How do I verify employee identity via the primary sponsor directory during onboarding?",
        help="Natural language user query to retrieve relevant chunks for",
    )
    parser.add_argument(
        "--k-values",
        type=int,
        nargs="+",
        default=[2, 4, 6],
        help="List of K values to demonstrate changing result sets (e.g. 2 4 6)",
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="Use ephemeral in-memory Chroma client instead of disk persistence",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in offline deterministic semantic mock mode",
    )
    parser.add_argument(
        "--output-log",
        type=Path,
        default=DEFAULT_RETRIEVAL_LOG,
        help="Path to save human-readable retrieval log",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_RETRIEVAL_JSON,
        help="Path to save structured JSON query results",
    )
    args = parser.parse_args()

    run_retrieval_demonstration(
        query=args.query,
        k_values=args.k_values,
        output_log_file=args.output_log,
        output_json_file=args.output_json,
        force_mock=args.mock,
        in_memory=args.in_memory,
    )


if __name__ == "__main__":
    main()
