"""
ClientVault — Similarity Ranking & Vector Retrieval Demonstration Engine

This module demonstrates:
- Task 1: Computing similarity metrics (Cosine Similarity and Euclidean Distance)
          between embedding vectors.
- Task 2: Generating query embeddings and comparing them against chunk embeddings
          from the prepared client corpus.
- Task 3: Ranking all candidate chunks by semantic similarity score, identifying the
          most similar (Top-K) and least similar (Bottom-K) chunks in meaning.
- Task 4: Formulating a rigorous mathematical and architectural justification for
          selecting Cosine Similarity in dense vector retrieval.
- Task 5: Running end-to-end benchmark rankings over representative queries, logging
          full scores, source text, and provenance metadata.
"""

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.corpus_embedder import (
    CorpusEmbedder,
    EmbeddedChunk,
    VectorStore,
    load_embedding_config,
    prepare_corpus_chunks,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RECORDS_PATH,
)

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.SimilarityRanker: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.SimilarityRanker")

DEFAULT_OUTPUT_LOG = PROJECT_ROOT / "similarity_ranking_output.log"
DEFAULT_RANKING_JSON = PROJECT_ROOT / "sample_ranking_results.json"


# ---------------------------------------------------------------------------
# Task 1: Similarity & Distance Metrics
# ---------------------------------------------------------------------------

def l2_norm(vec: List[float]) -> float:
    """Calculates the Euclidean (L2) norm of a vector."""
    return math.sqrt(sum(x * x for x in vec))


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Task 1: Computes Cosine Similarity between two numeric vectors:
        cos(theta) = (A . B) / (||A|| * ||B||)
    Returns a score in range [-1.0, 1.0], where 1.0 represents identical direction.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}")

    norm_a = l2_norm(vec_a)
    norm_b = l2_norm(vec_b)

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    similarity = dot_product / (norm_a * norm_b)
    return max(-1.0, min(1.0, similarity))


def euclidean_distance(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Computes Euclidean (L2) Distance between two vectors:
        dist(A, B) = sqrt(sum((a_i - b_i)^2))
    Lower distance indicates higher proximity.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))


