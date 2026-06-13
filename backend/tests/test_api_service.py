from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.api.service import StoaService
from backend.ingest.pipeline import ClaudeConfig, IngestionResult, PreparedPaper
from backend.screen import IntakeScreenResult


def sample_paper() -> dict:
    return {
        "id": "localpdf:abc123",
        "source_url": "localpdf://abc123/paper.pdf",
        "title": "Example Paper",
        "authors": [],
        "published": None,
        "summary": "Summary",
        "concepts": [],
        "methods": [],
        "domain": None,
        "embedding": [0.1, 0.2],
        "created_at": "2026-06-13T12:00:00+00:00",
        "updated_at": "2026-06-13T12:00:00+00:00",
    }


class FakeStore:
    def list_papers(self, limit: int) -> list[dict]:
        return [sample_paper()][:limit]

    def get_paper(self, paper_id: str) -> dict | None:
        return sample_paper() if paper_id == "localpdf:abc123" else None


class ApiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        self.config = ClaudeConfig(
            api_key="test-key",
            api_base="https://example.invalid",
        )
        self.service = StoaService(self.store, self.config)

    def test_read_responses_do_not_expose_embeddings(self) -> None:
        papers = self.service.list_papers(limit=10)
        paper = self.service.get_paper("localpdf:abc123")

        self.assertNotIn("embedding", papers[0])
        self.assertIsNotNone(paper)
        self.assertNotIn("embedding", paper)

    @patch("backend.api.service.ingest_prepared_paper")
    @patch("backend.api.service.prepare_pdf_bytes")
    def test_pdf_ingestion_delegates_to_shared_pipeline(
        self,
        prepare_pdf_bytes_mock,
        ingest_prepared_paper_mock,
    ) -> None:
        prepared = PreparedPaper(
            source_type="pdf",
            extraction_prompt="prompt",
            extraction_input={},
            intake_input={},
            paper_id="localpdf:abc123",
            source_url="localpdf://abc123/paper.pdf",
            metadata={},
            source_name="paper.pdf",
        )
        prepare_pdf_bytes_mock.return_value = prepared
        ingest_prepared_paper_mock.return_value = IngestionResult(
            intake_screen=IntakeScreenResult(
                decision="accept",
                rationale="Academic paper.",
            ),
            paper=sample_paper(),
            vocabulary_resolution={"types": {}, "vocab_updates": []},
            similarity_edges=[],
        )

        response = self.service.ingest_pdf(b"%PDF-test", "paper.pdf")

        prepare_pdf_bytes_mock.assert_called_once_with(
            b"%PDF-test",
            "paper.pdf",
            source_url=None,
        )
        ingest_prepared_paper_mock.assert_called_once_with(
            prepared,
            self.config,
            self.store,
        )
        self.assertNotIn("embedding", response["paper"])


if __name__ == "__main__":
    unittest.main()
