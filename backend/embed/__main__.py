from __future__ import annotations

import argparse
import json

from backend.store import Neo4jPaperStore, load_neo4j_config

from .embedder import DEFAULT_EMBEDDING_MODEL, build_embedding_input, embed_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 embedding preview for one stored Paper node")
    parser.add_argument("paper_id", help="Paper node id, e.g. arxiv:2301.04567")
    parser.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"SentenceTransformer model name (default: {DEFAULT_EMBEDDING_MODEL})",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=400,
        help="How many characters of the embedding input text to print",
    )
    args = parser.parse_args()

    store = Neo4jPaperStore(load_neo4j_config())
    try:
        store.verify_connectivity()
        paper = store.get_paper(args.paper_id)
    finally:
        store.close()

    if paper is None:
        print(json.dumps({"error": f"Paper not found: {args.paper_id}"}, indent=2))
        return

    embedding_input = build_embedding_input(paper)
    if not embedding_input.strip():
        print(json.dumps({"error": "Paper has no usable text fields for embedding."}, indent=2))
        return

    vector = embed_text(embedding_input, model_name=args.model)
    preview = embedding_input[: args.preview_chars]

    print(
        json.dumps(
            {
                "id": paper["id"],
                "model": args.model,
                "embedding_dimensions": len(vector),
                "embedding_input_preview": preview,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