def dot_product(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes inner product between two vectors."""
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}")
    return sum(a * b for a, b in zip(vec_a, vec_b))


# ---------------------------------------------------------------------------
# Task 4: Metric Justification
# ---------------------------------------------------------------------------

METRIC_JUSTIFICATION_TEXT = """
Architectural Justification: Why Cosine Similarity for Vector Retrieval
-------------------------------------------------------------------------------
1. Directional Alignment vs. Vector Magnitude Invariance:
   In language models, text length and token frequency can alter raw vector
   magnitude even when semantic meaning remains constant. Cosine similarity
   evaluates the cosine of the angle (theta) between vectors, completely
   normalizing out magnitude variations:
       cos(theta) = (A . B) / (||A||_2 * ||B||_2)
   This ensures a concise query like "reset password" matches a longer, descriptive
   runbook passage with equal semantic precision.

2. Equivalence on Normalized Hyperspheres:
   Modern embedding models (e.g. OpenAI text-embedding-3-small) output L2-normalized
   vectors (||v||_2 = 1.0) on the unit hypersphere. On unit-length vectors,
   Cosine Similarity simplifies directly to the dot product (A . B) and relates
   monotonically to Euclidean distance:
       ||A - B||_2^2 = ||A||^2 + ||B||^2 - 2(A . B) = 2 - 2 * cos(theta)
   Minimizing Euclidean distance is mathematically equivalent to maximizing Cosine
   Similarity, but Cosine Similarity provides a standardized [-1.0, +1.0] scale.

3. Interpretability & Thresholding:
   Cosine similarity provides an intuitive, bounded scale for retrieval confidence:
   - +0.80 to +1.00: High semantic equivalence / direct procedural match.
   - +0.40 to +0.79: Moderate contextual relevance / shared topical domain.
   -  0.00 to +0.39: Orthogonal / unrelated concepts.
   -  Negative: Opposing or incompatible semantic orientation.
-------------------------------------------------------------------------------
""".strip()


def get_metric_justification() -> Dict[str, Any]:
    """Returns structured rationale explaining metric selection."""
    return {
        "chosen_metric": "Cosine Similarity",
        "formula": "cos(theta) = (A . B) / (||A||_2 * ||B||_2)",
        "reasons": [
            "Length and magnitude invariance across differing passage lengths",
            "Direct equivalence to dot product on L2-normalized hyperspheres",
            "Clear [-1.0, +1.0] bounded range for deterministic relevance thresholding",
            "Separates semantic direction from lexical token density",
        ],
        "full_text": METRIC_JUSTIFICATION_TEXT,
    }


# ---------------------------------------------------------------------------
# Task 2 & 3: Ranking Structures & Query Comparison Engine
# ---------------------------------------------------------------------------

@dataclass
class RankedChunk:
    """Represents a candidate chunk scored and ranked against a query."""
    rank: int
    score: float
    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    vector_dim: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_preview_dict(self) -> Dict[str, Any]:
        snippet = self.content[:140].replace("\n", " ") + ("..." if len(self.content) > 140 else "")
        return {
            "rank": self.rank,
            "similarity_score": round(self.score, 4),
            "chunk_id": self.chunk_id,
            "document_id": self.metadata.get("document_id"),
            "client_id": self.metadata.get("client_id"),
            "section": self.metadata.get("section"),
            "page": self.metadata.get("page"),
            "content_snippet": snippet,
        }


@dataclass
class RankingSummary:
    """Encapsulates the complete ranking result for a query."""
    query: str
    total_candidates: int
    ranked_chunks: List[RankedChunk]
    most_similar: List[RankedChunk]
    least_similar: List[RankedChunk]
    highest_score: float
    lowest_score: float
    score_spread: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total_candidates": self.total_candidates,
            "highest_score": round(self.highest_score, 4),
            "lowest_score": round(self.lowest_score, 4),
            "score_spread": round(self.score_spread, 4),
            "most_similar": [c.to_preview_dict() for c in self.most_similar],
            "least_similar": [c.to_preview_dict() for c in self.least_similar],
            "all_ranked_chunks": [c.to_preview_dict() for c in self.ranked_chunks],
        }


class SimilarityRanker:
    """
    Task 2 & 3: Compares a user query against corpus chunk embeddings,
    calculates similarity scores, and produces ordered rankings.
    """

    def __init__(
        self,
        store: Optional[VectorStore] = None,
        embedder: Optional[CorpusEmbedder] = None,
        force_mock: bool = False,
    ):
        self.force_mock = force_mock
        self.embedder = embedder or CorpusEmbedder(force_mock=self.force_mock)

        if store is not None:
            self.store = store
        elif DEFAULT_RECORDS_PATH.exists():
            logger.info("Loading existing vector store from %s", DEFAULT_RECORDS_PATH)
            self.store = VectorStore.load_from_json(DEFAULT_RECORDS_PATH)
        else:
            logger.info("No persisted records found; preparing and embedding sample corpus...")
            chunks, _ = prepare_corpus_chunks()
            records = self.embedder.embed_chunks(chunks)
            self.store = VectorStore(records)

    def rank_for_query(
        self,
        query: str,
        client_id: Optional[str] = None,
        top_k: int = 2,
        bottom_k: int = 2,
    ) -> RankingSummary:
        """
        Task 2 & 3: Embeds the query, scores all candidate chunks, and returns
        the ranked order highlighting most and least similar chunks.
        """
        # Task 2: Embed user query
        query_vectors = self.embedder.embed_texts([query])
        query_vec = query_vectors[0]

        # Filter candidate pool if client isolation requested
        if client_id:
            candidates = self.store.filter_by_client(client_id)
        else:
            candidates = self.store.all_records()

        if not candidates:
            return RankingSummary(
                query=query,
                total_candidates=0,
                ranked_chunks=[],
                most_similar=[],
                least_similar=[],
                highest_score=0.0,
                lowest_score=0.0,
                score_spread=0.0,
            )

        # Task 1 & 2: Score candidates
        scored_candidates: List[Tuple[EmbeddedChunk, float]] = []
        for chunk in candidates:
            sim = cosine_similarity(query_vec, chunk.vector)
            scored_candidates.append((chunk, sim))

        # Task 3: Rank descending by score
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        ranked_list: List[RankedChunk] = []
        for idx, (chunk, score) in enumerate(scored_candidates, 1):
            ranked_list.append(
                RankedChunk(
                    rank=idx,
                    score=score,
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    metadata=chunk.metadata,
                    vector_dim=chunk.vector_dim,
                )
            )

        highest = ranked_list[0].score
        lowest = ranked_list[-1].score
        spread = highest - lowest

        most_sim = ranked_list[:top_k]
        least_sim = ranked_list[-bottom_k:] if len(ranked_list) >= bottom_k else ranked_list

        return RankingSummary(
            query=query,
            total_candidates=len(ranked_list),
            ranked_chunks=ranked_list,
            most_similar=most_sim,
            least_similar=least_sim,
            highest_score=highest,
            lowest_score=lowest,
            score_spread=spread,
        )


# ---------------------------------------------------------------------------
# Task 5: Demonstration Runner & Report Generation
# ---------------------------------------------------------------------------

SAMPLE_TEST_QUERIES = [
    {
        "id": "Q1",
        "query": "How do I reset an employee's forgotten account password?",
        "intent": "Credential provisioning & account onboarding procedure (ACME)",
    },
    {
        "id": "Q2",
        "query": "What is the guaranteed response time for critical database outages?",
        "intent": "SLA response time & escalation matrix (NEXUS)",
    },
    {
        "id": "Q3",
        "query": "What are the disaster recovery failover steps when primary site goes down?",
        "intent": "Disaster recovery & standby replica activation (VERTEX)",
    },
]


def run_similarity_ranking_demonstration(
    output_log_file: Optional[Path] = None,
    output_json_file: Optional[Path] = None,
    force_mock: bool = False,
) -> str:
    """Executes the similarity ranking demo across queries and saves output."""
    ranker = SimilarityRanker(force_mock=force_mock)

    logs: List[str] = []
    all_query_summaries: List[Dict[str, Any]] = []

    def emit(line: str = ""):
        logs.append(line)
        print(line)

    emit("=" * 80)
    emit("  ClientVault — Semantic Similarity Ranking & Vector Retrieval Benchmark")
    emit("=" * 80)
    emit()

    # Task 4: Print metric justification
    emit(">> TASK 4: RETRIEVAL METRIC JUSTIFICATION")
    emit("-" * 80)
    emit(METRIC_JUSTIFICATION_TEXT)
    emit()

    # Task 2 & 3: Run queries against chunk embeddings
    emit(">> TASK 2 & 3: QUERY COMPARISON, RANKING, AND EXTREMA ANALYSIS")
    emit("-" * 80)

    for item in SAMPLE_TEST_QUERIES:
        q_text = item["query"]
        emit(f"Query [{item['id']}]: \"{q_text}\"")
        emit(f"Target Intent: {item['intent']}")
        emit()

        summary = ranker.rank_for_query(q_text, top_k=2, bottom_k=2)
        all_query_summaries.append(summary.to_dict())

        emit(f"  Total Candidates Evaluated: {summary.total_candidates} chunks")
        emit(f"  Similarity Score Range:     {summary.lowest_score:.4f} to {summary.highest_score:.4f} (Spread: +{summary.score_spread:.4f})")
        emit()

        # Task 3: Show most similar results
        emit("  >> MOST SIMILAR CHUNKS (Top Matches):")
        for m in summary.most_similar:
            emit(f"    Rank #{m.rank} [Score: {m.score:.4f}] Chunk: '{m.chunk_id}'")
            emit(f"      Doc:     '{m.metadata.get('document_id')}' | Client: '{m.metadata.get('client_id')}'")
            emit(f"      Section: '{m.metadata.get('section')}' | Page: {m.metadata.get('page')}")
            snippet = m.content[:100].replace("\n", " ")
            emit(f"      Snippet: \"{snippet}...\"")
            emit()

        # Task 3: Show least similar results
        emit("  >> LEAST SIMILAR CHUNKS (Bottom Matches / Orthogonal):")
        for l in summary.least_similar:
            emit(f"    Rank #{l.rank} [Score: {l.score:.4f}] Chunk: '{l.chunk_id}'")
            emit(f"      Doc:     '{l.metadata.get('document_id')}' | Client: '{l.metadata.get('client_id')}'")
            emit(f"      Section: '{l.metadata.get('section')}' | Page: {l.metadata.get('page')}")
            snippet = l.content[:100].replace("\n", " ")
            emit(f"      Snippet: \"{snippet}...\"")
            emit()

        emit("-" * 80)

    emit("=" * 80)
    emit("  STATUS: Similarity metric computed, candidates ranked, and extrema verified.")
    emit("=" * 80)

    report_str = "\n".join(logs)

    # Task 5: Save log output
    log_path = output_log_file or DEFAULT_OUTPUT_LOG
    log_path.write_text(report_str, encoding="utf-8")
    emit(f"\n[OK] Demonstration log saved to {log_path.resolve()}")

    # Task 5: Save structured JSON ranking results
    json_path = output_json_file or DEFAULT_RANKING_JSON
    json_payload = {
        "metric": "Cosine Similarity",
        "metric_justification": get_metric_justification(),
        "query_results": all_query_summaries,
    }
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")
    emit(f"[OK] Structured sample rankings saved to {json_path.resolve()}")

    return report_str


def main():
    parser = argparse.ArgumentParser(description="ClientVault Similarity Ranking Runner")
    parser.add_argument("--output-log", type=str, default=str(DEFAULT_OUTPUT_LOG), help="Log file path")
    parser.add_argument("--output-json", type=str, default=str(DEFAULT_RANKING_JSON), help="JSON rankings path")
    parser.add_argument("--mock", action="store_true", help="Force deterministic semantic mode")
    args = parser.parse_args()

    run_similarity_ranking_demonstration(
        output_log_file=Path(args.output_log),
        output_json_file=Path(args.output_json),
        force_mock=args.mock,
    )


if __name__ == "__main__":
    main()
