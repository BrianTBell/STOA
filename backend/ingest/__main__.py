"""Command-line entrypoint for the STOA ingestion pipeline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .pipeline import (
    CLAUDE_MODEL,
    INTAKE_SCREEN_PROMPT_PATH,
    IntakeRejectedError,
    PreparedPaper,
    extract_prepared_paper,
    ingest_prepared_paper,
    load_claude_config,
    load_prompt,
    prepare_arxiv,
    prepare_pdf_path,
)


def print_preview(prepared: PreparedPaper) -> None:
    intake_prompt = load_prompt(INTAKE_SCREEN_PROMPT_PATH)
    print("\n--- Intake screen prompt (preview) ---\n")
    print(intake_prompt)
    print("\n--- Intake screen input JSON (preview) ---\n")
    print(json.dumps(prepared.intake_input, indent=2)[:20000])
    print("\n--- Extraction prompt (preview) ---\n")
    print(prepared.extraction_prompt)
    print("\n--- Extraction input JSON (preview) ---\n")
    print(json.dumps(prepared.extraction_input, indent=2)[:20000])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a local PDF or arXiv paper and extract structured data"
    )
    parser.add_argument("arxiv_id", nargs="?", help="The arXiv ID, e.g. 2301.04567")
    parser.add_argument("--pdf", help="Path to a local PDF file")
    parser.add_argument("--preview", action="store_true", help="Show prompts without calling Claude")
    parser.add_argument("--store", action="store_true", help="Write the result to Neo4j")
    parser.add_argument("--model", default=CLAUDE_MODEL, help=f"Claude model ID (default: {CLAUDE_MODEL})")
    args = parser.parse_args()

    if args.pdf and args.arxiv_id:
        parser.error("Provide either an arXiv ID or --pdf, not both.")
    if not args.pdf and not args.arxiv_id:
        parser.error("Provide an arXiv ID or use --pdf <path>.")

    try:
        prepared = (
            prepare_pdf_path(Path(args.pdf))
            if args.pdf
            else prepare_arxiv(args.arxiv_id)
        )

        load_dotenv()
        if args.preview or not os.environ.get("CLAUDE_API_KEY", "").strip():
            if not args.preview:
                print("WARNING: CLAUDE_API_KEY is not set. Showing a prompt preview instead.")
            if args.store:
                print("WARNING: No Neo4j write will be made in preview mode.")
            print_preview(prepared)
            return

        claude_config = load_claude_config(args.model)
        if not args.store:
            _, extracted_json = extract_prepared_paper(prepared, claude_config)
            print(json.dumps(extracted_json, indent=2))
            return

        from backend.store import Neo4jPaperStore, load_neo4j_config

        store = Neo4jPaperStore(load_neo4j_config())
        try:
            store.verify_connectivity()
            store.ensure_schema()
            result = ingest_prepared_paper(prepared, claude_config, store)
        finally:
            store.close()
        print(json.dumps(result.to_dict(), indent=2))
    except IntakeRejectedError as exc:
        print(
            json.dumps(
                {
                    "intake_screen": {
                        "decision": exc.result.decision,
                        "rationale": exc.result.rationale,
                    }
                },
                indent=2,
            )
        )
    except Exception as exc:
        print(f"Error: {exc}")
        print("No data has been written.")


if __name__ == "__main__":
    main()
