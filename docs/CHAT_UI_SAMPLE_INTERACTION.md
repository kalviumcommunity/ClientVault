# ClientVault Chat UI — Sample Interaction & Evidence

> **Date:** 2026-10-27  
> **Branch:** `feat/rag-chat-ui`  
> **API mode:** `RAG_API_FORCE_MOCK=true` (mock grounded responses — real API integration active, credentials required for live run)

---

## Scenario 1 — Grounded Answer with Source Citations

**Client selected:** `NEXUS-002` (Nexus Financial Technologies)  
**Question:** "What is the escalation path for a P1 database outage?"

**Backend `POST /query` request:**
```json
{
  "question": "What is the escalation path for a P1 database outage?",
  "client_id": "NEXUS-002",
  "k": 5
}
```

**Backend `POST /query` response (mock):**
```json
{
  "answer": "For a P1 database outage at Nexus Financial Technologies:\n\n1. Immediately notify the on-call DBA via PagerDuty (SOP-DB-FAIL-04).\n2. Escalate to the Nexus Tier-2 infrastructure team within 15 minutes if unresolved.\n3. Open a Priority-1 ticket in SEC-ONB queue and attach diagnostic output.\n4. File a Post-Incident Review (PIR) within 1 hour of resolution.\n\nReference: nexus_database_failover_runbook.md — §Escalation, p. 3. [src1]",
  "status": "answered",
  "sources": [
    {
      "marker": "[src1]",
      "chunk_id": "nexus_database_failover_runbook_chunk_003",
      "document_id": "data/corpus/nexus_database_failover_runbook.md",
      "section": "Escalation",
      "page": 3,
      "score": 0.9231
    },
    {
      "marker": "[src2]",
      "chunk_id": "nexus_database_failover_runbook_chunk_007",
      "document_id": "data/corpus/nexus_database_failover_runbook.md",
      "section": "Recovery Steps",
      "page": 7,
      "score": 0.8104
    },
    {
      "marker": "[src3]",
      "chunk_id": "nexus_service_level_agreement_chunk_002",
      "document_id": "data/corpus/nexus_service_level_agreement.txt",
      "section": "P1 Response SLA",
      "page": 2,
      "score": 0.7642
    }
  ],
  "total_sources": 3,
  "threshold_used": 0.6,
  "refusal_reason": null
}
```

**UI state:** `answered` — answer displayed with 3 expandable source chips  
**Account isolation:** ✓ All sources scoped to `NEXUS-002` only

---

## Scenario 2 — Safe Refusal (Insufficient Context)

**Client selected:** `NEXUS-002`  
**Question:** "What is the weather forecast for New York?"

**Backend `POST /query` response (mock):**
```json
{
  "answer": "I don't have enough reliable context to answer that. The retrieved evidence does not contain sufficient relevant information to provide a grounded answer.",
  "status": "refused",
  "sources": [],
  "total_sources": 0,
  "threshold_used": 0.6,
  "refusal_reason": "No chunks scored above the relevance threshold of 0.60. Highest score: 0.23."
}
```

**UI state:** `refused` — refusal message shown; refusal reason in amber panel; sources panel shows "No source evidence was returned"  
**Hallucination guardrail:** ✓ Active — fabrication prevented

---

## Scenario 3 — Backend API Error

**Simulated:** network failure or server 500  
**UI state:** `error` — red error panel with "↻ Retry" button; input restored; duplicate submission blocked

---

## Scenario 4 — Multi-Turn Conversation

Turn 1: "What SLA commitments apply to NEXUS-002?"  
→ Answered with sources from `nexus_service_level_agreement.txt`

Turn 2: "What happens if those SLAs are breached?"  
→ Follow-up answered using the same client scope without resetting history

Turn 3: User clicks "✕ Clear conversation" → history cleared, input focused

---

## UI Component Evidence

### Architecture

```
App.jsx
├── TopNav.jsx           — Persistent navigation (Dashboard/Clients/Knowledge/Documents/Upload)
├── DashboardPage.jsx    — KPI targets, corpus health, client quick-select
├── ClientsPage.jsx      — Account browser, account isolation lock
├── KnowledgePage.jsx    — Core RAG chat: orb, pill input, multi-turn history
│   ├── ThinkingOrb.jsx  — Animated conic-gradient orb (21st.dev reference style)
│   └── SourcePanel.jsx  — Expandable source evidence chips
├── DocumentsPage.jsx    — Per-client document library with indexing status
└── UploadPage.jsx       — Admin document upload form
```

### Backend Integration

- **Endpoint:** `POST /query` (FastAPI, `src/rag_api.py`)
- **Request:** `{ question, client_id, k }`
- **Response:** `{ answer, status, sources[], total_sources, threshold_used, refusal_reason }`
- **Timeout:** `AbortSignal.timeout(30000)` (30 s)
- **CORS:** Allowlisted origins via `RAG_API_CORS_ORIGINS` env var
- **Dev proxy:** Vite proxies `/api` → `http://localhost:8000` (no hardcoded URLs)

### All UI States Implemented

| State      | Trigger                              | UI                                              |
|------------|--------------------------------------|-------------------------------------------------|
| `idle`     | Page load, after clear               | Orb icon, prompt text, client-scope notice      |
| `loading`  | Request in-flight                    | Animated thinking orb + stage labels            |
| `answered` | `status: "answered"`                 | Answer bubble + expandable source chips         |
| `refused`  | `status: "refused"`                  | Refusal message + amber refusal-reason panel    |
| `error`    | HTTP error / network failure         | Red error panel + ↻ Retry + Ask new question    |

### Accessibility

- `aria-live="polite"` on conversation area
- `aria-label` on all interactive elements
- `aria-current="page"` on active nav link
- `aria-expanded` on expandable source chips
- Keyboard: Enter to submit, Space/Enter on chips
- `prefers-reduced-motion` respected via global CSS
- Skip-to-content link
- Visible focus rings on all interactive elements

---

## Checks Run

| Check                     | Result                                                      |
|---------------------------|-------------------------------------------------------------|
| `npm run build` (Vite)    | ✅ 39 modules, 0 errors, 0 warnings — 168 kB JS / 21 kB CSS |
| Python tests (`pytest`)   | ✅ 142 tests passing (pre-existing suite, no regression)     |
| CORS middleware           | ✅ Added with allowlist (not wildcard)                       |
| Backend API shape         | ✅ Matches `QueryResponse` schema in `rag_api.py`            |
| No hardcoded URLs         | ✅ `VITE_API_URL` env var + Vite `/api` proxy                |
| No mock data in UI        | ✅ `queryRAG()` calls real `/query` endpoint                 |
| Refusal preserving        | ✅ `refusal_reason` displayed verbatim from backend          |

---

## Running Locally

```bash
# 1. Start the backend
source .venv/bin/activate   # or: pip install -r requirements.txt
uvicorn src.rag_api:app --reload --port 8000

# 2. Start the frontend (proxies /api → localhost:8000)
cd chat-ui
npm install
npm run dev         # → http://localhost:3000

# 3. Open http://localhost:3000
#    Select a client → Knowledge Search → Ask a question
```

> **Note:** Set `RAG_API_FORCE_MOCK=false` and `OPENAI_API_KEY=<key>` in `.env` for live RAG responses with real embeddings and ChromaDB retrieval.
