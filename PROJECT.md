# Project

A community-curated knowledge graph that maps relationships between ideas across human knowledge. AI handles structure, humans handle value.

## The problem

Knowledge is fragmented. It lives in papers, books, lectures, posts, and conversations, siloed by medium and domain. Discovery is largely accidental — you don't know what you don't know. There is no living map of how ideas actually connect.

## The vision

A **living ontology** — a graph that grows continuously as content is ingested, that organizes itself around concepts (not citations), and that surfaces quality through community signal rather than gatekeeping. Imagine exploring knowledge the way you'd explore a universe: zoom out to see fields like galaxies, zoom in to see topics like planets, zoom further to see individual papers as cities.

## Philosophy

- **AI structures, humans value.** AI does the mechanical work of parsing, embedding, extracting concepts, and proposing connections. Humans decide what's worth surfacing through votes and refinement.
- **Honor-based curation.** No gatekeepers on ideas or academic quality. Quality emerges through community signal over time. The only intake rejection is for obvious junk input that does not appear to be a real academic paper or contains too little usable content to parse.
- **Concepts over citations.** Edges represent conceptual relationships between ideas, not citation graphs. Citation lineage is at best an optional secondary lens.
- **Copyright-clean by construction.** Source content is parsed for its meaning and then discarded. Nodes hold structured summaries, embeddings, and a link back to the original — never the original itself.
- **Schema emerges from data.** Node attributes are not predefined. They are extracted from content and reconciled against an evolving canonical vocabulary so the graph self-organizes without becoming a tag soup.

## What this is not

- Not a paper repository
- Not a citation graph
- Not a social network for researchers
- Not an AI-curated authority on quality
- Not gatekept

## Initial scope

The prototype is intentionally narrow:

- **Text sources only** — local PDF upload is primary; arXiv ingestion is a secondary convenience
- **One domain** to seed the graph (chosen by the owner during Phase 1)
- **Single user** — the owner is the only "community" while the graph is small
- **Local infrastructure** — Neo4j local, Python backend, simple frontend

Multi-source ingestion (video, audio, books), real community voting, and account-based contribution are explicitly out of scope until the core pipeline works end to end.

## Long-term direction

Once the core pipeline is solid:

- Expand to additional text sources beyond arXiv
- Add video and audio ingestion (transcription → same pipeline)
- Build the community contribution and voting layer
- Add the AI assistant query interface ("who are the key players in this topic")
- Implement the layered universe-style UI for exploration

## Owner

Mechanical engineer by background, Python-fluent, learning the full stack as the project grows. The owner steers the project conceptually and validates output. Coding is delegated to AI agents (see `AGENTS.md`).
