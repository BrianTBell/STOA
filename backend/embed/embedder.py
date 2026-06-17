from __future__ import annotations

from functools import lru_cache
from typing import Any

from sentence_transformers import SentenceTransformer

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def _format_list(values: object) -> str:
    if not isinstance(values, list):
        return ""
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return ", ".join(cleaned)


def build_embedding_input(paper: dict[str, Any]) -> str:
    """Build a stable text representation from stored Paper properties."""
    parts: list[str] = []

    title = str(paper.get("title") or "").strip()
    if title:
        parts.append(f"Title: {title}")

    domain = str(paper.get("domain") or "").strip()
    if domain:
        parts.append(f"Domain: {domain}")

    summary = str(paper.get("summary") or "").strip()
    if summary:
        parts.append(f"Summary: {summary}")

    concepts = _format_list(paper.get("concepts"))
    if concepts:
        parts.append(f"Concepts: {concepts}")

    methods = _format_list(paper.get("methods"))
    if methods:
        parts.append(f"Methods: {methods}")

    authors = _format_list(paper.get("authors"))
    if authors:
        parts.append(f"Authors: {authors}")

    return "\n".join(parts)


@lru_cache(maxsize=2)
def load_embedder(model_name: str = DEFAULT_EMBEDDING_MODEL) -> SentenceTransformer:
    """Load the embedding model once per process and reuse it.

    The lru_cache means the heavy SentenceTransformer (and PyTorch) load
    happens on the first call only. Every later ingestion reuses the same
    in memory instance instead of reloading the whole model, which keeps
    memory flat and avoids the load spike that crashed the small instance.
    """
    return SentenceTransformer(model_name)


def embed_text(
    text: str,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    model: SentenceTransformer | None = None,
) -> list[float]:
    model = model or load_embedder(model_name)
    vector = model.encode(text, normalize_embeddings=True)
    return [float(value) for value in vector.tolist()]


def embed_texts(
    texts: list[str],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    model: SentenceTransformer | None = None,
) -> list[list[float]]:
    model = model or load_embedder(model_name)
    vectors = model.encode(texts, normalize_embeddings=True)
    return [[float(value) for value in vector.tolist()] for vector in vectors]
