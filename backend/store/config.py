from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str


def load_neo4j_config() -> Neo4jConfig:
    load_dotenv(ROOT / ".env")

    uri = os.environ.get("NEO4J_URI", "").strip()
    username = os.environ.get("NEO4J_USERNAME", "").strip()
    password = os.environ.get("NEO4J_PASSWORD", "").strip()

    missing = [
        name
        for name, value in (
            ("NEO4J_URI", uri),
            ("NEO4J_USERNAME", username),
            ("NEO4J_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        missing_names = ", ".join(missing)
        raise RuntimeError(
            f"Missing Neo4j configuration in .env: {missing_names}. "
            "Phase 2 storage commands need all three values."
        )

    return Neo4jConfig(uri=uri, username=username, password=password)
