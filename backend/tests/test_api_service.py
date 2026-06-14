from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.api.service import DuplicatePaperError, StoaService
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

    def get_graph(self, limit: int) -> dict:
        paper = sample_paper()
        neighbor = {**sample_paper(), "id": "localpdf:neighbor"}
        return {
            "papers": [paper, neighbor][:limit],
            "edges": [
                {
                    "source_id": paper["id"],
                    "target_id": neighbor["id"],
                    "score": 0.91,
                    "nominated_by": [paper["id"]],
                    "created_at": "2026-06-13T12:00:00+00:00",
                    "updated_at": "2026-06-13T12:00:00+00:00",
                }
            ],
        }


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

    def test_graph_edges_expose_nominators(self) -> None:
        graph = self.service.get_graph(limit=10)

        self.assertEqual(
            graph["edges"][0]["nominated_by"],
            ["localpdf:abc123"],
        )
        self.assertNotIn("embedding", graph["papers"][0])

    @patch("backend.api.service.prepare_pdf_bytes")
    @patch("backend.api.service.build_local_pdf_id", return_value="localpdf:abc123")
    def test_duplicate_pdf_stops_before_preparation(
        self,
        _build_local_pdf_id_mock,
        prepare_pdf_bytes_mock,
    ) -> None:
        with self.assertRaises(DuplicatePaperError):
            self.service.ingest_pdf(b"%PDF-test", "paper.pdf")

        prepare_pdf_bytes_mock.assert_not_called()

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
