# Architecture

This document captures the stack and the pipeline. Update it whenever a meaningful technical decision is made.

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language (backend) | Python 3.11+ | Owner's strongest language; best ecosystem for ML/LLM work |
| Web framework | FastAPI | Modern, async, automatic OpenAPI docs, minimal boilerplate |
| Graph database | Neo4j (AuraDB Free or local instance) | Built for graphs; native Cypher; has a vector index for embedding similarity |
| Embedding model | `sentence-transformers` (default: `all-MiniLM-L6-v2`) | Local, free, fast, runs on CPU, good enough for prototype |
| LLM | Claude API (Haiku 4.5 default; Sonnet via `--model`) | Haiku handles structured JSON extraction at ~3-4x lower cost; Sonnet remains available for comparison or complex cases |
| Frontend | React + a graph viz library | Best ecosystem for graph UIs; library choice deferred to Phase 6 |
| Source API | arXiv API | Free, well-documented, full-text accessible |

Phase 2 storage is designed to work against any Neo4j instance reachable through `.env` settings. AuraDB Free is the default hosted path for this repo because it avoids local infrastructure friction while keeping the same driver and Cypher model we would use later in a deployed prototype.

## Pipeline

End-to-end flow from a new source URL to a queryable node with edges:

```
[arXiv URL]
     │
     ▼
[Fetch + parse text]  ──── discard source content (copyright-clean)
     │
     ▼
   ┌─┴────────────────────┬────────────────────┐
   ▼                      ▼                    ▼
[Claude extraction]   [Embedding]        [Confidence score]
 concepts, methods,    semantic           AI-estimated
 domain (JSON)         vector             quality signal
   │                      │                    │
   ▼                      │                    │
[Vocab resolution]        │                    │
 reconcile terms          │                    │
 against canonical set    │                    │
   │                      │                    │
   └──────────────────────┴────────────────────┘
                          │
                          ▼
                  [Write Neo4j node]
                   core paper properties (Phase 2)
                          │
                          ▼
                  [Edge generation]
                   vector index → top-N neighbors
                   → Claude reasons about pairs
                   → writes typed edges
                          │
                          ▼
                  [FastAPI → React UI]
                   layered exploration + AI assistant queries

Feedback loops:
  - Community votes → adjust confidence on existing nodes
  - Edge generation → queries Neo4j's vector index
```

## Component responsibilities

**Ingestion** — `backend/ingest/`. Fetches papers from arXiv by ID, extracts text, normalizes it, hands off to the extraction stage. Owns the discard step.

**Extraction** — `backend/extract/`. Sends parsed text to the Claude API with a structured prompt. Returns JSON with `concepts`, `methods`, `domain`, and a short summary. Schema lives in `SCHEMA.md`.

**Embedding** — `backend/embed/`. Runs `sentence-transformers` locally, returns a dense vector per document. Vector dimensionality is set by the model (384 for the default).

**Confidence scoring** — `backend/score/`. Lightweight Claude call that returns a 0–1 confidence value with a short rationale. Stored on the node. **Not used as a filter** — purely a surfacing signal.

**Vocabulary resolution** — `backend/vocab/`. Before writing extracted terms, queries the existing canonical vocabulary in Neo4j. Asks Claude to map new terms to existing canonical ones where appropriate, or propose new terms when nothing fits.

**Storage** — `backend/store/`. Wraps the Neo4j driver. Owns Cypher queries, node and edge writes, vector index queries.

**Edge generation** — `backend/edges/`. For a new node, uses Neo4j's vector index to find the top-N most similar existing nodes, then sends paper-pair summaries to Claude to label the relationship (e.g. `extends`, `contradicts`, `applies-to`).

**API** — `backend/api/`. FastAPI app exposing endpoints for ingestion triggers, graph queries, and (later) the AI assistant.

**Frontend** — `frontend/`. React app. Visualization library chosen in Phase 6.

### Phase 1 note

Phase 1 ingestion now supports two input paths:

- `python -m backend.ingest <arxiv_id>` fetches metadata and PDF text from arXiv
- `python -m backend.ingest --pdf <path>` reads a local PDF and extracts text directly

Phase 1 extraction uses separate prompt files for these paths so the arXiv flow can rely on trusted bibliographic metadata while the PDF flow treats the document text as the primary source of truth.

### Phase 2 note

Phase 2 storage adds these CLI entrypoints:

- `python -m backend.ingest <arxiv_id> --store`
- `python -m backend.ingest --pdf <path> --store`
- `python -m backend.store list`

## Repo layout

```
/
├── AGENTS.md
├── PROJECT.md
├── ARCHITECTURE.md
├── SCHEMA.md
├── ROADMAP.md
├── README.md
├── LICENSE
├── backend/
│   ├── ingest/
│   ├── extract/
│   ├── embed/
│   ├── score/
│   ├── vocab/
│   ├── store/
│   ├── edges/
│   ├── api/
│   └── tests/
├── frontend/        # deferred to Phase 6
└── docs/            # diagrams, design notes
```

Folder structure should grow as needed, not be created speculatively.

## Configuration

- All secrets (Claude API key, Neo4j password) live in a `.env` file at the repo root
- `.env` is gitignored; `.env.example` is checked in
- Configuration loaded from environment variables at runtime
- No hardcoded paths or keys anywhere in code
