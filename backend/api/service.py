"""Application service used by the FastAPI routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.ingest import (
    IngestionResult,
    build_local_pdf_id,
    ingest_prepared_paper,
    prepare_arxiv,
    prepare_pdf_bytes,
)
from backend.ingest.pipeline import ClaudeConfig

if TYPE_CHECKING:
    from backend.store import Neo4jPaperStore


class DuplicatePaperError(RuntimeError):
    def __init__(self, paper: dict[str, Any]) -> None:
        self.paper = paper_without_embedding(paper)
        title = self.paper.get("title") or self.paper["id"]
        super().__init__(f'"{title}" is already in STOA.')


def paper_without_embedding(paper: dict[str, Any]) -> dict[str, Any]:
    compact = dict(paper)
    compact.pop("embedding", None)
    return compact


class StoaService:
    def __init__(self, store: Neo4jPaperStore, claude_config: ClaudeConfig) -> None:
        self.store = store
        self.claude_config = claude_config

    def ingest_pdf(
        self,
        pdf_bytes: bytes,
        filename: str,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        existing = self.store.get_paper(build_local_pdf_id(pdf_bytes))
        if existing is not None:
            raise DuplicatePaperError(existing)
        prepared = prepare_pdf_bytes(pdf_bytes, filename, source_url=source_url)
        return self._format_ingestion_result(
            ingest_prepared_paper(prepared, self.claude_config, self.store)
        )

    def ingest_arxiv(self, arxiv_id: str) -> dict[str, Any]:
        cleaned_id = arxiv_id.strip()
        existing = self.store.get_paper(f"arxiv:{cleaned_id}")
        if existing is not None:
            raise DuplicatePaperError(existing)
        prepared = prepare_arxiv(cleaned_id)
        return self._format_ingestion_result(
            ingest_prepared_paper(prepared, self.claude_config, self.store)
        )

    def list_papers(self, limit: int) -> list[dict[str, Any]]:
        return [
            paper_without_embedding(paper)
            for paper in self.store.list_papers(limit=limit)
        ]

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        paper = self.store.get_paper(paper_id)
        return paper_without_embedding(paper) if paper is not None else None

    def get_graph(self, limit: int) -> dict[str, Any]:
        graph = self.store.get_graph(limit=limit)
        return {
            "papers": [
                paper_without_embedding(paper)
                for paper in graph["papers"]
            ],
            "edges": graph["edges"],
        }

    def get_similarity(self, paper_id: str, limit: int) -> dict[str, Any]:
        matches = self.store.find_similar_papers(paper_id, limit=limit)
        return {
            "id": paper_id,
            "matches": [
                {
                    "score": match["score"],
                    "paper": paper_without_embedding(match["paper"]),
                }
                for match in matches
            ],
        }

    def get_edges(self, paper_id: str, limit: int) -> dict[str, Any]:
        edges = self.store.list_similarity_edges(paper_id, limit=limit)
        return {
            "id": paper_id,
            "edges": [
                {
                    "direction": edge["direction"],
                    "score": edge["edge"]["score"],
                    "created_at": edge["edge"]["created_at"],
                    "updated_at": edge["edge"]["updated_at"],
                    "paper": paper_without_embedding(edge["paper"]),
                }
                for edge in edges
            ],
        }

    def close(self) -> None:
        self.store.close()

    def _format_ingestion_result(self, result: IngestionResult) -> dict[str, Any]:
        formatted = result.to_dict()
        formatted["paper"] = paper_without_embedding(formatted["paper"])
        return formatted
