from __future__ import annotations

import argparse
import json

from . import Neo4jPaperStore, load_neo4j_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 storage CLI for Neo4j Paper nodes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List stored Paper nodes")
    list_parser.add_argument("--limit", type=int, default=25, help="Maximum number of Paper nodes to return")

    get_parser = subparsers.add_parser("get", help="Fetch one Paper node by id")
    get_parser.add_argument("paper_id", help="Paper node id, e.g. arxiv:2301.04567")

    delete_parser = subparsers.add_parser("delete", help="Delete one Paper node by id")
    delete_parser.add_argument("paper_id", help="Paper node id to delete")

    args = parser.parse_args()

    store = Neo4jPaperStore(load_neo4j_config())
    try:
        store.verify_connectivity()
        store.ensure_schema()

        if args.command == "list":
            papers = store.list_papers(limit=args.limit)
            print(json.dumps(papers, indent=2))
            return

        paper = store.get_paper(args.paper_id)
        if args.command == "get":
            if paper is None:
                print(json.dumps({"error": f"Paper not found: {args.paper_id}"}, indent=2))
                return
            print(json.dumps(paper, indent=2))
            return

        deleted = store.delete_paper(args.paper_id)
        print(json.dumps({"id": args.paper_id, "deleted": deleted}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
