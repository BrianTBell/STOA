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
| Frontend | React 19 + TypeScript + Vite | Small modern frontend stack with fast local development and a production build |
| Graph visualization | Sigma.js + Graphology | WebGL rendering for an explorable graph, with graph data and rendering kept separate |
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

**Edge generation** - `backend/store/`. Each paper independently nominates its exact top-N cosine-similarity neighbors above the minimum threshold. When a paper is added, it is compared with every existing embedding once; only papers whose top-N set changes are rewritten. A canonical `SIMILAR_TO` edge remains visible when either endpoint nominates the other, so similarity does not need to be mutual. This avoids a second Claude comparison pass because the structured paper footprint is not rich enough to justify fine-grained relationship claims at acceptable token cost.

The current minimum similarity score is `0.65`. Combined with the top-three cap, this gives papers in sparse topic regions provisional useful connections while allowing stronger neighbors to displace weaker ones as the graph grows.

**API** - `backend/api/`. FastAPI app exposing endpoints for ingestion triggers, graph queries, and (later) the AI assistant.

**Frontend** - `frontend/`. React app built with Vite and TypeScript. Sigma.js renders the graph while Graphology owns the browser-side graph model.

**Local development controls** - `backend/dev/`. A standard-library Python command starts, restarts, and stops the API and Vite process together. It records only the child process IDs and local logs, adding no process-manager dependency.

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

Phase 5 extends the store path so each newly written paper updates the affected exact top-N similarity neighborhoods. It also adds these CLI entrypoints:

- `python -m backend.store edges <paper_id>`
- `python -m backend.store rebuild-edges`

### Phase 6 note

Phase 6 inserts a lightweight intake screen between text extraction and attribute extraction. Obvious junk, spam, malformed OCR sludge, or non-paper uploads stop there with a short rationale instead of consuming more Claude calls and graph writes.

### Phase 7 note

Phase 7 exposes the existing pipeline through FastAPI without duplicating ingestion or storage logic. The API supports:

- raw local PDF upload with `POST /ingest/pdf?filename=<name>` and an `application/pdf` body
- secondary arXiv ingestion with `POST /ingest/arxiv`
- paper listing, lookup, similarity queries, and edge inspection under `/papers`

PDF upload intentionally uses a raw request body instead of multipart form data. This keeps the direct Phase 7 dependencies to `fastapi` and `uvicorn`; no multipart parsing library is required. An uploaded PDF may include an optional `source_url`. When omitted, the pipeline stores a stable `localpdf://` source identifier derived from the document hash and filename.

Ingestion performs an identity check before expensive processing. Local PDFs use the existing content hash ID, so uploading the same file under another filename is still detected; arXiv papers use their normalized arXiv ID. Duplicate requests return the existing paper with HTTP `409` and do not call Claude or recompute embeddings. Read failures and intake rejections use separate structured error codes so clients can explain the outcome clearly.

The API creates one shared Neo4j driver when the server starts and closes it when the server stops. Ingestion remains synchronous: the request returns after screening, extraction, vocabulary resolution, embedding, storage, and edge generation have completed.

### Phase 8 note

Phase 8 adds a full-screen celestial knowledge atlas using Sigma.js and Graphology. `GET /graph` returns paper nodes and similarity edges in one request so the frontend does not make one edge request per paper.

The visualization derives navigation landmarks from existing paper metadata:

- canonical `domain` values become broad visual regions
- each paper's first canonical concept becomes its initial sub-region anchor
- stored `Paper` nodes and `SIMILAR_TO` edges remain the actual graph

Domain and concept landmarks are generated only in the browser. They are visual navigation aids, not new Neo4j nodes or permanent ontology claims. This lets the owner evaluate emergent layered navigation before considering any schema changes.

The frontend uses semantic zoom: domain and concept labels remain visible as wrapped navigation landmarks, while paper labels emerge at the nearest level. Shape communicates node role without relying only on color: domains use rings, concepts use diamonds, and papers use circles. Repeated domain/concept labels are suppressed so metadata aliases do not appear as separate regions. Search, camera movement, neighborhood highlighting, paper details, ingestion controls, source links, loading/error states, and mobile layout are included in the initial implementation. Local-file source URLs are not opened from the browser; the UI offers a title-and-author Scholar search instead.

When a paper is selected or hovered, its own nominated top-three similarity edges are highlighted in gold. Incoming-only edges remain visible in muted gray, distinguishing papers the selected paper chose from papers that independently chose it without discarding either relationship.

Field placement uses a lightweight graph-derived hybrid layout. Cross-field paper similarities attract their field centers, while field-level repulsion and protected radii based on paper/concept counts prevent regions from overlapping. The resulting distance is a relative navigation signal rather than a precise embedding metric.

The frontend exposes two separate pages without adding a routing dependency: `/` is the live graph explorer and `/about` is a standalone visual explanation of ingestion, similarity nominations, semantic zoom, graph updates, and the boundary between AI structure and human judgment.

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
|-- frontend/        # React/Vite/Sigma knowledge atlas
`-- docs/            # diagrams, design notes
```

Folder structure should grow as needed, not be created speculatively.

## Configuration

- All secrets (Claude API key, Neo4j password) live in a `.env` file at the repo root
- `.env` is gitignored; `.env.example` is checked in
- Configuration loaded from environment variables at runtime
- No hardcoded paths or keys anywhere in code
