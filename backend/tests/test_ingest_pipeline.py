from __future__ import annotations

import unittest

from backend.ingest.pipeline import (
    build_local_pdf_id,
    build_local_pdf_source_url,
    parse_json_response,
)


class IngestPipelineTests(unittest.TestCase):
    def test_local_pdf_identity_is_stable(self) -> None:
        paper_id = build_local_pdf_id(b"same file bytes")
        self.assertEqual(paper_id, build_local_pdf_id(b"same file bytes"))
        self.assertNotEqual(paper_id, build_local_pdf_id(b"different file bytes"))
        self.assertEqual(
            build_local_pdf_source_url(paper_id, r"C:\papers\example paper.pdf"),
            f"localpdf://{paper_id.removeprefix('localpdf:')}/example%20paper.pdf",
        )

    def test_claude_json_parser_accepts_code_fences(self) -> None:
        result = parse_json_response('```json\n{"decision": "accept"}\n```')
        self.assertEqual(result, {"decision": "accept"})


if __name__ == "__main__":
    unittest.main()
