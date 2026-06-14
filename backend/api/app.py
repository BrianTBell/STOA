"""FastAPI routes for ingestion and graph queries."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import Body, FastAPI, HTTPException, Query, Request, status

from backend.ingest import (
    IngestionError,
    IntakeRejectedError,
    PaperReadError,
    load_claude_config,
)

from .models import (
    ArxivIngestRequest,
    GraphResponse,
    IngestionResponse,
    PaperEdgesResponse,
    PaperResponse,
    SimilarityResponse,
)
from .service import DuplicatePaperError, StoaService


class ApiService(Protocol):
    def ingest_pdf(
        self,
        pdf_bytes: bytes,
        filename: str,
        source_url: str | None = None,
    ) -> dict: ...

    def ingest_arxiv(self, arxiv_id: str) -> dict: ...

    def list_papers(self, limit: int) -> list[dict]: ...

    def get_paper(self, paper_id: str) -> dict | None: ...

    def get_graph(self, limit: int) -> dict: ...

    def get_similarity(self, paper_id: str, limit: int) -> dict: ...

    def get_edges(self, paper_id: str, limit: int) -> dict: ...


def create_default_service() -> StoaService:
    from backend.store import Neo4jPaperStore, load_neo4j_config

    store = Neo4jPaperStore(load_neo4j_config())
    try:
        store.verify_connectivity()
        store.ensure_schema()
        return StoaService(store, load_claude_config())
    except Exception:
        store.close()
        raise


def create_app(service: ApiService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        owned_service = service is None
        application.state.service = service or create_default_service()
        try:
            yield
        finally:
            if owned_service:
                application.state.service.close()

    application = FastAPI(
        title="STOA API",
        version="0.1.0",
        description="Ingest academic papers and query the STOA knowledge graph.",
        lifespan=lifespan,
    )

    def get_service(request: Request) -> ApiService:
        return request.app.state.service

    def raise_ingestion_http_error(exc: Exception) -> None:
        if isinstance(exc, DuplicatePaperError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_paper",
                    "message": str(exc),
                    "paper": exc.paper,
                },
            ) from exc
        if isinstance(exc, IntakeRejectedError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "not_academic_paper",
                    "message": "This upload was not accepted as an academic paper.",
                    "rationale": exc.result.rationale,
                },
            ) from exc
        if isinstance(exc, PaperReadError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "cannot_read_paper",
                    "message": str(exc),
                },
            ) from exc
        if isinstance(exc, IngestionError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "ingestion_failed",
                    "message": str(exc),
                },
            ) from exc
        raise exc

    @application.post(
        "/ingest/pdf",
        response_model=IngestionResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Ingest a local PDF",
    )
    def ingest_pdf(
        request: Request,
        filename: str = Query(..., min_length=1, examples=["paper.pdf"]),
        source_url: str | None = Query(
            None,
            description="Optional original URL. A stable localpdf:// URL is generated when omitted.",
        ),
        pdf_bytes: bytes = Body(..., media_type="application/pdf"),
    ) -> dict:
        try:
            return get_service(request).ingest_pdf(pdf_bytes, filename, source_url)
        except Exception as exc:
            raise_ingestion_http_error(exc)
            raise

    @application.post(
        "/ingest/arxiv",
        response_model=IngestionResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Ingest an arXiv paper",
    )
    def ingest_arxiv(request: Request, payload: ArxivIngestRequest) -> dict:
        try:
            return get_service(request).ingest_arxiv(payload.arxiv_id)
        except Exception as exc:
            raise_ingestion_http_error(exc)
            raise

    @application.get("/papers", response_model=list[PaperResponse], summary="List papers")
    def list_papers(
        request: Request,
        limit: int = Query(25, ge=1, le=1000),
    ) -> list[dict]:
        return get_service(request).list_papers(limit)

    @application.get(
        "/graph",
        response_model=GraphResponse,
        summary="Get papers and similarity edges for graph visualization",
    )
    def get_graph(
        request: Request,
        limit: int = Query(1000, ge=1, le=5000),
    ) -> dict:
        return get_service(request).get_graph(limit)

    @application.get(
        "/papers/{paper_id:path}/edges",
        response_model=PaperEdgesResponse,
        summary="List similarity edges for a paper",
    )
    def get_edges(
        request: Request,
        paper_id: str,
        limit: int = Query(20, ge=1, le=1000),
    ) -> dict:
        try:
            return get_service(request).get_edges(paper_id, limit)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get(
        "/papers/{paper_id:path}/similar",
        response_model=SimilarityResponse,
        summary="Find papers with nearby embeddings",
    )
    def get_similarity(
        request: Request,
        paper_id: str,
        limit: int = Query(5, ge=1, le=100),
    ) -> dict:
        try:
            return get_service(request).get_similarity(paper_id, limit)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get(
        "/papers/{paper_id:path}",
        response_model=PaperResponse,
        summary="Get one paper",
    )
    def get_paper(request: Request, paper_id: str) -> dict:
        paper = get_service(request).get_paper(paper_id)
        if paper is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper not found: {paper_id}",
            )
        return paper

    return application


app = create_app()
