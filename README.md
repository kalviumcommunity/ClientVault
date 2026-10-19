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

## Security & Secrets Policy

1. **No Secret Leaks:** `.env`, API credentials, and certificates are strictly excluded by `.gitignore`.
2. **Data Isolation:** All raw files in `data/` and local vector stores in `outputs/` are ignored by git to protect client confidentiality.
3. **Template Sync:** When introducing new configuration keys, add them with placeholder values to `.env.example`.