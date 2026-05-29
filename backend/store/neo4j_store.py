from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from .config import Neo4jConfig


class Neo4jPaperStore:
    """Owns the Neo4j driver and Paper-node Cypher for storage and embeddings."""

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

    def ensure_vector_index(self, dimensions: int) -> None:
        query = """
        CREATE VECTOR INDEX paper_embedding_index IF NOT EXISTS
        FOR (paper:Paper)
        ON (paper.embedding)
        OPTIONS {
            indexConfig: {
                `vector.dimensions`: $dimensions,
                `vector.similarity_function`: 'cosine'
            }
        }
        """
        with self._driver.session() as session:
            session.run(query, dimensions=dimensions).consume()

    def get_vector_index_status(self) -> dict[str, Any] | None:
        query = """
        SHOW VECTOR INDEXES
        YIELD name, state, populationPercent, type, entityType, labelsOrTypes, properties
        WHERE name = 'paper_embedding_index'
        RETURN {
            name: name,
            state: state,
            populationPercent: populationPercent,
            type: type,
            entityType: entityType,
            labelsOrTypes: labelsOrTypes,
            properties: properties
        } AS index_info
        """
        with self._driver.session() as session:
            record = session.run(query).single()
        if record is None:
            return None
        return dict(record["index_info"])

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
            paper.embedding = $embedding,
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

    def set_paper_embedding(self, paper_id: str, embedding: list[float]) -> dict[str, Any] | None:
        query = """
        MATCH (paper:Paper {id: $paper_id})
        SET paper.embedding = $embedding
        RETURN paper
        """
        with self._driver.session() as session:
            record = session.run(query, paper_id=paper_id, embedding=embedding).single()
        if record is None:
            return None
        return dict(record["paper"])

    def _find_similar_papers(
        self,
        paper_id: str,
        embedding: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        query = """
        CYPHER 25
        MATCH (candidate:Paper)
        SEARCH candidate IN (
            VECTOR INDEX paper_embedding_index
            FOR $embedding
            LIMIT $query_limit
        ) SCORE AS score
        WHERE candidate.id <> $paper_id
        RETURN candidate AS paper, score
        ORDER BY score DESC
        LIMIT $result_limit
        """
        with self._driver.session() as session:
            result = session.run(
                query,
                paper_id=paper_id,
                embedding=embedding,
                query_limit=limit + 1,
                result_limit=limit,
            )
            return [
                {
                    "score": float(record["score"]),
                    "paper": dict(record["paper"]),
                }
                for record in result
            ]

    def find_similar_papers(
        self,
        paper_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        paper = self.get_paper(paper_id)
        if paper is None:
            raise ValueError(f"Paper not found: {paper_id}")

        embedding = paper.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise ValueError(f"Paper has no embedding: {paper_id}")

        return self._find_similar_papers(paper_id, embedding, limit)

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
