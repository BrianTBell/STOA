# Schema

The graph is intentionally loose. Schema emerges from data rather than being defined upfront. This document captures the conventions, not a rigid contract.

## Design principles

- **Loose attributes.** Nodes carry whatever attributes Claude extracts from content. They are stored as properties on the node and queried flexibly.
- **Canonical vocabulary.** Despite loose attributes, the *values* of certain attributes (concepts, methods, domain) are reconciled against a canonical vocabulary so the graph doesn't fragment into near-duplicate tags.
- **Clean intake.** Inputs should look like real academic papers before they enter the rest of the pipeline. Obvious junk or unusable content is rejected early with a short rationale.

## Nodes

### Paper node

The primary node type in the graph. Represents one ingested source.

Phase 2 stores the core bibliographic and extraction fields first. Later phases add `embedding` and, if the product later needs it, community signal fields.

```json
{
  "id": "arxiv:2301.04567",
  "source_url": "https://arxiv.org/abs/2301.04567",
  "title": "string",
  "authors": ["string"],
  "published": "ISO 8601 date",

  "summary": "Claude-generated short summary (2-3 sentences)",
  "concepts": ["canonical term", "..."],
  "methods": ["canonical term", "..."],
  "domain": "canonical term",

  "created_at": "ISO 8601 timestamp",
  "updated_at": "ISO 8601 timestamp"
}
```

Later phases add `embedding` as an additional property on the same `Paper` node.

For local PDFs, `id` uses the `localpdf:` prefix with a stable hash of the file bytes. CLI ingestion stores a `file:///...` URI pointing at the local document. API uploads use a caller-supplied original URL when available; otherwise they store a stable `localpdf://<hash>/<filename>` source identifier because browsers do not expose the original local path.

### Vocabulary node

Tracks canonical terms used across the graph. Created lazily as new terms are proposed and confirmed.

```json
{
  "id": "vocab:concept:fracture-mechanics",
  "term": "fracture mechanics",
  "type": "concept | method | domain",
  "aliases": ["fracture", "crack mechanics"],
  "first_seen": "ISO 8601",
  "use_count": 0
}
```

Papers reference vocabulary terms by value (the canonical string), not by node ID. The vocabulary nodes are for management and review, not for traversal-heavy queries.

## Edges

### Similarity edges between papers

Generated directly from Neo4j vector-neighbor results after a paper is stored.

```json
{
  "type": "SIMILAR_TO",
  "score": 0.0,
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

`score` is the cosine-similarity value returned by Neo4j's vector index for the paper pair. In Phase 5, edges are grounded in embedding similarity rather than an additional Claude judgment step.

## Vocabulary resolution

When a new paper is ingested, Claude extracts raw concept/method/domain terms. Before writing them to the node, the vocab resolution step runs:

1. Pull the current canonical vocabulary from Neo4j
2. Resolve exact canonical terms and known aliases locally in Python
3. For unresolved terms only, narrow the vocabulary by term type (`concept`, `method`, `domain`)
4. Send Claude just the unresolved terms plus the existing canonical terms for that type
5. Claude returns one of two outcomes per unresolved term:
   - **Alias** - extracted term is a variant of an existing canonical term (use canonical, add to aliases)
   - **New** - nothing fits; propose a new canonical term

New canonical terms are written to the vocabulary store and become available for the next paper. The graph's vocabulary grows organically and self-stabilizes as common terms solidify.

## Input quality screening

Before attribute extraction, Claude performs a lightweight intake check on the extracted text and returns:

- `accept` or `reject`
- a short rationale

The purpose is narrow: reject obvious spam, malformed uploads, or non-paper content before the pipeline spends more tokens on extraction, vocab resolution, embeddings, and graph writes. This is not a scientific-merit judgment and it is not stored as an enduring quality score on the paper node.

## Constraints worth preserving

- Never store the full source text of an ingested document
- Always store the canonical source URL so users can read the original
- Embeddings are stored as a property on the paper node, not as a separate node
- Vocabulary terms are stored as strings on paper nodes for query simplicity, with management metadata on vocabulary nodes
