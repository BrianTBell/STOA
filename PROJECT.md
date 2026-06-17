# Project

STOA is a full stack learning project. I am a mechanical engineer teaching myself modern software by building one real thing end to end: a knowledge graph that ingests technical papers, uses an LLM to extract their structure, embeds them, stores them in a graph database, and renders them as an explorable map. It is a portfolio piece, not a product. I built it to learn the stack and to have something real to show, and this document is honest about both what works and what I would change.

## What it does

Upload a technical paper, as a local PDF or by arXiv ID, and STOA:

- screens it with Claude to reject obvious non-papers
- extracts concepts, methods, domain, and a summary as structured JSON
- embeds the summary fields locally with `sentence-transformers`
- discards the source text and stores only the structured record, the embedding, and a link back to the original
- nominates each paper's nearest neighbors by cosine similarity and writes `SIMILAR_TO` edges
- renders the result as a zoomable graph in the browser

`ARCHITECTURE.md` has the full pipeline, `SCHEMA.md` the node schema, and `ROADMAP.md` the phase by phase build record.

## What I learned

The point of the project. Building it end to end meant getting hands on with:

- **LLM structured extraction** — prompting Claude to return reliable JSON, plus a separate intake screening pass
- **Vector embeddings** — generating dense vectors locally and reasoning about model memory cost
- **Graph databases** — Neo4j, Cypher, a vector index, and similarity queries
- **Edge generation** — turning nearest neighbor search into a stored, inspectable relationship
- **Frontend rendering** — React, TypeScript, and a WebGL graph with Sigma.js and Graphology, including semantic zoom
- **API design** — FastAPI, an OpenAPI surface, and one reusable pipeline shared by the CLI and the API
- **Deployment and operations** — shipping the frontend to Vercel and the backend to Render, plus the practical security work: keeping secrets server side, CORS, cost caps, and a memory limit I had to diagnose on a small instance

## Design choices I am happy with

A few decisions that reflect real engineering judgment rather than ambition:

- **Copyright clean by construction.** Source content is parsed for meaning and then discarded. Nodes hold structured summaries, embeddings, and a link back, never the original text.
- **Schema emerges from data.** Node attributes are not predefined. They are extracted from content and reconciled against an evolving canonical vocabulary so the graph self organizes instead of becoming tag soup.
- **One pipeline, two entry points.** The CLI and the API run the same ingestion code, so behavior cannot drift between them.

## Limitations and what I would do differently

Being clear about the limits matters more to me than overselling the idea.

- **Similarity is adjacency, not progression.** The graph connects papers that resemble each other, but cosine similarity has no notion of order. It cannot tell you what to read first, so it does not, on its own, produce a learning path. The genuinely differentiated version would replace the similarity engine with LLM extracted concept dependencies (which concepts a paper assumes versus introduces), giving directed prerequisite edges. That is the rebuild I would do if I took this further.
- **An upload only graph maps your reading, not a field.** Because the graph contains only what you feed it, it cannot show you what you are missing, which is the hardest and most valuable part of mapping an unfamiliar area. Solving that would mean ingesting beyond your own reading, for example pulling a seed paper's references, which moves the project toward existing tools like Connected Papers and Semantic Scholar.
- **Cold start is real.** The first handful of papers surface little, because a similarity graph is only useful once it is dense.

## Scope

This is a single user prototype seeded by me. Ideas I explored but did not pursue, because this is a learning build and not a business, include community voting and curation, multi source ingestion (video, audio, books), and a natural language query assistant. They live in `ROADMAP.md` as possible extensions, not commitments.

## Owner

Mechanical engineer by background, Python fluent, learning the full stack by building this. I steer the project conceptually and validate the output; the implementation is done with AI coding agents (see `AGENTS.md`).
