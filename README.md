# Northwind Gadgets — Support Chatbot

A single conversational agent that answers questions about a fictional
company ("Northwind Gadgets") by choosing, per question, between two
retrieval strategies:

- **Agentic RAG** over five policy documents (HR leave, product FAQ, returns
  & refunds, warranty, pricing & discounts) — vector retrieval with citations.
- **Text-to-SQL** over a ~200-row `orders` table — the agent writes and
  executes a real SQL query; the order data is never embedded.

The agent decides which source(s) a question needs, and can use both for
questions that span policy and order data (e.g. *"our policy allows 30-day
returns; did order ORD-1002 qualify?"*).

> **Live URL:** _add after deploying — see [Deployment](#deployment)_
> **Repo:** _add after pushing to GitHub — see [Publishing this repo](#publishing-this-repo)_

---

## Architecture

```
┌─────────────┐        POST /chat (NDJSON stream)        ┌──────────────────┐
│  Next.js UI │ ───────────────────────────────────────▶ │   FastAPI app     │
│ (chat, tool │ ◀─────────────────────────────────────── │                  │
│  badges,    │   {tool} → {citations|sql} → {tokens...} │  ┌────────────┐  │
│  citations) │                                           │  │  Router /   │  │
└─────────────┘                                           │  │  Agent      │  │
                                                            │  └─────┬──────┘  │
                                                            │        │          │
                                                    ┌───────┴──┐ ┌──┴────────┐ │
                                                    │ RAG tool │ │ SQL tool  │ │
                                                    │ (Chroma) │ │ (SQLite)  │ │
                                                    └──────────┘ └───────────┘ │
                                                            │        │          │
                                                     5 policy docs   orders.csv │
                                                            └────────────────────┘
                                             LLM: Anthropic Claude (routing, SQL gen, answer gen)
```

**Flow for every message (`app/router.py`):**

1. **Route** — a small, non-streaming LLM call classifies the question into
   `rag`, `sql`, `both`, or `none`, returning a one-line reason. This is a
   real decision, not a keyword match: the same prompt correctly routes
   "What's the refund window?" → `rag`, "How many orders are pending?" →
   `sql`, and "our policy allows 30-day returns; did order ORD-1002
   qualify?" → `both`.
2. **Retrieve** — the selected tool(s) run:
   - RAG: embed the question, pull the top-k chunks from Chroma, discard any
     below a minimum similarity score (avoids feeding the model a
     low-relevance chunk it might paraphrase into something hallucinated-sounding).
   - SQL: the LLM generates a single `SELECT` against a fixed schema
     description; the query is validated (SELECT-only, whitelisted table, no
     multiple statements, no DDL/DML keywords) before execution against
     SQLite.
3. **Generate** — a second LLM call streams the final answer, grounded
   *only* in the retrieved context block(s). The system prompt explicitly
   forbids outside knowledge and requires the literal fallback string
   `"I don't have that information."` when context is empty — this is what
   produces the safe fallback for out-of-scope questions and prevents
   hallucinated policy text or invented SQL columns.
4. Every step is emitted as an event over the stream (`tool`, `citations`,
   `sql`, `token`, `done`), so the frontend can show which tool ran and the
   underlying evidence (citations or generated SQL) alongside the answer as
   it's still being typed out.

### Why this shape

- **One router, two tools, one answer call** rather than letting the model
  free-loop with tool-calling. For a fixed, small, well-scoped dataset like
  this, a deterministic three-step pipeline (route → retrieve → generate) is
  easier to reason about, cheaper, and just as capable as an open-ended
  agent loop, while being much easier to grade/debug (each stage's output is
  visible as its own stream event).
- **Grounding is enforced by prompt + fallback string, not by hoping** —
  the answer-generation prompt is given nothing except the retrieved
  chunks / SQL rows, so it structurally cannot cite information it wasn't
  given.

---

## Stack & reasoning

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + `StreamingResponse` | Native async, trivial to stream newline-delimited JSON events (tool → citations/SQL → tokens) to the frontend without needing full SSE plumbing. |
| LLM | Anthropic Claude (`claude-sonnet-4-6`), via `ANTHROPIC_API_KEY` | Single provider used for routing, SQL generation, and answer generation, keeping the prompt-engineering surface small. `app/llm_client.py` isolates all SDK calls, so swapping providers means editing one file. |
| Vector store | **Chroma**, local/embedded, persisted to disk, bundled MiniLM (ONNX) embeddings | The unstructured corpus is 5 short, fixed documents — there's no case for a managed vector DB here. Chroma needs zero external services and no separate embeddings API key, so the whole stack runs from one `ANTHROPIC_API_KEY` plus `docker compose up`. Chunking is heading-bounded (`## ` sections) rather than fixed-size windows, since the source docs are short policy sections where a whole section is the natural retrieval unit and keeps citations precise. |
| Structured store | SQLite, loaded from `orders.csv` at startup | ~200 rows doesn't need Postgres; SQLite gives a real SQL surface (so the "agent writes a query" requirement is genuine, not a pandas `.query()` string) with zero setup. |
| Frontend | Next.js (App Router, TypeScript) | Simple chat UI; reads the backend's NDJSON stream via `fetch` + `ReadableStream` and renders tokens as they arrive, plus a badge for which tool ran and expandable panels for citations / generated SQL. |
| Packaging | Separate Dockerfiles for backend/frontend + `docker-compose.yml` | Runs anywhere Docker runs; `docker compose up` is the entire local setup. |

## Routing decision (detail)

`app/router.py::decide_tool` sends the question alone (no chat history) to
the LLM with a system prompt describing exactly what each source contains,
and asks for strict JSON: `{"tool": "...", "reasoning": "..."}`. This is
deliberately a *classification* call, not a tool-use/function-calling call,
because the output space is only four labels — a JSON classification prompt
is simpler to validate and cheaper than a full tool-use round trip, and the
`reasoning` field is surfaced in logs for debugging misroutes.

If the router call fails to parse (e.g. transient API issue), it fails
closed to `none`, which produces the safe fallback answer rather than an
error page.

## Safe fallback / anti-hallucination

- Out-of-scope questions route to `none`; the answer prompt then has no
  context and is instructed to reply with the exact fallback string.
- RAG hits below `MIN_RELEVANCE` (0.15 cosine similarity) are dropped before
  they ever reach the answer prompt.
- SQL generation is schema-constrained (`app/sql_tool.py::SCHEMA_DESCRIPTION`)
  and told to emit `NO_QUERY` if the question doesn't fit the schema; the
  executor separately rejects anything that isn't a single `SELECT` against
  the whitelisted `orders` table (defense in depth against prompt injection
  in the question itself).
- The answer-generation step is told to use SQL rows verbatim rather than
  recomputing, so arithmetic (e.g. revenue sums) comes from SQLite, not from
  the LLM doing mental math.

## Known limitations

- **No conversation memory** — each question is routed and answered
  independently; a true multi-turn agent would carry chat history into both
  the router and answer prompts (straightforward to add, omitted for scope).
- **Router is a single classification call**, not a self-correcting agent
  loop — if it misroutes a genuinely ambiguous question, there's no retry
  step that notices the retrieved context was empty and tries the other
  tool. A production version would add a "context looks insufficient, try
  the other source" retry.
- **Chroma is local/embedded**, not a managed service — fine for 5 fixed
  documents, would not be the right choice at real document-corpus scale.
- **SQL generation is single-shot** — no query-repair loop on syntax errors;
  a failed query is surfaced to the answer model as an error string rather
  than retried.
- **`CURRENT_DATE` is a fixed env var** (`2026-06-15` per the assignment
  brief) rather than the real clock, by design — but that means this
  deployment will keep answering "today" as that date until the env var is
  changed.
- **No auth/rate limiting** on the API — acceptable for an assessment demo,
  not for a real public deployment.

---

## Running locally

```bash
cp backend/.env.example backend/.env        # add your ANTHROPIC_API_KEY
cp frontend/.env.local.example frontend/.env.local

docker compose up --build
# backend:  http://localhost:8000  (health check: /health)
# frontend: http://localhost:3000
```

The backend ingests the documents into Chroma and loads `orders.csv` into
SQLite automatically on startup (idempotent — safe to restart).

### Running without Docker

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python -m app.ingest          # one-time: build the vector index + SQLite db
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

## Deployment

Any host works; a low-friction combination:

- **Backend** → [Railway](https://railway.app) / [Render](https://render.com) /
  [Fly.io](https://fly.io) — all support "deploy from Dockerfile" directly
  from a GitHub repo. Set `ANTHROPIC_API_KEY` and `ALLOWED_ORIGINS` (to your
  deployed frontend's URL) as environment variables. Chroma's persistence
  dir (`/app/chroma_db`) should be mounted as a volume if the platform
  supports it — otherwise the container just re-ingests the (tiny) doc set
  on every restart, which is also fine here.
- **Frontend** → [Vercel](https://vercel.com) (native Next.js support) or
  the same Docker host as the backend. Set `NEXT_PUBLIC_API_BASE` to the
  deployed backend URL.

Once deployed, put the live URL at the top of this README.

## Publishing this repo

```bash
cd northwind-chatbot
git init
git add .
git commit -m "Northwind Gadgets support chatbot: agentic RAG + text-to-SQL router"
git branch -M main
git remote add origin https://github.com/<you>/northwind-chatbot.git
git push -u origin main
```

## Project structure

```
northwind-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI app, /chat streaming endpoint
│   │   ├── router.py        # routing decision + orchestration + answer streaming
│   │   ├── rag_tool.py       # vector retrieval + citation building
│   │   ├── sql_tool.py       # text-to-SQL generation, validation, execution
│   │   ├── vector_store.py   # Chroma ingestion/query
│   │   ├── llm_client.py     # Anthropic SDK wrapper (complete / complete_json / stream)
│   │   ├── ingest.py         # one-off / startup ingestion script
│   │   ├── config.py         # env-driven configuration
│   │   └── schemas.py        # request/response models
│   ├── data/
│   │   ├── docs/              # 5 policy markdown docs (RAG source)
│   │   └── orders.csv         # ~200-row structured order data (SQL source)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/                   # Next.js App Router pages
│   ├── components/            # ChatWindow, MessageBubble
│   ├── lib/api.ts             # NDJSON stream client
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```
