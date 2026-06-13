"""Request and response models exposed by the Phase 7 API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ArxivIngestRequest(BaseModel):
    arxiv_id: str = Field(min_length=1, examples=["2301.04567"])


class IntakeScreenResponse(BaseModel):
    decision: str
    rationale: str


class PaperResponse(BaseModel):
    id: str
    source_url: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    published: str | None = None
    summary: str | None = None
    concepts: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    domain: str | None = None
    created_at: str
    updated_at: str


class WrittenEdgeResponse(BaseModel):
    paper_id: str
    score: float
    created_at: str
    updated_at: str


class IngestionResponse(BaseModel):
    intake_screen: IntakeScreenResponse
    paper: PaperResponse
    vocabulary_resolution: dict[str, Any]
    similarity_edges: list[WrittenEdgeResponse]


class SimilarPaperResponse(BaseModel):
    score: float
    paper: PaperResponse


class SimilarityResponse(BaseModel):
    id: str
    matches: list[SimilarPaperResponse]


class EdgeResponse(BaseModel):
    direction: str
    score: float
    created_at: str
    updated_at: str
    paper: PaperResponse


class PaperEdgesResponse(BaseModel):
    id: str
    edges: list[EdgeResponse]
