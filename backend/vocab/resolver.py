from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = ROOT / "backend" / "extract" / "prompts" / "vocab_resolution_prompt_v1.txt"
TERM_TYPES = ("concept", "method", "domain")


@dataclass
class VocabularyResolutionResult:
    resolved_paper: dict[str, Any]
    resolution_log: dict[str, Any]


def load_vocab_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[prompt file not found: {PROMPT_PATH.relative_to(ROOT)}]"


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def is_specific_algorithm_term(term: str) -> bool:
    normalized = normalize_term(term)
    algorithm_markers = (
        "q-learning",
        "ppo",
        "trpo",
        "sac",
        "dqn",
        "deep q",
        "actor-critic",
        "policy gradient",
        "temporal difference",
        "temporal-difference",
    )
    return any(marker in normalized for marker in algorithm_markers)


def is_broad_category_term(term: str) -> bool:
    normalized = normalize_term(term)
    category_markers = (
        "methods",
        "learning",
        "algorithms",
        "approaches",
        "techniques",
        "family",
    )
    return any(marker in normalized for marker in category_markers)


def alias_allowed(term_type: str, source_term: str, canonical_term: str) -> bool:
    if term_type != "concept":
        return True

    if is_specific_algorithm_term(source_term) and is_broad_category_term(canonical_term):
        return False

    return True


def build_vocab_id(term_type: str, canonical_term: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_term(canonical_term)).strip("-")
    return f"vocab:{term_type}:{slug}"


def dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        normalized = normalize_term(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(term.strip())
    return ordered


def build_vocab_lookups(vocabulary_entries: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    exact_lookup: dict[str, str] = {}
    alias_lookup: dict[str, str] = {}

    for entry in vocabulary_entries:
        canonical_term = str(entry.get("term") or "").strip()
        if not canonical_term:
            continue

        exact_lookup[normalize_term(canonical_term)] = canonical_term
        aliases = entry.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                alias_text = str(alias).strip()
                if alias_text:
                    alias_lookup[normalize_term(alias_text)] = canonical_term

    return exact_lookup, alias_lookup


def local_resolution(
    extracted_terms: list[str],
    exact_lookup: dict[str, str],
    alias_lookup: dict[str, str],
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    resolved: list[str] = []
    unresolved: list[str] = []
    local_log: list[dict[str, str]] = []

    for term in extracted_terms:
        normalized = normalize_term(term)
        if not normalized:
            continue

        if normalized in exact_lookup:
            canonical = exact_lookup[normalized]
            resolved.append(canonical)
            local_log.append({"term": term, "decision": "exact", "canonical_term": canonical})
            continue

        if normalized in alias_lookup:
            canonical = alias_lookup[normalized]
            resolved.append(canonical)
            local_log.append({"term": term, "decision": "known_alias", "canonical_term": canonical})
            continue

        unresolved.append(term)

    return dedupe_terms(resolved), unresolved, local_log


def resolve_with_claude(
    term_type: str,
    unresolved_terms: list[str],
    vocabulary_entries: list[dict[str, Any]],
    claude_query: Callable[[str], Any],
) -> list[dict[str, str]]:
    if not unresolved_terms:
        return []

    prompt = load_vocab_prompt()
    input_data = {
        "term_type": term_type,
        "unresolved_terms": unresolved_terms,
        "existing_canonical_terms": [
            str(entry.get("term") or "").strip()
            for entry in vocabulary_entries
            if str(entry.get("term") or "").strip()
        ],
    }
    full_prompt = f"{prompt}\n\nINPUT JSON:\n{json.dumps(input_data, indent=2)}\n"
    response = claude_query(full_prompt)

    if not isinstance(response, list):
        raise ValueError(f"Vocabulary resolution expected a JSON list for {term_type}.")

    unresolved_by_normalized = {normalize_term(term): term for term in unresolved_terms}
    decisions: list[dict[str, str]] = []

    for item in response:
        if not isinstance(item, dict):
            continue

        extracted_term = str(item.get("extracted_term") or "").strip()
        decision = str(item.get("decision") or "").strip().lower()
        canonical_term = str(item.get("canonical_term") or "").strip()

        if normalize_term(extracted_term) not in unresolved_by_normalized:
            continue
        if decision not in {"alias", "new"} or not canonical_term:
            continue

        source_term = unresolved_by_normalized[normalize_term(extracted_term)]
        if decision == "alias" and not alias_allowed(term_type, source_term, canonical_term):
            decision = "new"
            canonical_term = source_term.strip()

        decisions.append({"term": source_term, "decision": decision, "canonical_term": canonical_term})

    return decisions


def build_vocab_updates(term_type: str, resolution_log: list[dict[str, str]]) -> list[dict[str, Any]]:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    merged: dict[str, dict[str, Any]] = {}

    for log_entry in resolution_log:
        canonical_term = log_entry["canonical_term"].strip()
        key = normalize_term(canonical_term)
        current = merged.get(key)
        if current is None:
            current = {
                "id": build_vocab_id(term_type, canonical_term),
                "term": canonical_term,
                "type": term_type,
                "aliases": [],
                "first_seen": timestamp,
                "use_count_increment": 0,
            }
            merged[key] = current

        current["use_count_increment"] += 1
        if log_entry["decision"] in {"known_alias", "alias"}:
            alias_term = log_entry["term"].strip()
            if normalize_term(alias_term) != key and alias_term not in current["aliases"]:
                current["aliases"].append(alias_term)

    return list(merged.values())


def resolve_paper_vocabulary(
    paper_record: dict[str, Any],
    vocabulary_by_type: dict[str, list[dict[str, Any]]],
    claude_query: Callable[[str], Any],
) -> VocabularyResolutionResult:
    resolved_paper = dict(paper_record)
    resolution_log: dict[str, Any] = {"types": {}, "vocab_updates": []}
    all_updates: list[dict[str, Any]] = []

    type_to_field = {"concept": "concepts", "method": "methods", "domain": "domain"}

    for term_type in TERM_TYPES:
        vocabulary_entries = vocabulary_by_type.get(term_type, [])
        exact_lookup, alias_lookup = build_vocab_lookups(vocabulary_entries)

        raw_value = resolved_paper.get(type_to_field[term_type])
        if term_type == "domain":
            extracted_terms = [raw_value] if isinstance(raw_value, str) and raw_value.strip() else []
        else:
            extracted_terms = [term for term in raw_value if isinstance(term, str)] if isinstance(raw_value, list) else []

        local_resolved, unresolved, local_log = local_resolution(extracted_terms, exact_lookup, alias_lookup)
        claude_log = resolve_with_claude(term_type, unresolved, vocabulary_entries, claude_query)

        handled = {normalize_term(entry["term"]) for entry in claude_log}
        for term in unresolved:
            if normalize_term(term) not in handled:
                claude_log.append({"term": term, "decision": "new", "canonical_term": term.strip()})

        claude_resolved = [entry["canonical_term"].strip() for entry in claude_log]
        final_terms = dedupe_terms(local_resolved + claude_resolved)

        if term_type == "domain":
            resolved_paper["domain"] = final_terms[0] if final_terms else None
        else:
            resolved_paper[type_to_field[term_type]] = final_terms

        type_log = {
            "local": local_log,
            "claude": claude_log,
            "final_terms": final_terms,
        }
        resolution_log["types"][term_type] = type_log
        all_updates.extend(build_vocab_updates(term_type, local_log + claude_log))

    merged_updates: dict[tuple[str, str], dict[str, Any]] = {}
    for update in all_updates:
        key = (update["type"], normalize_term(update["term"]))
        current = merged_updates.get(key)
        if current is None:
            merged_updates[key] = update
            continue
        current["use_count_increment"] += update["use_count_increment"]
        for alias in update["aliases"]:
            if alias not in current["aliases"]:
                current["aliases"].append(alias)

    resolution_log["vocab_updates"] = list(merged_updates.values())
    return VocabularyResolutionResult(resolved_paper=resolved_paper, resolution_log=resolution_log)
