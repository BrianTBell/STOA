from __future__ import annotations

import datetime
from typing import Any

from neo4j import GraphDatabase

from .config import Neo4jConfig


class Neo4jPaperStore:
    """Owns the Neo4j driver and Paper/Vocabulary Cypher for storage."""

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
        paper_query = """
        CREATE CONSTRAINT paper_id_unique IF NOT EXISTS
        FOR (paper:Paper)
        REQUIRE paper.id IS UNIQUE
        """
        vocab_query = """
        CREATE CONSTRAINT vocab_id_unique IF NOT EXISTS
        FOR (vocab:Vocabulary)
        REQUIRE vocab.id IS UNIQUE
        """
        with self._driver.session() as session:
            session.run(paper_query).consume()
            session.run(vocab_query).consume()

    def _now_iso(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def _canonical_pair(self, paper_id_a: str, paper_id_b: str) -> tuple[str, str]:
        return tuple(sorted((paper_id_a, paper_id_b)))

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

    def list_vocabulary(self, term_type: str | None = None, limit: int = 5000) -> list[dict[str, Any]]:
        if term_type:
            query = """
            MATCH (vocab:Vocabulary {type: $term_type})
            RETURN vocab
            ORDER BY vocab.term ASC
            LIMIT $limit
            """
            params = {"term_type": term_type, "limit": limit}
        else:
            query = """
            MATCH (vocab:Vocabulary)
            RETURN vocab
            ORDER BY vocab.type ASC, vocab.term ASC
            LIMIT $limit
            """
            params = {"limit": limit}

        with self._driver.session() as session:
            result = session.run(query, **params)
            return [dict(record["vocab"]) for record in result]

    def upsert_vocabulary_entries(self, entries: list[dict[str, Any]]) -> None:
        if not entries:
            return

        query = """
        UNWIND $entries AS entry
        MERGE (vocab:Vocabulary {id: entry.id})
        ON CREATE SET
            vocab.term = entry.term,
            vocab.type = entry.type,
            vocab.aliases = entry.aliases,
            vocab.first_seen = entry.first_seen,
            vocab.use_count = entry.use_count_increment
        ON MATCH SET
            vocab.term = entry.term,
            vocab.type = entry.type,
            vocab.first_seen = coalesce(vocab.first_seen, entry.first_seen),
            vocab.use_count = coalesce(vocab.use_count, 0) + entry.use_count_increment,
            vocab.aliases = reduce(
                merged = coalesce(vocab.aliases, []),
                alias IN entry.aliases |
                    CASE
                        WHEN alias IN merged THEN merged
                        ELSE merged + alias
                    END
            )
        """
        with self._driver.session() as session:
            session.run(query, entries=entries).consume()

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

    def regenerate_similarity_edges(
        self,
        paper_id: str,
        limit: int = 3,
        min_score: float = 0.80,
    ) -> list[dict[str, Any]]:
        matches = [
            match
            for match in self.find_similar_papers(paper_id, limit=limit)
            if match["score"] >= min_score
        ]
        timestamp = self._now_iso()
        upsert_query = """
        UNWIND $matches AS match
        MATCH (source:Paper {id: match.source_id})
        MATCH (target:Paper {id: match.target_id})
        MERGE (source)-[edge:SIMILAR_TO]->(target)
        ON CREATE SET edge.created_at = $timestamp
        SET
            edge.score = CASE
                WHEN edge.score IS NULL OR match.score > edge.score THEN match.score
                ELSE edge.score
            END,
            edge.updated_at = $timestamp
        RETURN source.id AS source_id, target.id AS target_id, edge.score AS score, edge.created_at AS created_at, edge.updated_at AS updated_at
        ORDER BY score DESC
        """

        canonical_matches = []
        for match in matches:
            source_id, target_id = self._canonical_pair(paper_id, match["paper"]["id"])
            canonical_matches.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "score": match["score"],
                }
            )

        with self._driver.session() as session:
            result = session.run(
                upsert_query,
                timestamp=timestamp,
                matches=canonical_matches,
            )
            written_edges = [
                {
                    "paper_id": record["target_id"] if record["source_id"] == paper_id else record["source_id"],
                    "score": float(record["score"]),
                    "created_at": record["created_at"],
                    "updated_at": record["updated_at"],
                }
                for record in result
            ]
        self.normalize_all_similarity_edges()
        return written_edges

    def normalize_all_similarity_edges(self) -> None:
        query = """
        MATCH (left:Paper)-[edge:SIMILAR_TO]->(right:Paper)
        RETURN left.id AS left_id, right.id AS right_id, edge.score AS score, edge.created_at AS created_at
        """
        rows: list[dict[str, Any]] = []
        with self._driver.session() as session:
            result = session.run(query)
            rows = [dict(record) for record in result]

        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            source_id, target_id = self._canonical_pair(row["left_id"], row["right_id"])
            group = grouped.setdefault(
                (source_id, target_id),
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "score": float(row["score"]) if row["score"] is not None else 0.0,
                    "created_at": row["created_at"] or self._now_iso(),
                },
            )
            if row["score"] is not None:
                group["score"] = max(group["score"], float(row["score"]))
            created_at = row["created_at"]
            if created_at and created_at < group["created_at"]:
                group["created_at"] = created_at

        if not rows:
            return

        timestamp = self._now_iso()
        delete_query = "MATCH ()-[edge:SIMILAR_TO]->() DELETE edge"
        create_query = """
        UNWIND $pairs AS pair
        MATCH (source:Paper {id: pair.source_id})
        MATCH (target:Paper {id: pair.target_id})
        MERGE (source)-[edge:SIMILAR_TO]->(target)
        SET
            edge.score = pair.score,
            edge.created_at = pair.created_at,
            edge.updated_at = $timestamp
        """
        pairs = list(grouped.values())
        with self._driver.session() as session:
            session.run(delete_query).consume()
            session.run(create_query, pairs=pairs, timestamp=timestamp).consume()

    def list_similarity_edges(
        self,
        paper_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self.get_paper(paper_id) is None:
            raise ValueError(f"Paper not found: {paper_id}")

        query = """
        MATCH (paper:Paper {id: $paper_id})
        CALL (paper) {
            MATCH (paper)-[edge:SIMILAR_TO]->(neighbor:Paper)
            RETURN 'outgoing' AS direction, neighbor, edge
            UNION ALL
            MATCH (neighbor:Paper)-[edge:SIMILAR_TO]->(paper)
            RETURN 'incoming' AS direction, neighbor, edge
        }
        RETURN direction, neighbor AS paper, edge
        ORDER BY edge.score DESC, paper.id ASC
        LIMIT $limit
        """
        with self._driver.session() as session:
            result = session.run(query, paper_id=paper_id, limit=limit)
            return [
                {
                    "direction": record["direction"],
                    "paper": dict(record["paper"]),
                    "edge": dict(record["edge"]),
                }
                for record in result
            ]

    def delete_paper(self, paper_id: str) -> bool:
        query = """
        MATCH (paper:Paper {id: $paper_id})
        WITH paper, count(paper) AS matches
        DETACH DELETE paper
        RETURN matches > 0 AS deleted
        """
        with self._driver.session() as session:
            record = session.run(query, paper_id=paper_id).single()
        if record is None:
            return False
        return bool(record["deleted"])
