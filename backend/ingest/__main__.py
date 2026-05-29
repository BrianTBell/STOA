"""CLI entrypoint for Phase 1 ingestion.

Usage:
    python -m backend.ingest <arxiv_id>
    python -m backend.ingest --pdf <pdf_path>

If a `CLAUDE_API_KEY` is present in `.env`, this script will call Claude
and print structured JSON for the paper. If no key is present, it prints
the extraction prompt and input payload for review.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv
from PyPDF2 import PdfReader

from backend.store import Neo4jPaperStore, load_neo4j_config

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "backend" / "extract" / "prompts"
ARXIV_PROMPT_PATH = PROMPTS_DIR / "extraction_prompt_v1.txt"
PDF_PROMPT_PATH = PROMPTS_DIR / "extraction_prompt_pdf_v1.txt"
CLAUDE_DEFAULT_BASE = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_API_VERSION = "2023-06-01"
MAX_PROMPT_TEXT_CHARS = 11000
MAX_RESPONSE_TOKENS = 1200
ARXIV_MIN_RETRY_SECONDS = 3
ARXIV_HEADERS = {
    "User-Agent": "STOA/0.1 (mailto:briantbell.work@gmail.com)",
}


def fetch_metadata(arxiv_id: str) -> dict:
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=ARXIV_HEADERS, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)
            if entry is None:
                return {}
            title = entry.find("atom:title", ns).text.strip()
            published = entry.find("atom:published", ns).text
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
            summary = entry.find("atom:summary", ns).text.strip()
            return {"title": title, "published": published, "authors": authors, "abstract": summary}
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
        except requests.RequestException:
            if attempt == 3:
                raise

        wait_seconds = ARXIV_MIN_RETRY_SECONDS * attempt
        print(f"Metadata request failed (attempt {attempt}/3). Retrying in {wait_seconds} seconds...")
        time.sleep(wait_seconds)

    raise RuntimeError("Metadata request failed after retries")


def download_pdf(arxiv_id: str, dest_path: Path) -> None:
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    with requests.get(url, headers=ARXIV_HEADERS, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    texts = []
    for page in reader.pages:
        try:
            t = page.extract_text()
        except Exception:
            t = ""
        if t:
            texts.append(t)
    return "\n\n".join(texts)


def load_prompt(prompt_path: Path) -> str:
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[prompt file not found: {prompt_path.relative_to(ROOT)}]"


def truncate_text_for_prompt(text: str, max_chars: int = MAX_PROMPT_TEXT_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    prefix = text[:8000]
    suffix = text[-3000:]
    return (
        f"{prefix}\n\n[TEXT TRUNCATED: only the first 8000 characters and last 3000 characters are shown]"
        f"\n\n{suffix}"
    )


def build_skeleton(arxiv_id: str, metadata: dict, extracted_text: str) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "id": f"arxiv:{arxiv_id}",
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
        "title": metadata.get("title"),
        "authors": metadata.get("authors", []),
        "published": metadata.get("published"),
        "summary": metadata.get("abstract"),
        "concepts": [],
        "methods": [],
        "domain": None,
        "extracted_text_preview": extracted_text[:2000],
        "created_at": now,
    }


def build_pdf_input_data(pdf_path: Path, extracted_text: str) -> dict:
    return {
        "document_name": pdf_path.name,
        "extracted_text_preview": extracted_text[:2000],
        "extracted_text_full": truncate_text_for_prompt(extracted_text),
    }


def normalize_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = normalize_string(item)
        if text:
            cleaned.append(text)
    return cleaned


def build_local_pdf_id(pdf_path: Path) -> str:
    digest = hashlib.sha256()
    with pdf_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return f"localpdf:{digest.hexdigest()[:16]}"


def build_paper_record_for_arxiv(arxiv_id: str, metadata: dict, extracted_json: dict) -> dict:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "id": f"arxiv:{arxiv_id}",
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
        "title": normalize_string(extracted_json.get("title")) or metadata.get("title"),
        "authors": normalize_string_list(extracted_json.get("authors")) or metadata.get("authors", []),
        "published": metadata.get("published"),
        "summary": normalize_string(extracted_json.get("summary")),
        "concepts": normalize_string_list(extracted_json.get("concepts")),
        "methods": normalize_string_list(extracted_json.get("methods")),
        "domain": normalize_string(extracted_json.get("domain")),
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def build_paper_record_for_pdf(pdf_path: Path, extracted_json: dict) -> dict:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "id": build_local_pdf_id(pdf_path),
        "source_url": pdf_path.resolve().as_uri(),
        "title": normalize_string(extracted_json.get("title")) or pdf_path.stem,
        "authors": normalize_string_list(extracted_json.get("authors")),
        "published": None,
        "summary": normalize_string(extracted_json.get("summary")),
        "concepts": normalize_string_list(extracted_json.get("concepts")),
        "methods": normalize_string_list(extracted_json.get("methods")),
        "domain": normalize_string(extracted_json.get("domain")),
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def format_claude_prompt(prompt: str, input_data: dict) -> str:
    input_json = json.dumps(input_data, indent=2)
    return f"{prompt}\n\nINPUT JSON:\n{input_json}\n"


def query_claude(prompt: str, api_key: str, api_base: str, model: str = CLAUDE_MODEL) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "max_tokens": MAX_RESPONSE_TOKENS,
        "temperature": 0.0,
    }

    for attempt in range(1, 3):
        r = requests.post(api_base, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            result = r.json()
            content = result.get("content")
            if isinstance(content, list):
                parts = [item.get("text", "") for item in content if isinstance(item, dict)]
                text = "".join(parts).strip()
                if text:
                    return text
            raise ValueError("Claude returned no completion text")

        if attempt == 2:
            try:
                debug_body = r.text
            except Exception:
                debug_body = "<unable to read response body>"
            raise RuntimeError(f"Claude request failed with status {r.status_code}: {debug_body}")
        time.sleep(1)

    raise RuntimeError("Claude request failed after retries")


def parse_json_response(text: str) -> dict:
    # Strip markdown code fences — smaller models sometimes add them despite instructions
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Drop the opening fence line (``` or ```json) and the closing ```
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse JSON response from Claude: {exc}\nRaw response:\n{text[:500]}"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 ingestion: fetch paper text and call Claude for structured extraction")
    parser.add_argument("arxiv_id", nargs="?", help="The arXiv ID, e.g. 2301.04567")
    parser.add_argument("--pdf", help="Path to a local PDF file to extract instead of fetching from arXiv")
    parser.add_argument("--preview", action="store_true", help="Show prompt preview without calling Claude")
    parser.add_argument("--store", action="store_true", help="Write the resulting Paper node to Neo4j")
    parser.add_argument("--model", default=CLAUDE_MODEL, help="Claude model ID (default: claude-haiku-4-5-20251001)")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("CLAUDE_API_KEY", "").strip()
    api_base = os.environ.get("CLAUDE_API_BASE", CLAUDE_DEFAULT_BASE).strip()

    if args.pdf and args.arxiv_id:
        parser.error("Provide either an arXiv ID or --pdf, not both.")
    if not args.pdf and not args.arxiv_id:
        parser.error("Provide an arXiv ID or use --pdf <path>.")

    if args.pdf:
        pdf_path = Path(args.pdf).expanduser().resolve()
        if not pdf_path.exists():
            print(f"Error: PDF file not found: {pdf_path}")
            return
        if not pdf_path.is_file():
            print(f"Error: PDF path is not a file: {pdf_path}")
            return

        print(f"Reading local PDF: {pdf_path}")
        try:
            extracted = extract_text_from_pdf(pdf_path)
        except Exception as exc:
            print(f"PDF extract failed: {exc}")
            extracted = ""

        if not extracted:
            print("Error: Could not extract any text from the PDF. It may be unreadable or not a valid PDF.")
            return

        prompt = load_prompt(PDF_PROMPT_PATH)
        input_data = build_pdf_input_data(pdf_path, extracted)
    else:
        arxiv_id = args.arxiv_id
        print(f"Fetching metadata for {arxiv_id}...")
        metadata = fetch_metadata(arxiv_id)

        with tempfile.TemporaryDirectory() as td:
            pdf_path = Path(td) / f"{arxiv_id.replace('/', '_')}.pdf"
            try:
                print("Downloading PDF...")
                download_pdf(arxiv_id, pdf_path)
                print("Extracting text from PDF (may be imperfect)...")
                extracted = extract_text_from_pdf(pdf_path)
            except Exception as exc:
                print(f"PDF download/extract failed: {exc}")
                extracted = ""

        if not extracted:
            print("Error: Could not extract any text from the PDF. It may be unreadable or not a valid PDF.")
            return

        skeleton = build_skeleton(arxiv_id, metadata, extracted)
        prompt = load_prompt(ARXIV_PROMPT_PATH)
        input_data = {
            "source_url": skeleton["source_url"],
            "title": skeleton["title"],
            "authors": skeleton["authors"],
            "published": skeleton["published"],
            "extracted_text_preview": skeleton["extracted_text_preview"],
            "extracted_text_full": truncate_text_for_prompt(extracted),
        }

    if args.preview or not api_key:
        if api_key:
            print("WARNING: `CLAUDE_API_KEY` is set, but `--preview` was requested. No API call will be made.")
        elif args.store:
            print("WARNING: `--store` was requested, but no `CLAUDE_API_KEY` is set. No Neo4j write will be made.")
        print("\n--- Extraction prompt (preview) ---\n")
        print(prompt)
        print("\n--- Extraction input JSON (preview) ---\n")
        print(json.dumps(input_data, indent=2)[:20000])
        return

    print("Calling Claude to extract structured JSON...")
    full_prompt = format_claude_prompt(prompt, input_data)
    try:
        raw_response = query_claude(full_prompt, api_key, api_base, model=args.model)
        extracted_json = parse_json_response(raw_response)
    except Exception as exc:
        print(f"Error: {exc}")
        print("Claude returned invalid or unparsable output. No data has been written.")
        return

    if args.pdf:
        paper_record = build_paper_record_for_pdf(pdf_path, extracted_json)
    else:
        paper_record = build_paper_record_for_arxiv(arxiv_id, metadata, extracted_json)

    if not args.store:
        print(json.dumps(extracted_json, indent=2))
        return

    try:
        store = Neo4jPaperStore(load_neo4j_config())
        try:
            store.verify_connectivity()
            store.ensure_schema()
            stored_paper = store.upsert_paper(paper_record)
        finally:
            store.close()
    except Exception as exc:
        print(f"Neo4j write failed: {exc}")
        print("Structured extraction succeeded, but no data has been written.")
        return

    print(json.dumps(stored_paper, indent=2))


if __name__ == "__main__":
    main()
