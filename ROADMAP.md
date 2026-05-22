# Roadmap

Phases run in order. Do not start the next phase until the current phase is verified working by the owner.

## Phase 1 — Ingestion and extraction

**Goal:** A Python script that takes an arXiv ID, fetches the paper, sends it to Claude, and prints structured JSON to the terminal.

**Done when:**
- Running `python -m backend.ingest <arxiv_id>` produces JSON with `title`, `authors`, `summary`, `concepts`, `methods`, `domain`
- The owner has reviewed at least 5 papers worth of output and trusts the extraction quality
- The Claude prompt is captured in a versioned file under `backend/extract/prompts/`

**Out of scope:** Neo4j, embeddings, scoring, vocab — all deferred. Just text in, JSON out.

## Phase 2 — Storage

**Goal:** Write the extracted JSON to Neo4j as a paper node and read it back.

**Done when:**
- Local Neo4j is running (Docker or Desktop, owner's choice)
- A node is written for each ingested paper with all attributes from Phase 1
- A simple CLI command can list all nodes in the graph
- `SCHEMA.md` matches what's actually being written

**Out of scope:** edges, embeddings, scoring, vocab.

## Phase 3 — Embeddings

**Goal:** Add embeddings to every paper node and create a Neo4j vector index.

**Done when:**
- `sentence-transformers` runs locally and produces a vector per paper
- Vectors are stored on the paper node as a property
- Neo4j vector index exists and can return top-N nearest neighbors for a given paper
- A simple CLI command demonstrates "find similar papers to <id>"

## Phase 4 — Vocabulary resolution

**Goal:** Extracted terms reconcile against a canonical vocabulary before being written.

**Done when:**
- A vocabulary store exists in Neo4j
- New papers map their extracted terms to canonical terms via a Claude call
- New canonical terms are added when nothing matches
- The owner can review the vocabulary and confirm it's not fragmenting into near-duplicates

## Phase 5 — Edge generation

**Goal:** New papers automatically get conceptual edges to similar existing papers.

**Done when:**
- For each new paper, the top-N nearest neighbors are found via the vector index
- Claude reasons about each candidate pair and returns a relationship type and description
- Edges are written to Neo4j with type, description, and confidence
- The owner has reviewed edge quality across at least 20 papers and trusts the output

## Phase 6 — Confidence scoring

**Goal:** Every node has an AI-assigned confidence score.

**Done when:**
- A Claude call returns a 0–1 confidence and rationale for each ingested paper
- Score and rationale are stored on the node
- The owner has reviewed scoring behavior across a varied set of papers

This phase intentionally comes after edges because edges are the more important signal. Confidence is added once the core graph structure is producing value.

## Phase 7 — API

**Goal:** A FastAPI server exposes the graph.

**Done when:**
- Endpoints exist for: ingest a paper by arXiv ID, list nodes, get a node by ID, get edges for a node, find similar to a node
- OpenAPI docs render at `/docs`
- The owner can hit each endpoint from the browser or curl and get sensible JSON

## Phase 8 — Frontend (basic)

**Goal:** A React app that renders the graph and lets the owner click around.

**Done when:**
- A graph viz library is chosen (candidates: Sigma.js, Cytoscape.js, react-force-graph) and rationale captured in `ARCHITECTURE.md`
- The graph renders with nodes and edges from the API
- Clicking a node shows its attributes and a link to the source
- Layered/zoom navigation is sketched (does not need to be fully realized in this phase)

## Phase 9 — AI assistant query layer

**Goal:** Natural-language queries against the graph.

**Done when:**
- A user can ask "who are the key contributors to X" or "what concepts are connected to Y" in the UI
- Claude translates the question into a Cypher query or graph traversal
- Results are rendered back to the user

## Phase 10 — Community layer (future)

Out of scope for the immediate roadmap. When the time comes, this includes user accounts, voting, the `community_score` field becoming live, and contribution mechanics.

## Cross-cutting work

These get added when first needed, not upfront:

- Testing (`pytest`, basic test scaffold added in Phase 1, expanded each phase)
- Linting/formatting (`ruff`, `black`, added in Phase 1)
- Logging (added when output volume warrants it)
- Configuration management (added in Phase 1 with `.env` for the Claude API key)
- CI (added when the codebase is large enough to benefit)
