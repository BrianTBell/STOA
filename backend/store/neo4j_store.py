from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from .config import Neo4jConfig


class Neo4jPaperStore:
    """Owns the Neo4j driver and Paper-node Cypher for Phase 2."""

    def __init__(self, config: Neo4jConfig) -> None:
        self._driver = GraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
        )

    def close(self) -> None:
        self._driver.close()

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def ensure_schema(self) -> None:
        query = """
        CREATE CONSTRAINT paper_id_unique IF NOT EXISTS
        FOR (paper:Paper)
        REQUIRE paper.id IS UNIQUE
        """
        with self._driver.session() as session:
            session.run(query).consume()

    def upsert_paper(self, paper: dict[str, Any]) -> dict[str, Any]:
        query = """
        MERGE (paper:Paper {id: $id})
        ON CREATE SET paper.created_at = $created_at
        SET
            paper.source_url = $source_url,
            paper.title = $title,
            paper.authors = $authors,
            paper.published = $published,
            paper.summary = $summary,
            paper.concepts = $concepts,
            paper.methods = $methods,
            paper.domain = $domain,
            paper.updated_at = $updated_at
        RETURN paper
        """
        with self._driver.session() as session:
            record = session.run(query, **paper).single()
        if record is None:
            raise RuntimeError("Neo4j did not return the stored Paper node.")
        return dict(record["paper"])

    def list_papers(self, limit: int = 100) -> list[dict[str, Any]]:
        query = """
        MATCH (paper:Paper)
        RETURN paper
        ORDER BY paper.id ASC
        LIMIT $limit
        """
        with self._driver.session() as session:
            result = session.run(query, limit=limit)
            return [dict(record["paper"]) for record in result]

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        query = """
        MATCH (paper:Paper {id: $paper_id})
        RETURN paper
        """
        with self._driver.session() as session:
            record = session.run(query, paper_id=paper_id).single()
        if record is None:
            return None
        return dict(record["paper"])

    def delete_paper(self, paper_id: str) -> bool:
        query = """
        MATCH (paper:Paper {id: $paper_id})
        WITH paper, count(paper) AS matches
        DELETE paper
        RETURN matches > 0 AS deleted
        """
        with self._driver.session() as session:
            record = session.run(query, paper_id=paper_id).single()
        if record is None:
            return False
        return bool(record["deleted"])
