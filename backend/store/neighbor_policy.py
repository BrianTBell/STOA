from __future__ import annotations

from typing import Any, Iterable


def select_top_neighbors(
    candidates: Iterable[dict[str, Any]],
    limit: int,
    min_score: float,
) -> list[dict[str, Any]]:
    """Return a deterministic paper's nearest eligible neighbors."""
    best_by_id: dict[str, float] = {}
    for candidate in candidates:
        paper_id = str(candidate["paper_id"])
        score = float(candidate["score"])
        if score < min_score:
            continue
        best_by_id[paper_id] = max(score, best_by_id.get(paper_id, float("-inf")))

    ranked = sorted(
        (
            {"paper_id": paper_id, "score": score}
            for paper_id, score in best_by_id.items()
        ),
        key=lambda candidate: (-candidate["score"], candidate["paper_id"]),
    )
    return ranked[:limit]
