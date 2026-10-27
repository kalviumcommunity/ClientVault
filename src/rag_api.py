"""
ClientVault — Backend API for the RAG Service (FastAPI)

POST /query — accepts a question and optional client_id, returns grounded
answer with sources, status, and citation metadata. Runs the existing RAG
pipeline through hallucination guardrails and citation verification.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from dotenv import load_dotenv

from src.hallucination_guardrails import (
    guarded_generate,
    REFUSAL_MESSAGE,
    DEFAULT_RELEVANCE_THRESHOLD,
)

load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ClientVault.RAGAPI: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ClientVault.RAGAPI")

app = FastAPI(
    title="ClientVault RAG API",
    description="Grounded answer generation with source citations for client-specific knowledge bases.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Environment config
# ---------------------------------------------------------------------------
DEFAULT_PORT = int(os.getenv("RAG_API_PORT", "8000"))
MAX_QUESTION_LENGTH = int(os.getenv("RAG_API_MAX_QUESTION_LENGTH", "1000"))
FORCE_MOCK = os.getenv("RAG_API_FORCE_MOCK", "true").lower() in ("true", "1", "yes")
THRESHOLD = float(os.getenv("RAG_API_THRESHOLD", str(DEFAULT_RELEVANCE_THRESHOLD)))


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_LENGTH,
                          description="The user's question (1-1000 chars)")
    client_id: Optional[str] = Field(None, description="Optional account/client filter")
    k: int = Field(default=5, ge=1, le=20, description="Number of chunks to retrieve")

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("question must be a non-empty string")
        return stripped


class SourceItem(BaseModel):
    marker: str
    chunk_id: str
    document_id: str
    section: str
    page: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    status: str  # "answered" | "refused" | "error"
    sources: List[SourceItem]
    total_sources: int
    threshold_used: float
    refusal_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy", "service": "ClientVault RAG API"}


@app.post("/query", response_model=QueryResponse, tags=["rag"])
async def query_endpoint(req: QueryRequest) -> QueryResponse:
    """Main RAG query endpoint."""
    try:
        result = guarded_generate(
            query=req.question,
            client_id=req.client_id,
            k=req.k,
            threshold=THRESHOLD,
            force_mock=FORCE_MOCK,
        )

        sources = [
            SourceItem(
                marker=s["marker"],
                chunk_id=s["chunk_id"],
                document_id=s["document_id"],
                section=s["section"],
                page=s["page"],
                score=s["score"],
            )
            for s in result.sources
        ]

        status = "refused" if not result.passed_guard else "answered"

        return QueryResponse(
            answer=result.answer,
            status=status,
            sources=sources,
            total_sources=result.source_count,
            threshold_used=result.threshold_used,
            refusal_reason=result.refusal_reason,
        )

    except Exception as e:
        logger.exception("Internal error processing query")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT)
