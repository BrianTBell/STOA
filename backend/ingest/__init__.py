"""Reusable ingestion pipeline for local PDFs and arXiv papers."""

from .pipeline import (
    CLAUDE_MODEL,
    IngestionError,
    IngestionResult,
    IntakeRejectedError,
    PreparedPaper,
    ingest_prepared_paper,
    load_claude_config,
    prepare_arxiv,
    prepare_pdf_bytes,
    prepare_pdf_path,
)

__all__ = [
    "CLAUDE_MODEL",
    "IngestionError",
    "IngestionResult",
    "IntakeRejectedError",
    "PreparedPaper",
    "ingest_prepared_paper",
    "load_claude_config",
    "prepare_arxiv",
    "prepare_pdf_bytes",
    "prepare_pdf_path",
]
