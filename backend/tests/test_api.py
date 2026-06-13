from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from urllib.parse import urlencode

from backend.api import create_app


def sample_paper(paper_id: str = "localpdf:abc123") -> dict[str, Any]:
    return {
        "id": paper_id,
        "source_url": "localpdf://abc123/paper.pdf",
        "title": "Example Paper",
        "authors": ["Ada Example"],
        "published": None,
        "summary": "A short example summary.",
        "concepts": ["example concept"],
        "methods": ["example method"],
        "domain": "engineering",
        "created_at": "2026-06-13T12:00:00+00:00",
        "updated_at": "2026-06-13T12:00:00+00:00",
    }


class FakeService:
    def __init__(self) -> None:
        self.pdf_call: tuple[bytes, str, str | None] | None = None
        self.arxiv_call: str | None = None

    def _ingestion_result(self, paper_id: str) -> dict[str, Any]:
        return {
            "intake_screen": {
                "decision": "accept",
                "rationale": "The upload is an academic paper.",
            },
            "paper": sample_paper(paper_id),
            "vocabulary_resolution": {"types": {}, "vocab_updates": []},
            "similarity_edges": [],
        }

    def ingest_pdf(
        self,
        pdf_bytes: bytes,
        filename: str,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        self.pdf_call = (pdf_bytes, filename, source_url)
        return self._ingestion_result("localpdf:abc123")

    def ingest_arxiv(self, arxiv_id: str) -> dict[str, Any]:
        self.arxiv_call = arxiv_id
        return self._ingestion_result(f"arxiv:{arxiv_id}")

    def list_papers(self, limit: int) -> list[dict[str, Any]]:
        return [sample_paper()][:limit]

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        if paper_id == "missing":
            return None
        return sample_paper(paper_id)

    def get_similarity(self, paper_id: str, limit: int) -> dict[str, Any]:
        if paper_id == "missing":
            raise ValueError("Paper not found: missing")
        return {
            "id": paper_id,
            "matches": [{"score": 0.91, "paper": sample_paper("localpdf:neighbor")}][:limit],
        }

    def get_edges(self, paper_id: str, limit: int) -> dict[str, Any]:
        if paper_id == "missing":
            raise ValueError("Paper not found: missing")
        return {
            "id": paper_id,
            "edges": [
                {
                    "direction": "outgoing",
                    "score": 0.91,
                    "created_at": "2026-06-13T12:00:00+00:00",
                    "updated_at": "2026-06-13T12:00:00+00:00",
                    "paper": sample_paper("localpdf:neighbor"),
                }
            ][:limit],
        }


async def asgi_request(
    app: Any,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: bytes = b"",
    content_type: str | None = None,
) -> tuple[int, Any]:
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    headers = []
    if content_type:
        headers.append((b"content-type", content_type.encode("ascii")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": urlencode(query or {}).encode("ascii"),
        "headers": headers,
        "client": ("test", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async with app.router.lifespan_context(app):
        await app(scope, receive, send)

    response_start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return response_start["status"], json.loads(response_body or b"null")


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeService()
        self.app = create_app(self.service)

    def request(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        return asyncio.run(asgi_request(self.app, method, path, **kwargs))

    def test_openapi_contains_phase_seven_routes(self) -> None:
        paths = self.app.openapi()["paths"]
        self.assertIn("/ingest/pdf", paths)
        self.assertIn("/ingest/arxiv", paths)
        self.assertIn("/papers", paths)
        self.assertIn("/papers/{paper_id}/edges", paths)
        self.assertIn("/papers/{paper_id}/similar", paths)
        self.assertIn("/papers/{paper_id}", paths)

    def test_pdf_ingestion_accepts_raw_pdf_body(self) -> None:
        status_code, response = self.request(
            "POST",
            "/ingest/pdf",
            query={"filename": "paper.pdf"},
            body=b"%PDF-test",
            content_type="application/pdf",
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(response["paper"]["id"], "localpdf:abc123")
        self.assertEqual(self.service.pdf_call, (b"%PDF-test", "paper.pdf", None))

    def test_arxiv_ingestion_accepts_json(self) -> None:
        status_code, response = self.request(
            "POST",
            "/ingest/arxiv",
            body=json.dumps({"arxiv_id": "2301.04567"}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(response["paper"]["id"], "arxiv:2301.04567")
        self.assertEqual(self.service.arxiv_call, "2301.04567")

    def test_graph_read_endpoints(self) -> None:
        list_status, papers = self.request("GET", "/papers")
        paper_status, paper = self.request("GET", "/papers/localpdf:abc123")
        edges_status, edges = self.request("GET", "/papers/localpdf:abc123/edges")
        similar_status, similar = self.request("GET", "/papers/localpdf:abc123/similar")

        self.assertEqual(list_status, 200)
        self.assertEqual(len(papers), 1)
        self.assertEqual(paper_status, 200)
        self.assertEqual(paper["id"], "localpdf:abc123")
        self.assertEqual(edges_status, 200)
        self.assertEqual(edges["edges"][0]["score"], 0.91)
        self.assertEqual(similar_status, 200)
        self.assertEqual(similar["matches"][0]["score"], 0.91)

    def test_missing_paper_returns_404(self) -> None:
        status_code, response = self.request("GET", "/papers/missing")
        self.assertEqual(status_code, 404)
        self.assertEqual(response["detail"], "Paper not found: missing")

    def test_legacy_arxiv_id_with_slash_is_supported(self) -> None:
        status_code, response = self.request(
            "GET",
            "/papers/arxiv:hep-th/9901001/similar",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(response["id"], "arxiv:hep-th/9901001")


test_app = create_app(FakeService())


if __name__ == "__main__":
    unittest.main()
