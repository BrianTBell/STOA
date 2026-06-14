from __future__ import annotations

import unittest

from backend.store.neighbor_policy import select_top_neighbors


class NeighborPolicyTests(unittest.TestCase):
    def test_selects_top_neighbors_above_threshold(self) -> None:
        candidates = [
            {"paper_id": "paper:d", "score": 0.74},
            {"paper_id": "paper:b", "score": 0.91},
            {"paper_id": "paper:c", "score": 0.82},
            {"paper_id": "paper:a", "score": 0.95},
            {"paper_id": "paper:e", "score": 0.80},
        ]

        self.assertEqual(
            select_top_neighbors(candidates, limit=3, min_score=0.75),
            [
                {"paper_id": "paper:a", "score": 0.95},
                {"paper_id": "paper:b", "score": 0.91},
                {"paper_id": "paper:c", "score": 0.82},
            ],
        )

    def test_uses_paper_id_to_break_equal_score_ties(self) -> None:
        candidates = [
            {"paper_id": "paper:c", "score": 0.8},
            {"paper_id": "paper:a", "score": 0.8},
            {"paper_id": "paper:b", "score": 0.8},
        ]

        self.assertEqual(
            select_top_neighbors(candidates, limit=2, min_score=0.75),
            [
                {"paper_id": "paper:a", "score": 0.8},
                {"paper_id": "paper:b", "score": 0.8},
            ],
        )

    def test_keeps_best_duplicate_candidate_score(self) -> None:
        candidates = [
            {"paper_id": "paper:a", "score": 0.78},
            {"paper_id": "paper:a", "score": 0.88},
        ]

        self.assertEqual(
            select_top_neighbors(candidates, limit=3, min_score=0.75),
            [{"paper_id": "paper:a", "score": 0.88}],
        )


if __name__ == "__main__":
    unittest.main()
