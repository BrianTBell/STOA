from __future__ import annotations

import argparse
import json

from backend.embed import (
    DEFAULT_EMBEDDING_MODEL,
    build_embedding_input,
    embed_text,
    load_embedder,
)

from . import Neo4jPaperStore, load_neo4j_config


def paper_without_embedding(paper: dict) -> dict:
    compact = dict(paper)
    compact.pop("embedding", None)
    return compact


def main() -> None:
    parser = argparse.ArgumentParser(description="Storage CLI for Neo4j Paper and Vocabulary nodes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List stored Paper nodes")
    list_parser.add_argument("--limit", type=int, default=25, help="Maximum number of Paper nodes to return")

    get_parser = subparsers.add_parser("get", help="Fetch one Paper node by id")
    get_parser.add_argument("paper_id", help="Paper node id, e.g. arxiv:2301.04567")

    delete_parser = subparsers.add_parser("delete", help="Delete one Paper node by id")
    delete_parser.add_argument("paper_id", help="Paper node id to delete")

    embed_all_parser = subparsers.add_parser("embed-all", help="Generate embeddings for stored Paper nodes")
    embed_all_parser.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"SentenceTransformer model name (default: {DEFAULT_EMBEDDING_MODEL})",
    )

    similar_parser = subparsers.add_parser("similar", help="Find nearest neighbors for one Paper node")
    similar_parser.add_argument("paper_id", help="Paper node id, e.g. arxiv:2301.04567")
    similar_parser.add_argument("--limit", type=int, default=5, help="Maximum number of similar papers to return")

    edges_parser = subparsers.add_parser("edges", help="List similarity edges for one Paper node")
    edges_parser.add_argument("paper_id", help="Paper node id, e.g. arxiv:2301.04567")
    edges_parser.add_argument("--limit", type=int, default=20, help="Maximum number of edges to return")

    subparsers.add_parser(
        "rebuild-edges",
        help="Rebuild exact top-three similarity nominations for all papers",
    )

    vocab_parser = subparsers.add_parser("vocab", help="List stored Vocabulary nodes")
    vocab_parser.add_argument("--type", choices=["concept", "method", "domain"], help="Filter vocabulary by type")
    vocab_parser.add_argument("--limit", type=int, default=100, help="Maximum number of vocabulary nodes to return")

    args = parser.parse_args()

    store = Neo4jPaperStore(load_neo4j_config())
    try:
        store.verify_connectivity()
        store.ensure_schema()

        if args.command == "list":
            papers = store.list_papers(limit=args.limit)
            print(json.dumps([paper_without_embedding(paper) for paper in papers], indent=2))
            return

        if args.command == "embed-all":
            papers = store.list_papers(limit=10000)
            if not papers:
                print(json.dumps({"embedded": 0, "dimensions": 0, "model": args.model}, indent=2))
                return

            model = load_embedder(args.model)
            embedded_count = 0
            dimensions = 0
            for paper in papers:
                embedding_input = build_embedding_input(paper)
                if not embedding_input.strip():
                    continue
                vector = embed_text(embedding_input, model_name=args.model, model=model)
                dimensions = len(vector)
                store.set_paper_embedding(paper["id"], vector)
                embedded_count += 1

            if dimensions:
                store.ensure_vector_index(dimensions)

            print(
                json.dumps(
                    {
                        "embedded": embedded_count,
                        "dimensions": dimensions,
                        "model": args.model,
                    },
                    indent=2,
                )
            )
            return

        if args.command == "vocab":
            vocab_entries = store.list_vocabulary(term_type=args.type, limit=args.limit)
            print(json.dumps(vocab_entries, indent=2))
            return

        if args.command == "rebuild-edges":
            result = store.rebuild_similarity_edges()
            print(json.dumps(result, indent=2))
            return

        paper = store.get_paper(args.paper_id)
        if args.command == "get":
            if paper is None:
                print(json.dumps({"error": f"Paper not found: {args.paper_id}"}, indent=2))
                return
            print(json.dumps(paper, indent=2))
            return

        if args.command == "similar":
            try:
                matches = store.find_similar_papers(args.paper_id, limit=args.limit)
            except ValueError as exc:
                print(json.dumps({"error": str(exc)}, indent=2))
                return
            print(
                json.dumps(
                    {
                        "id": args.paper_id,
                        "matches": [
                            {
                                "score": match["score"],
                                "paper": paper_without_embedding(match["paper"]),
                            }
                            for match in matches
                        ],
                    },
                    indent=2,
                )
            )
            return

        if args.command == "edges":
            try:
                edges = store.list_similarity_edges(args.paper_id, limit=args.limit)
            except ValueError as exc:
                print(json.dumps({"error": str(exc)}, indent=2))
                return
            print(
                json.dumps(
                    {
                        "id": args.paper_id,
                        "edges": [
                            {
                                "direction": edge["direction"],
                                "score": edge["edge"].get("score"),
                                "created_at": edge["edge"].get("created_at"),
                                "updated_at": edge["edge"].get("updated_at"),
                                "paper": paper_without_embedding(edge["paper"]),
                            }
                            for edge in edges
                        ],
                    },
                    indent=2,
                )
            )
            return

        deleted = store.delete_paper(args.paper_id)
        print(json.dumps({"id": args.paper_id, "deleted": deleted}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
