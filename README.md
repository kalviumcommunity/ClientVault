# ClientVault

> **Client Support Knowledge Assistant** — B2B internal account-specific retrieval and procedure verification system.

ClientVault enables IT support engineers and service desk teams to quickly retrieve approved, account-specific procedures during incidents while enforcing strict account isolation, factual grounding, and full source traceability.

---

## Workspace Structure

The repository organizes concerns into isolated directories:

```
ClientVault/
├── data/              # Documents & raw client corpora (git-ignored; never commit sensitive data)
├── src/               # Application source code, ingestion, retrieval, and API logic
│   ├── __init__.py
│   └── main.py        # Workspace verification and starter entrypoint
├── prompts/           # Grounding system prompts, retrieval instructions, templates
│   ├── .gitkeep
│   └── system_prompt.txt
├── outputs/           # Local vector storage, generated answers, test logs (git-ignored)
├── .env.example       # Template listing required configuration keys and model settings
├── .gitignore         # Strict exclusion rules (.venv, node_modules, .env, data/*, outputs/*)
├── requirements.txt   # Reproducible Python dependencies with version constraints
└── README.md          # Setup instructions and clean-run verification proof
```

---

## Setup & Quickstart

Follow these steps to set up and run the workspace cleanly on any fresh environment:

### 1. Create Virtual Environment

Ensure you have Python 3.11+ installed. Create an isolated virtual environment:

```bash
python3 -m venv .venv
```

### 2. Activate Virtual Environment

- **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```
- **Windows:**
  ```bash
  .venv\Scripts\activate
  ```

### 3. Install Dependencies

Install the pinned dependencies with version constraints:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example template to `.env`:

```bash
cp .env.example .env
```

Configure the required keys in `.env` (your real `.env` is git-ignored and never committed):
- `OPENAI_BASE_URL`: Endpoint for API calls (default: `https://api.openai.com/v1`)
- `OPENAI_API_KEY`: Your private API key
- `OPENAI_CHAT_MODEL`: Chat completion model (default: `gpt-4o-mini`)
- `OPENAI_EMBEDDING_MODEL`: Vector embedding model (default: `text-embedding-3-small`)

### 5. Run Workspace Verification

Verify that the environment, dependencies, directories, and vector database initialize cleanly:

```bash
python src/main.py
```

### 6. Run Chat Completion Client

Execute a first successful chat completion call against an OpenAI-compatible API with payload logging and error resilience:

```bash
# Run against live configured endpoint in .env:
python src/chat_completion.py

# Run in self-contained mock mode (offline verification + token usage):
python src/chat_completion.py --mock

# Run in mock mode demonstrating 401 and 429 error resilience:
python src/chat_completion.py --mock --test-errors
```

### 7. Run Prompt Evaluation & Comparison Suite

Evaluate and compare the baseline prompt (Variation A) against the production-constrained prompt (Variation B) on supported vs unsupported security scenarios:

```bash
# Run prompt evaluation in self-contained mock mode:
python src/prompt_eval.py --mock

# Run prompt evaluation against live configured endpoint in .env:
python src/prompt_eval.py

# Run automated test suite (all chat completion and prompt evaluation tests):
python -m unittest discover tests
```

