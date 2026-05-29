"""Embedding helpers for Phase 3."""

from .embedder import (
    DEFAULT_EMBEDDING_MODEL,
    build_embedding_input,
    embed_text,
    embed_texts,
    load_embedder,
)

__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "build_embedding_input",
    "embed_text",
    "embed_texts",
    "load_embedder",
]
