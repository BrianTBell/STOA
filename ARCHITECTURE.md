# Architecture

This document captures the stack and the pipeline. Update it whenever a meaningful technical decision is made.

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language (backend) | Python 3.11+ | Owner's strongest language; best ecosystem for ML/LLM work |
| Web framework | FastAPI | Modern, async, automatic OpenAPI docs, minimal boilerplate |
| API server | Uvicorn | Small ASGI server used to run FastAPI locally |
| Graph database | Neo4j (AuraDB Free or local instance) | Built for graphs; native Cypher; has a vector index for embedding similarity |
| Embedding model | `sentence-transformers` (default: `all-MiniLM-L6-v2`) | Local, free, fast, runs on CPU, good enough for prototype |
| LLM | Claude API (Haiku 4.5 default; Sonnet via `--model`) | Haiku handles structured JSON extraction at ~3-4x lower cost; Sonnet remains available for comparison or complex cases |
| Frontend | React + a graph viz library | Best ecosystem for graph UIs; library choice deferred to Phase 8 |
| Source API | arXiv API | Free, well-documented, full-text accessible |

Phase 2 storage is designed to work against any Neo4j instance reachable through `.env` settings. AuraDB Free is the default hosted path for this repo because it avoids local infrastructure friction while keeping the same driver and Cypher model we would use later in a deployed prototype.

## Pipeline

End-to-end flow from a new source URL to a queryable node with edges:

```
[arXiv URL]
     |
     v
[Fetch + parse text]  ---- discard source content (copyright-clean)
     |
     v
   |
   v
[Claude intake screen]
 accept/reject + short rationale
   |
   v
[Claude extraction] ---- [Embedding]
 concepts, methods,      semantic
 domain (JSON)           vector
   |                         |
   v                         |
[Vocab resolution]           |
 reconcile terms             |
 against canonical set       |
   |                         |
   +-------------------------+
             |
             v
     [Write Neo4j node]
      core paper properties
             |
             v
     [Edge generation]
      vector index -> top-N neighbors
      -> writes SIMILAR_TO edges + score
             |
             v
     [FastAPI -> React UI]
      layered exploration + AI assistant queries

Feedback loops:
  - Edge generation -> queries Neo4j's vector index
```

## Component responsibilities

**Ingestion** - `backend/ingest/`. Accepts local PDF bytes as the primary path or fetches a paper from arXiv by ID, extracts and normalizes the text, then hands it to the extraction stage. Owns the discard step. The reusable pipeline lives outside the CLI entrypoint so the CLI and API execute the same implementation.

**Extraction** - `backend/extract/`. Sends parsed text to the Claude API with a structured prompt. Returns JSON with `concepts`, `methods`, `domain`, and a short summary. Schema lives in `SCHEMA.md`.

**Embedding** - `backend/embed/`. Runs `sentence-transformers` locally, returns a dense vector per document. Because the full source text is discarded after extraction, embeddings are generated from the stored paper fields (`title`, `summary`, `concepts`, `methods`, `domain`) rather than the raw document text. Vector dimensionality is set by the model (384 for the default).

**Input quality screening** - `backend/screen/`. Lightweight Claude call immediately after text extraction. Returns an accept/reject intake decision with a short rationale based on whether the upload appears to be a real academic paper with enough usable content to parse. This is a junk-input screen, not a scientific-merit score.

**Vocabulary resolution** - `backend/vocab/`. Before writing extracted terms, queries the existing canonical vocabulary in Neo4j. Exact canonical terms and known aliases resolve locally first. Only unresolved terms go to Claude, along with the canonical terms from the same attribute type.

**Storage** - `backend/store/`. Wraps the Neo4j driver. Owns Cypher queries, node and edge writes, vector index queries. Phase 3 similarity search uses Neo4j's `SEARCH` clause.

**Edge generation** - `backend/edges/`. For a new node, uses Neo4j's vector index to find the top-N most similar existing nodes, then writes `SIMILAR_TO` edges with the returned similarity scores when they clear a minimum score threshold. This phase intentionally avoids a second Claude comparison pass because the structured paper footprint is not rich enough to justify fine-grained relationship claims at acceptable token cost.

**API** - `backend/api/`. FastAPI app exposing endpoints for ingestion triggers, graph queries, and (later) the AI assistant.

**Frontend** - `frontend/`. React app. Visualization library chosen in Phase 8.

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

### Phase 3 note

Phase 3 extends the storage flow so new ingests compute an embedding before the Neo4j write. It also adds these CLI entrypoints:

- `python -m backend.store embed-all`
- `python -m backend.store similar <paper_id>`

### Phase 4 note

Phase 4 canonicalizes `concepts`, `methods`, and `domain` before writing the paper node. It also adds this CLI entrypoint:

- `python -m backend.store vocab`

### Phase 5 note

Phase 5 extends the store path so each newly written paper regenerates its outgoing `SIMILAR_TO` edges from top-N vector neighbors. It also adds this CLI entrypoint:

- `python -m backend.store edges <paper_id>`

### Phase 6 note

Phase 6 inserts a lightweight intake screen between text extraction and attribute extraction. Obvious junk, spam, malformed OCR sludge, or non-paper uploads stop there with a short rationale instead of consuming more Claude calls and graph writes.

### Phase 7 note

Phase 7 exposes the existing pipeline through FastAPI without duplicating ingestion or storage logic. The API supports:

- raw local PDF upload with `POST /ingest/pdf?filename=<name>` and an `application/pdf` body
- secondary arXiv ingestion with `POST /ingest/arxiv`
- paper listing, lookup, similarity queries, and edge inspection under `/papers`

PDF upload intentionally uses a raw request body instead of multipart form data. This keeps the direct Phase 7 dependencies to `fastapi` and `uvicorn`; no multipart parsing library is required. An uploaded PDF may include an optional `source_url`. When omitted, the pipeline stores a stable `localpdf://` source identifier derived from the document hash and filename.

The API creates one shared Neo4j driver when the server starts and closes it when the server stops. Ingestion remains synchronous: the request returns after screening, extraction, vocabulary resolution, embedding, storage, and edge generation have completed.

## Repo layout

```
/
|-- AGENTS.md
|-- PROJECT.md
|-- ARCHITECTURE.md
|-- SCHEMA.md
|-- ROADMAP.md
|-- README.md
|-- LICENSE
|-- backend/
|   |-- ingest/
|   |-- extract/
|   |-- embed/
|   |-- vocab/
|   |-- screen/
|   |-- store/
|   |-- edges/
|   |-- api/
|   `-- tests/
|-- frontend/        # deferred to Phase 8
`-- docs/            # diagrams, design notes
```

Folder structure should grow as needed, not be created speculatively.

## Configuration

- All secrets (Claude API key, Neo4j password) live in a `.env` file at the repo root
- `.env` is gitignored; `.env.example` is checked in
- Configuration loaded from environment variables at runtime
- No hardcoded paths or keys anywhere in code
