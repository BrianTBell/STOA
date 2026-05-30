"""Lightweight input screening for obvious junk or unusable uploads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntakeScreenResult:
    decision: str
    rationale: str

    @property
    def accepted(self) -> bool:
        return self.decision == "accept"


def build_intake_screen_input(
    *,
    source_type: str,
    source_label: str,
    extracted_text_preview: str,
    extracted_text_full: str,
    title: str | None = None,
    authors: list[str] | None = None,
    published: str | None = None,
) -> dict:
    payload = {
        "source_type": source_type,
        "source_label": source_label,
        "extracted_text_preview": extracted_text_preview,
        "extracted_text_full": extracted_text_full,
    }
    if title:
        payload["title"] = title
    if authors:
        payload["authors"] = authors
    if published:
        payload["published"] = published
    return payload


def validate_intake_screen_result(result: dict) -> IntakeScreenResult:
    decision = str(result.get("decision", "")).strip().lower()
    rationale = str(result.get("rationale", "")).strip()

    if decision not in {"accept", "reject"}:
        raise ValueError("Intake screen response must set decision to 'accept' or 'reject'")
    if not rationale:
        raise ValueError("Intake screen response must include a short rationale")

    return IntakeScreenResult(decision=decision, rationale=rationale)
