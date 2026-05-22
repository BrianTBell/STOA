# Architecture

This document captures the stack and the pipeline. Update it whenever a meaningful technical decision is made.

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language (backend) | Python 3.11+ | Owner's strongest language; best ecosystem for ML/LLM work |
| Web framework | FastAPI | Modern, async, automatic OpenAPI docs, minimal boilerplate |
| Graph database | Neo4j | Built for graphs; native Cypher; has a vector index for embedding similarity |
| Embedding model | `sentence-transformers` (default: `all-MiniLM-L6-v2`) | Local, free, fast, runs on CPU, good enough for prototype |
| LLM | Claude API (Sonnet) | High-quality extraction and reasoning; cheap at prototype scale |
| Frontend | React + a graph viz library | Best ecosystem for graph UIs; library choice deferred to Phase 6 |
| Source API | arXiv API | Free, well-documented, full-text accessible |

Local development assumes Neo4j Desktop or a Docker container. Production hosting is out of scope.

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
                   JSON attrs + embedding + confidence
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
- Configuration loaded via `pydantic-settings` or equivalent
- No hardcoded paths or keys anywhere in code
