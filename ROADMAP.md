# Roadmap

Phases run in order. Do not start the next phase until the current phase is verified working by the owner.

## Phase 1 - Ingestion and extraction

**Goal:** A Python script that can ingest either an arXiv paper or a local PDF, send the paper text to Claude, and print structured JSON to the terminal.

**Done when:**
- Running `python -m backend.ingest <arxiv_id>` produces JSON with `title`, `authors`, `summary`, `concepts`, `methods`, `domain`
- Running `python -m backend.ingest --pdf <path_to_pdf>` produces JSON with `title`, `authors`, `summary`, `concepts`, `methods`, `domain`
- The owner has reviewed at least 5 papers worth of output and trusts the extraction quality
- The Claude prompts are captured in versioned files under `backend/extract/prompts/`

**Out of scope:** Neo4j, embeddings, scoring, vocab - all deferred. Just text in, JSON out.

## Phase 2 - Storage

**Goal:** Write the extracted JSON to Neo4j as a paper node and read it back.

**Done when:**
- A Neo4j instance is running and reachable from the backend (AuraDB Free, Desktop, or Docker)
- A node is written for each ingested paper with all attributes from Phase 1
- A simple CLI command can list all nodes in the graph
- `SCHEMA.md` matches what's actually being written

**Out of scope:** edges, embeddings, scoring, vocab.

## Phase 3 - Embeddings

**Goal:** Add embeddings to every paper node and create a Neo4j vector index.

**Done when:**
- `sentence-transformers` runs locally and produces a vector per paper
- Vectors are stored on the paper node as a property
- Neo4j vector index exists and can return top-N nearest neighbors for a given paper
- A simple CLI command demonstrates "find similar papers to <id>"

## Phase 4 - Vocabulary resolution

**Goal:** Extracted terms reconcile against a canonical vocabulary before being written.

**Done when:**
- A vocabulary store exists in Neo4j
- New papers map their extracted terms to canonical terms via a Claude call
- New canonical terms are added when nothing matches
- The owner can review the vocabulary and confirm it's not fragmenting into near-duplicates

## Phase 5 - Edge generation

**Goal:** New papers automatically get similarity edges to nearby existing papers.

**Done when:**
- Backend writes `SIMILAR_TO` edges for new papers based on top-N nearest neighbors from the Neo4j vector index
- Similarity edges are only written when the vector score clears the configured minimum threshold
- Similarity score is stored on each edge
- A simple CLI command can inspect edges for a paper
- The owner has reviewed similarity-edge behavior across a varied set of papers

## Phase 6 - Input quality screening

**Goal:** Obvious junk, spam, or non-paper uploads are screened out before extraction.

**Done when:**
- After PDF text extraction, a Claude call returns a structured intake decision for each upload
- The decision distinguishes between acceptable academic-paper input and obvious junk / unusable content
- Rejected uploads return a short rationale and do not proceed to attribute extraction, vocab resolution, embedding, or graph writes
- The owner has reviewed screening behavior across a varied set of papers and a few intentionally bad inputs

This phase intentionally comes after edges because the core graph structure matters more than intake hardening during early prototype work. The screening step is meant to block obvious garbage, not to judge whether a legitimate paper is good science.

## Phase 7 - API

**Goal:** A FastAPI server exposes the graph.

**Done when:**
- Endpoints exist for: ingest a local PDF, ingest a paper by arXiv ID, list nodes, get a node by ID, get edges for a node, find similar to a node
- Local PDF ingestion is the primary API path and arXiv ingestion remains available as a secondary convenience
- The CLI and API call the same reusable ingestion pipeline
- OpenAPI docs render at `/docs`
- The owner can hit each endpoint from the browser or curl and get sensible JSON
- Automated tests cover the API contract without calling Claude or Neo4j

## Phase 8 - Frontend (basic)

**Goal:** A React app that renders the graph and lets the owner click around.

**Done when:**
- A graph viz library is chosen (candidates: Sigma.js, Cytoscape.js, react-force-graph) and rationale captured in `ARCHITECTURE.md`
- The graph renders with nodes and edges from the API
- Clicking a node shows its attributes and a link to the source
- Layered/zoom navigation is sketched (does not need to be fully realized in this phase)

## Phase 9 - AI assistant query layer

**Goal:** Natural-language queries against the graph.

**Done when:**
- A user can ask "who are the key contributors to X" or "what concepts are connected to Y" in the UI
- Claude translates the question into a Cypher query or graph traversal
- Results are rendered back to the user

## Phase 10 - Community layer (future)

Out of scope for the immediate roadmap. When the time comes, this includes user accounts, voting, the `community_score` field becoming live, and contribution mechanics.

## Cross-cutting work

These get added when first needed, not upfront:

- Testing (`pytest`, basic test scaffold added in Phase 1, expanded each phase)
- Linting/formatting (`ruff`, `black`, added in Phase 1)
- Logging (added when output volume warrants it)
- Configuration management (added in Phase 1 with `.env` for the Claude API key)
- CI (added when the codebase is large enough to benefit)