Detailed design decisions and side-by-side matrices are documented in [`prompts/PROMPT_RATIONALE.md`](file:///Users/abhinavv/Documents/ClientVault/prompts/PROMPT_RATIONALE.md) and [`prompts/comparison_report.md`](file:///Users/abhinavv/Documents/ClientVault/prompts/comparison_report.md).

### 8. Run Token Counting & Cost Estimation Utility

Measure corpus subword tokens with `tiktoken` and project production RAG inference billing:

```bash
# Run full token count, cost estimation, and length-token analysis:
python src/token_cost_estimator.py

# Save results directly to log file:
python src/token_cost_estimator.py --output-file token_cost_output.log

# Evaluate alternative models (e.g., gpt-4o):
python src/token_cost_estimator.py --model gpt-4o
Sample benchmark metrics are recorded in [`token_cost_output.log`](file:///Users/abhinavv/Documents/ClientVault/token_cost_output.log).

### 9. Run Multi-Turn History Management & Token Trimming

Maintain conversational context across multi-turn interactions while enforcing token budgets:

```bash
# Run multi-turn overflow demo with sliding window trimming:
python src/history_manager.py --budget 350 --strategy trim

# Run multi-turn demo with conversational summarization:
python src/history_manager.py --budget 350 --strategy summarize

# Run automated unit tests:
python -m unittest discover tests
```
### 10. Run LLM Parameter Tuning & Grounding Experiments

Analyze how model inference hyperparameters (`temperature`, `max_tokens`, `stop`, `top_p`) affect output stability, length bounding, and hallucination risk in grounded enterprise retrieval:

```bash
# Run full parameter suite in self-contained mock mode:
python src/parameter_tuning.py --mock

# Run against live configured endpoint in .env:
python src/parameter_tuning.py

# Save results directly to log file:
python src/parameter_tuning.py --mock --output-file parameter_comparison_output.log

# Run automated unit tests:
python -m unittest discover tests
```
### 11. Run Structured JSON Output & Schema Validation

Enforce machine-readable JSON schemas on model outputs with Pydantic validation, markdown extraction, heuristic syntax repair, and non-crashing fallback recovery:

```bash
# Run full structured output suite in self-contained mock mode:
python src/structured_output.py --mock

# Save results directly to log file:
python src/structured_output.py --mock --output-file structured_output_results.log

# Run automated unit tests:
python -m unittest discover tests
```
Comprehensive comparison traces and error recovery logs are captured in [`structured_output_results.log`](file:///Users/abhinavv/Documents/ClientVault/structured_output_results.log).

### 12. Run Reusable Prompt Templates & Dynamic Injection

Manage prompt structures separately from business logic using template files (`prompts/templates/*.template`) with named placeholders (`{context}`, `{question}`, `{client_id}`), dynamic runtime injection, and multi-feature reuse:

```bash
# Run template demonstration rendering chat and batch audit prompts:
python src/prompt_template.py

# Save results directly to log file:
python src/prompt_template.py --output-file prompt_template_renders.log

# Run automated unit tests:
python -m unittest discover tests
```
Example renders across interactive chat and batch compliance features are captured in [`prompt_template_renders.log`](file:///Users/abhinavv/Documents/ClientVault/prompt_template_renders.log).

### 13. Run Multi-Format Document Loader & Intake Confirmation

Ingest client knowledge documents across formats (`.md`, `.txt`, `.html`, `.pdf`) into a standardized plain-text representation with granular source identity and non-crashing error resilience:

```bash
# Run multi-format intake demonstration over sample corpus:
python src/document_loader.py

# Save intake report to log file:
python src/document_loader.py --output-file document_intake_output.log

# Run automated unit tests:
python -m unittest discover tests
```
Sample corpus intake verification and skipped-file logs are captured in [`document_intake_output.log`](file:///Users/abhinavv/Documents/ClientVault/document_intake_output.log).

### 14. Run Retrieval Text Cleaning & Normalization Pipeline

Strip recurring boilerplate headers, footers, pagination ("Page X of Y"), and navigation artifacts while normalizing Unicode and whitespace across all documents:

```bash
# Run cleaning pipeline over corpus and generate before/after report:
python src/text_cleaner.py

# Save audit report to log file:
python src/text_cleaner.py --output-file cleaning_pipeline_output.log

# Run automated unit tests:
python -m unittest discover tests
```
Complete before/after comparison tables and line reduction metrics are captured in [`cleaning_pipeline_output.log`](file:///Users/abhinavv/Documents/ClientVault/cleaning_pipeline_output.log).

### 15. Run Document Chunking, Metadata Tagging & Provenance Suite

Split cleaned documents into retrieval units using multiple chunking strategies (Token-Aware with Controlled Overlap, Fixed-Size with Overlap, Paragraph/Semantic, Sentence-Boundary), attach consistent metadata (`source_id`, `document_id`, `section`, `page`, `chunk_index`, `total_chunks`, `char_span`, `client_id`, `document_code`, `extra`), and verify 100% deterministic source traceability:

```bash
# Run multi-strategy evaluation & token-aware chunking:
python src/chunker.py

# Save evaluation report, sample chunks + metadata, and provenance trace to log:
python src/chunker.py --output-file token_chunking_output.log

# Run standalone boundary context preservation demonstration:
python src/chunker.py --demo-boundary

# Run automated unit tests:
python -m unittest discover tests
```
Comparative chunk count, average sizes, metadata schema serialization, boundary context preservation proofs, model budget justification (GPT-4o-mini), and exact source traceability proofs are captured in [`token_chunking_output.log`](file:///Users/fibafathima/ClientVault/token_chunking_output.log) and [`chunking_comparison_output.log`](file:///Users/fibafathima/ClientVault/chunking_comparison_output.log).

### 16. Run Full Corpus Ingestion & Completeness Audit Pipeline

Run the end-to-end ingestion pipeline across the entire synthetic multi-client corpus (loading, boilerplate cleaning, token-aware chunking, granular metadata tagging, and completeness reconciliation audit) ensuring 100% of documents are accounted for with zero silent drops:

```bash
# Execute end-to-end ingestion pipeline over entire corpus:
python src/ingestion_pipeline.py --corpus-dir data/corpus --output-file ingestion_summary.log

# Run automated unit tests for the ingestion pipeline:
python -m unittest tests/test_ingestion_pipeline.py
```
Full ingestion statistics, account breakdowns, skipped file records, and sample chunk inspections are preserved in [`ingestion_summary.log`](file:///Users/fibafathima/ClientVault/ingestion_summary.log).
### 16. Run Text Embedding Generation & Semantic Similarity Demonstration

Generate dense text embeddings (`text-embedding-3-small`, 1536 dimensions), verify strict dimensional uniformity across sample texts, compute cosine similarity between similar and dissimilar pairs, and demonstrate semantic retrieval mechanics:

```bash
# Run embedding similarity demonstration in deterministic / API mode:
python src/embedding_demo.py --mock

# Save execution benchmark and similarity matrix to log file:
python src/embedding_demo.py --mock --output-file embedding_similarity_output.log

# Run automated unit tests:
python -m unittest tests/test_embedding_demo.py
```
Full similarity matrix and mathematical explanations are recorded in [`embedding_similarity_output.log`](file:///Users/fibafathima/ClientVault/embedding_similarity_output.log) and [`docs/EMBEDDING_REPRESENTATION.md`](file:///Users/fibafathima/ClientVault/docs/EMBEDDING_REPRESENTATION.md).

### 17. Run Corpus Embedding Generation & Vector Storage Pipeline

Convert prepared corpus chunks into dense embedding vectors (`text-embedding-3-small`, 1536 dims), attach full source and client isolation metadata, verify dimensional uniformity, and persist vector records:

```bash
# Run corpus embedding pipeline in deterministic / API mode:
python src/corpus_embedder.py --mock

# Specify custom output log and vector records storage paths:
python src/corpus_embedder.py --mock --output-log corpus_embedding_output.log --output-records corpus_embedding_records.json

# Run automated unit tests:
python -m unittest tests/test_corpus_embedder.py
```
Ingested chunks, vector dimensions, sample values, and client-isolated retrieval verifications are saved in [`corpus_embedding_output.log`](file:///Users/fibafathima/ClientVault/corpus_embedding_output.log) and [`corpus_embedding_records.json`](file:///Users/fibafathima/ClientVault/corpus_embedding_records.json).

### 18. Run Semantic Similarity Ranking & Vector Retrieval

Compare query embeddings against stored corpus chunk embeddings using Cosine Similarity, rank candidates, and display most similar (Top-K) and least similar (Bottom-K) chunks:

```bash
# Run similarity ranking demonstration across benchmark queries:
python src/similarity_ranker.py --mock

# Specify custom output log and ranking JSON paths:
python src/similarity_ranker.py --mock --output-log similarity_ranking_output.log --output-json sample_ranking_results.json

# Run automated unit tests:
python -m unittest tests/test_similarity_ranker.py
```
Full query comparison logs, candidate scores, and mathematical justifications are preserved in [`similarity_ranking_output.log`](file:///Users/fibafathima/ClientVault/similarity_ranking_output.log), [`sample_ranking_results.json`](file:///Users/fibafathima/ClientVault/sample_ranking_results.json), and [`docs/METRIC_JUSTIFICATION.md`](file:///Users/fibafathima/ClientVault/docs/METRIC_JUSTIFICATION.md).

### 19. Run Scalable Batch Embedding Pipeline & Cost Tracking

Embed large chunk corpora efficiently with configurable batch sizes, automatic retries with exponential backoff for transient API/rate-limit errors, granular token cost calculation ($0.020 / 1M tokens), and idempotent deduplication caching to skip already-embedded chunks:

```bash
# Run batch embedding pipeline with simulated transient retry and idempotent re-run:
python src/batch_embedder.py --mock --batch-size 2

# Specify custom store and run summary log:
python src/batch_embedder.py --mock --batch-size 4 --output-store outputs/batch_embedded_corpus.json --output-log batch_embedding_output.log

# Run automated unit tests:
python -m unittest tests/test_batch_embedder.py
```
A complete execution trace demonstrating batch partitioning, transient retry recovery, cost accounting, and duplicate skipping on re-run is preserved in [`batch_embedding_output.log`](file:///Users/fibafathima/ClientVault/batch_embedding_output.log).

### 20. Run Retrieval Relevance Sanity Testing & Quality Audit

Execute automated sanity tests across predetermined query-chunk pairs to confirm that related documents consistently rank above unrelated ones, diagnose surprising edge cases (such as header dominance and out-of-domain nearest-neighbor traps), and generate structured sanity reports:

```bash
# Run retrieval sanity check suite:
python src/retrieval_sanity_checker.py --mock

# Specify custom output report and JSON paths:
python src/retrieval_sanity_checker.py --mock --output-log retrieval_sanity_report.log --output-json retrieval_sanity_results.json

# Run automated unit tests:
python -m unittest tests/test_retrieval_sanity_checker.py
```
Detailed test results, separation margins, and architectural edge case analyses are preserved in [`retrieval_sanity_report.log`](file:///Users/fibafathima/ClientVault/retrieval_sanity_report.log) and [`retrieval_sanity_results.json`](file:///Users/fibafathima/ClientVault/retrieval_sanity_results.json).

### 21. Run Vector Database Collection Setup & Readback Audit

Initialize ChromaDB vector database collection, enforce collection dimension sizing (1536 dimensions, HNSW cosine metric), validate strongly-typed record schema with client isolation metadata, and confirm record insert and readback:

```bash
# Run vector database collection setup and readback verification:
python src/vector_db.py --mock --in-memory

# Specify persistent storage directory and custom output log:
python src/vector_db.py --mock --persist-dir outputs/chroma_db --output-log vector_db_readback_output.log

# Run automated unit tests:
python -m unittest tests/test_vector_db.py
```
Verification checklists, vector lengths, and readback record audits are saved in [`vector_db_readback_output.log`](file:///Users/fibafathima/ClientVault/vector_db_readback_output.log).

### 22. Run Corpus Vector Database Indexing & Audit

Index all corpus embeddings into the ChromaDB vector database collection with provenance metadata, validate that stored counts match prepared chunks, and run granular spot-checks verifying ID, vector, text, and metadata fidelity:

```bash
# Run corpus indexing and integrity audit:
python src/corpus_indexer.py --mock --in-memory

# Specify persistent storage directory and custom output log:
python src/corpus_indexer.py --mock --persist-dir outputs/chroma_db --output-log corpus_indexing_output.log

# Run automated unit tests:
python -m unittest tests/test_corpus_indexer.py
```
Count alignment audits, indexing stats, and spot-check readback reports are preserved in [`corpus_indexing_output.log`](file:///Users/fibafathima/ClientVault/corpus_indexing_output.log).

### 23. Run Vector Database Top-K Semantic Retrieval

Embed user queries using `text-embedding-3-small` (1536 dimensions), execute nearest-neighbor similarity searches against the ChromaDB collection, retrieve Top-K chunks with similarity scores and metadata, and demonstrate result set variations across changing $K$ ($K=2$, $K=4$, $K=6$):

```bash
# Run top-k semantic retrieval and demonstrate varying K:
python src/vector_retriever.py --mock --in-memory

# Specify custom query, K values, and output files:
python src/vector_retriever.py --mock --query "How do I verify employee identity via sponsor directory?" --k-values 2 4 6 --output-log sample_retrieval_output.log --output-json sample_retrieval_results.json

# Run automated unit tests:
python -m unittest tests/test_vector_retriever.py
```
Full query comparison logs, score spreads, and structured JSON results are preserved in [`sample_retrieval_output.log`](file:///Users/fibafathima/ClientVault/sample_retrieval_output.log) and [`sample_retrieval_results.json`](file:///Users/fibafathima/ClientVault/sample_retrieval_results.json).

### 24. Run Scoped Filtered Retrieval and Hybrid Lexical Search

Scope retrieval using metadata filters (`client_id`, `document_id`, `section`, `page`), combine dense vector semantic search with exact keyword and identifier matching (ticket queue codes like `SEC-ONB`, SOP codes like `SOP-DB-FAIL-04`), compare filtered vs unfiltered results, and quantify precision gains:

```bash
# Run end-to-end filtered retrieval and hybrid search demonstration:
python src/filtered_retriever.py --mock

# Run automated unit tests:
python -m unittest tests/test_filtered_retriever.py
```
Full comparative analysis, precision metrics, and JSON output are preserved in [`sample_filtered_search_output.log`](file:///Users/fibafathima/ClientVault/sample_filtered_search_output.log) and [`sample_filtered_search_results.json`](file:///Users/fibafathima/ClientVault/sample_filtered_search_results.json).

### 25. Run Retrieval Tuning & Settings Optimization

Evaluate and tune retrieval settings across candidate configurations (Naive Vector, Account-Filtered Vector, Filtered with Threshold, and ClientVault Optimal Filtered Hybrid), measure relevance metrics (Top-1 Hit Rate, Top-K Recall, MRR, Account Isolation, Out-of-Domain Safety), and select production defaults:

```bash
# Run end-to-end retrieval tuning experiment and generate audit report:
python src/retrieval_tuner.py --mock

# Run automated unit tests:
python -m unittest tests/test_retrieval_tuner.py
```
Full tuning metrics, comparative tables, and structured JSON results are preserved in [`retrieval_tuning_output.log`](file:///Users/fibafathima/ClientVault/retrieval_tuning_output.log) and [`retrieval_tuning_results.json`](file:///Users/fibafathima/ClientVault/retrieval_tuning_results.json).

### 26. Run Two-Stage Candidate Re-Ranking

Retrieve a larger candidate set ($K_{\text{initial}}=10$), re-rank candidates using cross-attention lexical-semantic scoring (evaluating token co-occurrence, phrase proximity, exact codes e.g. `SEC-ONB`, and procedural action density), and select the final grounded Top-3 chunks ($K_{\text{final}}=3$):

```bash
# Run end-to-end two-stage candidate retrieval and re-ranking:
python src/reranker.py --mock

# Run automated unit tests:
python -m unittest tests/test_reranker.py
```
Full before-and-after candidate rankings, shift metrics, and structured JSON results are preserved in [`sample_rerank_output.log`](file:///Users/fibafathima/ClientVault/sample_rerank_output.log) and [`sample_rerank_results.json`](file:///Users/fibafathima/ClientVault/sample_rerank_results.json).



### 1. Workspace Health Check
```
=================================================================
  ClientVault — Foundation Health Check & Run Proof
  Python Version: 3.12.5 (/Users/abhinavv/Documents/ClientVault/.venv/bin/python)
=================================================================

1. Verifying Workspace Directory Separation:
  [OK] Directory exists: data/
  [OK] Directory exists: prompts/
  [OK] Directory exists: outputs/
  [OK] Directory exists: src/

2. Verifying Environment & Configuration Keys:
  [OK] Loaded local .env file
  [OK] Config OPENAI_BASE_URL: https://api.openai.com/v1
  [WARN] Config OPENAI_API_KEY: Not configured (set in .env)
  [OK] Config OPENAI_CHAT_MODEL: gpt-4o-mini
  [OK] Config OPENAI_EMBEDDING_MODEL: text-embedding-3-small

3. Verifying Core Dependencies & Local ChromaDB:
  [OK] Dependency imported: openai
  [OK] Dependency imported: chromadb
  [OK] ChromaDB initialized successfully (collection count: 0)

=================================================================
  STATUS: ALL CHECKS PASSED - WORKSPACE READY
=================================================================
```

### 2. Chat Completion Single Call & Error Handling Proof
The sample execution output of `python src/chat_completion.py --mock --test-errors` is recorded in [`sample_output.log`](file:///Users/abhinavv/Documents/ClientVault/sample_output.log):

```text
=================================================================
  ClientVault — Chat Completion Verification (Mock Mode)
  Target Endpoint: http://127.0.0.1:50123/v1 (Local OpenAI-compatible mock)
  Selected Model:  gpt-4o-mini
=================================================================

[INFO] ClientVault.ChatCompletion: ---------- OUTGOING LLM REQUEST ----------
[INFO] ClientVault.ChatCompletion: Target Endpoint: http://127.0.0.1:50123/v1
[INFO] ClientVault.ChatCompletion: Selected Model:  gpt-4o-mini
[INFO] ClientVault.ChatCompletion: Messages Payload:
[
  {
    "role": "system",
    "content": "You are the Client Support Knowledge Assistant..."
  },
  {
    "role": "user",
    "content": "Explain the standard client onboarding verification procedure."
  }
]
[INFO] ClientVault.ChatCompletion: ------------------------------------------
[INFO] ClientVault.ChatCompletion: ---------- INCOMING LLM RESPONSE ----------
[INFO] ClientVault.ChatCompletion: Response ID:     chatcmpl-localmock-1792390556
[INFO] ClientVault.ChatCompletion: Reported Model:  gpt-4o-mini
[INFO] ClientVault.ChatCompletion: Finish Reason:   stop
[INFO] ClientVault.ChatCompletion: Role:            assistant
[INFO] ClientVault.ChatCompletion: Response Content:
Standard Client Onboarding Verification (KB-ONB-001 §3.2, p.4):
1. Verify authorized client sponsor identity via verified primary domain email.
2. Enforce strict dual-operator approval before credential provisioning.
3. Restrict initial IAM role to staging sandbox with audit trail enabled.
[INFO] ClientVault.ChatCompletion: Token Usage:
[INFO] ClientVault.ChatCompletion:   Prompt Tokens:     38
[INFO] ClientVault.ChatCompletion:   Completion Tokens: 54
[INFO] ClientVault.ChatCompletion:   Total Tokens:      92
[INFO] ClientVault.ChatCompletion: -------------------------------------------

=================================================================
  STATUS: CALL SUCCESSFUL (200 OK)
=================================================================

--- MODEL REPLY ---
Standard Client Onboarding Verification (KB-ONB-001 §3.2, p.4):
1. Verify authorized client sponsor identity via verified primary domain email.
2. Enforce strict dual-operator approval before credential provisioning.
3. Restrict initial IAM role to staging sandbox with audit trail enabled.
-------------------

Tokens Used: 92 (Prompt: 38, Completion: 54)

=================================================================
  Demonstrating Error Handling (Task 4 Resilience)
=================================================================

[Scenario A: HTTP 401 Authentication Error Simulation]
[ERROR] ClientVault.ChatCompletion: [AUTHENTICATION FAILED (HTTP 401)] The provided API key is invalid or unauthorized.
  Server Message: Error code: 401 - {'error': {'message': 'Incorrect API key provided.', 'type': 'invalid_request_error', 'param': None, 'code': 'invalid_api_key'}}
  Action Required: Check 'OPENAI_API_KEY' in your .env file and ensure it is valid.

[Scenario B: HTTP 429 Rate Limit Error Simulation]
[ERROR] ClientVault.ChatCompletion: [RATE LIMIT EXCEEDED (HTTP 429)] Request limit or account quota has been exceeded.
  Server Message: Error code: 429 - {'error': {'message': 'Rate limit reached for requests (quota exceeded).', 'type': 'requests', 'param': None, 'code': 'rate_limit_exceeded'}}
  Action Required: Verify account quota/billing at your provider or back off and retry later.
```

---

## RAG Chat UI (Knowledge Search)

React 18 + Vite + Tailwind CSS 4 + shadcn/ui (TypeScript-enabled, dark theme) in `chat-ui/`, backed by the
FastAPI RAG API (`src/rag_api.py`, `POST /query`). shadcn components live in `chat-ui/src/components/ui/`
(`@/` → `chat-ui/src`); the Knowledge Search composer is `components/ui/ai-thiking-orb-and-input.tsx`.

```bash
# Terminal 1 — backend (http://localhost:8000)
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn src.rag_api:app --port 8000

# Terminal 2 — frontend (http://localhost:3000, proxies /api → :8000)
cd chat-ui
npm install
npm run dev

# Typecheck / production build / API tests
npm --prefix chat-ui run typecheck
npm --prefix chat-ui run build
python -m unittest tests.test_rag_api tests.test_rag_stream tests.test_rag_observability

# Usage report from the request log
python -m src.usage_report --bucket hour
```

Answers stream from `POST /query/stream` (server-sent events: `citations`, `token`, `refusal`, `done`, `error`);
`POST /query` still returns the whole answer as JSON. Citation markers in an answer open the matching source
card, which shows the retrieved chunk text.

Repeated identical queries (same question, client, `k`, threshold, generation mode) are served from an
in-memory TTL cache (`X-Cache: HIT`). Every request is written to a JSONL log with sources, cache hit/miss,
token usage and estimated cost; `python -m src.usage_report` or `GET /usage` summarises it.
See [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md).

Config: `RAG_API_*` in `.env` (incl. `RAG_API_STREAM_DELAY_MS` for offline pacing, `RAG_API_CACHE_*`,
`RAG_API_REQUEST_LOG`); `VITE_API_URL` /
`VITE_STREAM_IDLE_TIMEOUT_MS` for the UI (see `.env.example`).
Sample interactions and screenshots: [`docs/STREAMING_SAMPLE_INTERACTION.md`](docs/STREAMING_SAMPLE_INTERACTION.md),
[`docs/CHAT_UI_SAMPLE_INTERACTION.md`](docs/CHAT_UI_SAMPLE_INTERACTION.md).

## Security & Secrets Policy

1. **No Secret Leaks:** `.env`, API credentials, and certificates are strictly excluded by `.gitignore`.
2. **Data Isolation:** All raw files in `data/` and local vector stores in `outputs/` are ignored by git to protect client confidentiality.
3. **Template Sync:** When introducing new configuration keys, add them with placeholder values to `.env.example`.