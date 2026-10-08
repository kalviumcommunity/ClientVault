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

---

## Clean-Run Proof Confirmation

The workspace setup has been verified from a fresh installation using the steps above. Output:

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

---

## Security & Secrets Policy

1. **No Secret Leaks:** `.env`, API credentials, and certificates are strictly excluded by `.gitignore`.
2. **Data Isolation:** All raw files in `data/` and local vector stores in `outputs/` are ignored by git to protect client confidentiality.
3. **Template Sync:** When introducing new configuration keys, add them with placeholder values to `.env.example`.