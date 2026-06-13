"""Reusable paper ingestion pipeline shared by the CLI and API."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from PyPDF2 import PdfReader

from backend.screen import IntakeScreenResult, build_intake_screen_input, validate_intake_screen_result
from backend.vocab import resolve_paper_vocabulary

if TYPE_CHECKING:
    from backend.store import Neo4jPaperStore

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "backend" / "extract" / "prompts"
ARXIV_PROMPT_PATH = PROMPTS_DIR / "extraction_prompt_v1.txt"
PDF_PROMPT_PATH = PROMPTS_DIR / "extraction_prompt_pdf_v1.txt"
INTAKE_SCREEN_PROMPT_PATH = PROMPTS_DIR / "intake_screen_prompt_v1.txt"
CLAUDE_DEFAULT_BASE = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_API_VERSION = "2023-06-01"
MAX_PROMPT_TEXT_CHARS = 11000
MAX_RESPONSE_TOKENS = 1200
ARXIV_MIN_RETRY_SECONDS = 3
DEFAULT_SIMILAR_EDGE_NEIGHBORS = 3
DEFAULT_SIMILAR_EDGE_MIN_SCORE = 0.80
ARXIV_HEADERS = {
    "User-Agent": "STOA/0.1 (mailto:briantbell.work@gmail.com)",
}


class IngestionError(RuntimeError):
    """Raised when an ingestion cannot complete."""


class IntakeRejectedError(IngestionError):
    """Raised when the intake screen rejects a document."""

    def __init__(self, result: IntakeScreenResult) -> None:
        self.result = result
        super().__init__(result.rationale)


@dataclass(frozen=True)
class ClaudeConfig:
    api_key: str
    api_base: str
    model: str = CLAUDE_MODEL


@dataclass(frozen=True)
class PreparedPaper:
    source_type: str
    extraction_prompt: str
    extraction_input: dict[str, Any]
    intake_input: dict[str, Any]
    paper_id: str
    source_url: str
    metadata: dict[str, Any]
    source_name: str


@dataclass(frozen=True)
class IngestionResult:
    intake_screen: IntakeScreenResult
    paper: dict[str, Any]
    vocabulary_resolution: dict[str, Any]
    similarity_edges: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intake_screen": {
                "decision": self.intake_screen.decision,
                "rationale": self.intake_screen.rationale,
            },
            "paper": self.paper,
            "vocabulary_resolution": self.vocabulary_resolution,
            "similarity_edges": self.similarity_edges,
        }


def load_claude_config(model: str = CLAUDE_MODEL) -> ClaudeConfig:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("CLAUDE_API_KEY", "").strip()
    if not api_key:
        raise IngestionError("Missing CLAUDE_API_KEY in .env.")
    api_base = os.environ.get("CLAUDE_API_BASE", CLAUDE_DEFAULT_BASE).strip()
    return ClaudeConfig(api_key=api_key, api_base=api_base, model=model)


def fetch_metadata(arxiv_id: str) -> dict[str, Any]:
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers=ARXIV_HEADERS, timeout=20)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            namespace = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", namespace)
            if entry is None:
                raise IngestionError(f"arXiv paper not found: {arxiv_id}")

            title_element = entry.find("atom:title", namespace)
            published_element = entry.find("atom:published", namespace)
            summary_element = entry.find("atom:summary", namespace)
            authors = [
                name.text
                for author in entry.findall("atom:author", namespace)
                if (name := author.find("atom:name", namespace)) is not None and name.text
            ]
            return {
                "title": title_element.text.strip() if title_element is not None and title_element.text else None,
                "published": published_element.text if published_element is not None else None,
                "authors": authors,
                "abstract": summary_element.text.strip() if summary_element is not None and summary_element.text else None,
            }
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise IngestionError(f"arXiv metadata request failed: {exc}") from exc
        except requests.RequestException as exc:
            if attempt == 3:
                raise IngestionError(f"arXiv metadata request failed: {exc}") from exc
        except ET.ParseError as exc:
            raise IngestionError("arXiv returned invalid metadata XML.") from exc

        time.sleep(ARXIV_MIN_RETRY_SECONDS * attempt)

    raise IngestionError("arXiv metadata request failed after retries.")


def download_pdf(arxiv_id: str, destination: Path) -> None:
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    try:
        with requests.get(url, headers=ARXIV_HEADERS, stream=True, timeout=30) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as exc:
        raise IngestionError(f"arXiv PDF download failed: {exc}") from exc


def extract_text_from_pdf(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        texts: list[str] = []
        for page in reader.pages:
            try:
                text = page.extract_text()
            except Exception:
                text = ""
            if text:
                texts.append(text)
        return "\n\n".join(texts)
    except Exception as exc:
        raise IngestionError(f"PDF text extraction failed: {exc}") from exc


def load_prompt(prompt_path: Path) -> str:
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise IngestionError(f"Prompt file not found: {prompt_path.relative_to(ROOT)}") from exc


def truncate_text_for_prompt(text: str, max_chars: int = MAX_PROMPT_TEXT_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return (
        f"{text[:8000]}\n\n"
        "[TEXT TRUNCATED: only the first 8000 characters and last 3000 characters are shown]"
        f"\n\n{text[-3000:]}"
    )


def normalize_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := normalize_string(item))]


def build_local_pdf_id(pdf_bytes: bytes) -> str:
    return f"localpdf:{hashlib.sha256(pdf_bytes).hexdigest()[:16]}"


def build_local_pdf_source_url(paper_id: str, filename: str) -> str:
    digest = paper_id.removeprefix("localpdf:")
    return f"localpdf://{digest}/{quote(Path(filename).name)}"


def format_claude_prompt(prompt: str, input_data: dict[str, Any]) -> str:
    return f"{prompt}\n\nINPUT JSON:\n{json.dumps(input_data, indent=2)}\n"


def query_claude(prompt: str, config: ClaudeConfig) -> str:
    headers = {
        "x-api-key": config.api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_RESPONSE_TOKENS,
        "temperature": 0.0,
    }

    for attempt in range(1, 3):
        try:
            response = requests.post(config.api_base, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            if attempt == 2:
                raise IngestionError(f"Claude request failed: {exc}") from exc
            time.sleep(1)
            continue

        if response.status_code == 200:
            content = response.json().get("content")
            if isinstance(content, list):
                text = "".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                ).strip()
                if text:
                    return text
            raise IngestionError("Claude returned no completion text.")

        if attempt == 2:
            raise IngestionError(
                f"Claude request failed with status {response.status_code}: {response.text[:500]}"
            )
        time.sleep(1)

    raise IngestionError("Claude request failed after retries.")


def parse_json_response(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise IngestionError(
            f"Failed to parse JSON response from Claude: {exc}. Raw response: {text[:500]}"
        ) from exc


def query_claude_json(prompt: str, config: ClaudeConfig) -> Any:
    return parse_json_response(query_claude(prompt, config))


def prepare_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    *,
    source_url: str | None = None,
) -> PreparedPaper:
    if not pdf_bytes:
        raise IngestionError("The PDF upload is empty.")
    safe_filename = Path(filename).name.strip()
    if not safe_filename:
        raise IngestionError("A PDF filename is required.")
    if Path(safe_filename).suffix.lower() != ".pdf":
        raise IngestionError("The uploaded filename must end in .pdf.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
        temporary_path = Path(temporary_file.name)
        temporary_file.write(pdf_bytes)
    try:
        extracted_text = extract_text_from_pdf(temporary_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    if not extracted_text.strip():
        raise IngestionError(
            "Could not extract text from the PDF. It may be scanned, unreadable, or corrupted."
        )

    paper_id = build_local_pdf_id(pdf_bytes)
    resolved_source_url = normalize_string(source_url) or build_local_pdf_source_url(
        paper_id, safe_filename
    )
    full_text = truncate_text_for_prompt(extracted_text)
    preview = extracted_text[:2000]
    extraction_input = {
        "document_name": safe_filename,
        "extracted_text_preview": preview,
        "extracted_text_full": full_text,
    }
    return PreparedPaper(
        source_type="pdf",
        extraction_prompt=load_prompt(PDF_PROMPT_PATH),
        extraction_input=extraction_input,
        intake_input=build_intake_screen_input(
            source_type="pdf",
            source_label=safe_filename,
            extracted_text_preview=preview,
            extracted_text_full=full_text,
        ),
        paper_id=paper_id,
        source_url=resolved_source_url,
        metadata={},
        source_name=safe_filename,
    )


def prepare_pdf_path(pdf_path: Path) -> PreparedPaper:
    resolved_path = pdf_path.expanduser().resolve()
    if not resolved_path.is_file():
        raise IngestionError(f"PDF file not found: {resolved_path}")
    return prepare_pdf_bytes(
        resolved_path.read_bytes(),
        resolved_path.name,
        source_url=resolved_path.as_uri(),
    )


def prepare_arxiv(arxiv_id: str) -> PreparedPaper:
    cleaned_id = arxiv_id.strip()
    if not cleaned_id:
        raise IngestionError("An arXiv ID is required.")

    metadata = fetch_metadata(cleaned_id)
    with tempfile.TemporaryDirectory() as temporary_directory:
        pdf_path = Path(temporary_directory) / f"{cleaned_id.replace('/', '_')}.pdf"
        download_pdf(cleaned_id, pdf_path)
        extracted_text = extract_text_from_pdf(pdf_path)

    if not extracted_text.strip():
        raise IngestionError("Could not extract text from the arXiv PDF.")

    source_url = f"https://arxiv.org/abs/{cleaned_id}"
    full_text = truncate_text_for_prompt(extracted_text)
    preview = extracted_text[:2000]
    extraction_input = {
        "source_url": source_url,
        "title": metadata.get("title"),
        "authors": metadata.get("authors", []),
        "published": metadata.get("published"),
        "extracted_text_preview": preview,
        "extracted_text_full": full_text,
    }
    return PreparedPaper(
        source_type="arxiv",
        extraction_prompt=load_prompt(ARXIV_PROMPT_PATH),
        extraction_input=extraction_input,
        intake_input=build_intake_screen_input(
            source_type="arxiv",
            source_label=source_url,
            title=metadata.get("title"),
            authors=metadata.get("authors", []),
            published=metadata.get("published"),
            extracted_text_preview=preview,
            extracted_text_full=full_text,
        ),
        paper_id=f"arxiv:{cleaned_id}",
        source_url=source_url,
        metadata=metadata,
        source_name=cleaned_id,
    )


def build_paper_record(prepared: PreparedPaper, extracted_json: dict[str, Any]) -> dict[str, Any]:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "id": prepared.paper_id,
        "source_url": prepared.source_url,
        "title": normalize_string(extracted_json.get("title"))
        or normalize_string(prepared.metadata.get("title"))
        or Path(prepared.source_name).stem,
        "authors": normalize_string_list(extracted_json.get("authors"))
        or normalize_string_list(prepared.metadata.get("authors")),
        "published": normalize_string(prepared.metadata.get("published")),
        "summary": normalize_string(extracted_json.get("summary")),
        "concepts": normalize_string_list(extracted_json.get("concepts")),
        "methods": normalize_string_list(extracted_json.get("methods")),
        "domain": normalize_string(extracted_json.get("domain")),
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def extract_prepared_paper(
    prepared: PreparedPaper,
    claude_config: ClaudeConfig,
) -> tuple[IntakeScreenResult, dict[str, Any]]:
    intake_result = validate_intake_screen_result(
        query_claude_json(
            format_claude_prompt(load_prompt(INTAKE_SCREEN_PROMPT_PATH), prepared.intake_input),
            claude_config,
        )
    )
    if not intake_result.accepted:
        raise IntakeRejectedError(intake_result)

    extracted_json = query_claude_json(
        format_claude_prompt(prepared.extraction_prompt, prepared.extraction_input),
        claude_config,
    )
    if not isinstance(extracted_json, dict):
        raise IngestionError("Claude extraction response must be a JSON object.")
    return intake_result, extracted_json


def ingest_prepared_paper(
    prepared: PreparedPaper,
    claude_config: ClaudeConfig,
    store: Neo4jPaperStore,
) -> IngestionResult:
    from backend.embed import build_embedding_input, embed_text

    intake_result, extracted_json = extract_prepared_paper(prepared, claude_config)
    paper_record = build_paper_record(prepared, extracted_json)

    vocabulary_by_type = {
        term_type: store.list_vocabulary(term_type=term_type)
        for term_type in ("concept", "method", "domain")
    }
    resolution_result = resolve_paper_vocabulary(
        paper_record,
        vocabulary_by_type=vocabulary_by_type,
        claude_query=lambda prompt: query_claude_json(prompt, claude_config),
    )
    paper_record = resolution_result.resolved_paper
    if resolution_result.resolution_log["vocab_updates"]:
        store.upsert_vocabulary_entries(resolution_result.resolution_log["vocab_updates"])

    paper_record["embedding"] = embed_text(build_embedding_input(paper_record))
    store.ensure_vector_index(len(paper_record["embedding"]))
    stored_paper = store.upsert_paper(paper_record)
    similarity_edges = store.regenerate_similarity_edges(
        stored_paper["id"],
        limit=DEFAULT_SIMILAR_EDGE_NEIGHBORS,
        min_score=DEFAULT_SIMILAR_EDGE_MIN_SCORE,
    )
    return IngestionResult(
        intake_screen=intake_result,
        paper=stored_paper,
        vocabulary_resolution=resolution_result.resolution_log,
        similarity_edges=similarity_edges,
    )
