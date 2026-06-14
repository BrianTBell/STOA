from __future__ import annotations

import datetime
from typing import Any

from neo4j import GraphDatabase

from .config import Neo4jConfig
from .neighbor_policy import select_top_neighbors


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

    def get_graph(self, limit: int = 1000) -> dict[str, list[dict[str, Any]]]:
        papers = self.list_papers(limit=limit)
        paper_ids = [paper["id"] for paper in papers]
        if not paper_ids:
            return {"papers": [], "edges": []}

        query = """
        MATCH (source:Paper)-[edge:SIMILAR_TO]->(target:Paper)
        WHERE source.id IN $paper_ids AND target.id IN $paper_ids
        RETURN
            source.id AS source_id,
            target.id AS target_id,
            edge.score AS score,
            coalesce(edge.nominated_by, []) AS nominated_by,
            edge.created_at AS created_at,
            edge.updated_at AS updated_at
        ORDER BY score DESC, source_id ASC, target_id ASC
        """
        with self._driver.session() as session:
            result = session.run(query, paper_ids=paper_ids)
            edges = [
                {
                    "source_id": record["source_id"],
                    "target_id": record["target_id"],
                    "score": float(record["score"]),
                    "nominated_by": list(record["nominated_by"]),
                    "created_at": record["created_at"],
                    "updated_at": record["updated_at"],
                }
                for record in result
            ]
        return {"papers": papers, "edges": edges}

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
        min_score: float = 0.65,
    ) -> list[dict[str, Any]]:
        if self._has_legacy_similarity_edges():
            self.rebuild_similarity_edges(limit=limit, min_score=min_score)
            return self._formatted_incident_edges(paper_id)

        scores = self._exact_similarity_scores(paper_id, min_score)
        new_nominations = select_top_neighbors(scores, limit, min_score)

        candidate_ids = [score["paper_id"] for score in scores]
        current_by_paper = self._list_nominations(candidate_ids)
        updates = [{"paper_id": paper_id, "neighbors": new_nominations}]

        for score in scores:
            candidate_id = score["paper_id"]
            current = current_by_paper.get(candidate_id, [])
            desired = select_top_neighbors(
                [*current, {"paper_id": paper_id, "score": score["score"]}],
                limit,
                min_score,
            )
            if desired != current:
                updates.append({"paper_id": candidate_id, "neighbors": desired})

        self._sync_nominations(updates)
        return self._formatted_incident_edges(paper_id)

    def _has_legacy_similarity_edges(self) -> bool:
        query = """
        MATCH ()-[edge:SIMILAR_TO]->()
        WHERE edge.nominated_by IS NULL
        RETURN count(edge) > 0 AS has_legacy_edges
        """
        with self._driver.session() as session:
            record = session.run(query).single()
        return bool(record["has_legacy_edges"]) if record is not None else False

    def _exact_similarity_scores(
        self,
        paper_id: str,
        min_score: float,
    ) -> list[dict[str, Any]]:
        query = """
        MATCH (paper:Paper {id: $paper_id})
        MATCH (candidate:Paper)
        WHERE
            candidate.id <> paper.id
            AND paper.embedding IS NOT NULL
            AND candidate.embedding IS NOT NULL
        WITH
            candidate.id AS paper_id,
            vector.similarity.cosine(paper.embedding, candidate.embedding) AS score
        WHERE score >= $min_score
        RETURN paper_id, score
        ORDER BY score DESC, paper_id ASC
        """
        with self._driver.session() as session:
            result = session.run(query, paper_id=paper_id, min_score=min_score)
            return [
                {"paper_id": record["paper_id"], "score": float(record["score"])}
                for record in result
            ]

    def _list_nominations(
        self,
        paper_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        nominations = {paper_id: [] for paper_id in paper_ids}
        if not paper_ids:
            return nominations

        query = """
        MATCH (paper:Paper)-[edge:SIMILAR_TO]-(neighbor:Paper)
        WHERE
            paper.id IN $paper_ids
            AND paper.id IN coalesce(edge.nominated_by, [])
        RETURN paper.id AS paper_id, neighbor.id AS neighbor_id, edge.score AS score
        ORDER BY paper_id ASC, score DESC, neighbor_id ASC
        """
        with self._driver.session() as session:
            result = session.run(query, paper_ids=paper_ids)
            for record in result:
                nominations[record["paper_id"]].append(
                    {
                        "paper_id": record["neighbor_id"],
                        "score": float(record["score"]),
                    }
                )
        return nominations

    def _sync_nominations(
        self,
        updates: list[dict[str, Any]],
        replace_all: bool = False,
    ) -> None:
        if not updates and not replace_all:
            return

        timestamp = self._now_iso()
        remove_query = """
        MATCH (paper:Paper {id: $paper_id})-[edge:SIMILAR_TO]-(neighbor:Paper)
        WHERE $paper_id IN coalesce(edge.nominated_by, [])
        SET
            edge.nominated_by = [
                nominator IN edge.nominated_by
                WHERE nominator <> $paper_id
            ],
            edge.updated_at = $timestamp
        WITH edge
        WHERE size(edge.nominated_by) = 0
        DELETE edge
        """
        upsert_query = """
        UNWIND $neighbors AS neighbor
        MATCH (source:Paper {id: neighbor.source_id})
        MATCH (target:Paper {id: neighbor.target_id})
        MERGE (source)-[edge:SIMILAR_TO]->(target)
        ON CREATE SET
            edge.created_at = $timestamp,
            edge.nominated_by = []
        SET
            edge.score = neighbor.score,
            edge.nominated_by = CASE
                WHEN $paper_id IN coalesce(edge.nominated_by, [])
                THEN edge.nominated_by
                ELSE coalesce(edge.nominated_by, []) + $paper_id
            END,
            edge.updated_at = $timestamp
        """

        def write_updates(transaction: Any) -> None:
            if replace_all:
                transaction.run(
                    "MATCH ()-[edge:SIMILAR_TO]->() DELETE edge"
                ).consume()
            for update in updates:
                paper_id = update["paper_id"]
                transaction.run(
                    remove_query,
                    paper_id=paper_id,
                    timestamp=timestamp,
                ).consume()
                neighbors = []
                for neighbor in update["neighbors"]:
                    source_id, target_id = self._canonical_pair(
                        paper_id,
                        neighbor["paper_id"],
                    )
                    neighbors.append(
                        {
                            "source_id": source_id,
                            "target_id": target_id,
                            "score": neighbor["score"],
                        }
                    )
                transaction.run(
                    upsert_query,
                    paper_id=paper_id,
                    neighbors=neighbors,
                    timestamp=timestamp,
                ).consume()

        with self._driver.session() as session:
            session.execute_write(write_updates)

    def _formatted_incident_edges(self, paper_id: str) -> list[dict[str, Any]]:
        return [
            {
                "paper_id": edge["paper"]["id"],
                "score": float(edge["edge"]["score"]),
                "created_at": edge["edge"].get("created_at"),
                "updated_at": edge["edge"].get("updated_at"),
            }
            for edge in self.list_similarity_edges(paper_id, limit=10000)
        ]

    def rebuild_similarity_edges(
        self,
        limit: int = 3,
        min_score: float = 0.65,
    ) -> dict[str, int | bool]:
        paper_ids_query = """
        MATCH (paper:Paper)
        WHERE paper.embedding IS NOT NULL
        RETURN paper.id AS paper_id
        ORDER BY paper_id ASC
        """
        with self._driver.session() as session:
            paper_ids = [
                record["paper_id"]
                for record in session.run(paper_ids_query)
            ]

        updates = []
        for paper_id in paper_ids:
            scores = self._exact_similarity_scores(paper_id, min_score)
            updates.append(
                {
                    "paper_id": paper_id,
                    "neighbors": select_top_neighbors(scores, limit, min_score),
                }
            )

        self._sync_nominations(updates, replace_all=True)

        nomination_query = """
        MATCH (paper:Paper)
        WHERE paper.embedding IS NOT NULL
        OPTIONAL MATCH (paper)-[edge:SIMILAR_TO]-()
        WHERE paper.id IN coalesce(edge.nominated_by, [])
        WITH paper, count(edge) AS nomination_count
        RETURN
            coalesce(sum(nomination_count), 0) AS nominations,
            coalesce(max(nomination_count), 0) AS max_nominations
        """
        edge_query = """
        MATCH ()-[edge:SIMILAR_TO]->()
        RETURN count(edge) AS edges
        """
        invalid_nominator_query = """
        MATCH (source:Paper)-[edge:SIMILAR_TO]->(target:Paper)
        UNWIND coalesce(edge.nominated_by, []) AS nominator
        WITH source, target, nominator
        WHERE nominator <> source.id AND nominator <> target.id
        RETURN count(nominator) AS invalid_nominators
        """
        with self._driver.session() as session:
            nomination_record = session.run(nomination_query).single()
            edge_record = session.run(edge_query).single()
            invalid_record = session.run(invalid_nominator_query).single()
        return {
            "papers": len(paper_ids),
            "edges": int(edge_record["edges"]) if edge_record is not None else 0,
            "nominations": (
                int(nomination_record["nominations"])
                if nomination_record is not None
                else 0
            ),
            "max_nominations": (
                int(nomination_record["max_nominations"])
                if nomination_record is not None
                else 0
            ),
            "nominators_valid": (
                int(invalid_record["invalid_nominators"]) == 0
                if invalid_record is not None
                else True
            ),
        }

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
        affected_query = """
        MATCH (paper:Paper {id: $paper_id})-[edge:SIMILAR_TO]-()
        UNWIND coalesce(edge.nominated_by, []) AS nominator
        WITH DISTINCT nominator
        WHERE nominator <> $paper_id
        RETURN nominator
        """
        query = """
        MATCH (paper:Paper {id: $paper_id})
        WITH paper, count(paper) AS matches
        DETACH DELETE paper
        RETURN matches > 0 AS deleted
        """
        with self._driver.session() as session:
            affected_paper_ids = [
                record["nominator"]
                for record in session.run(affected_query, paper_id=paper_id)
            ]
            record = session.run(query, paper_id=paper_id).single()
        if record is None:
            return False
        deleted = bool(record["deleted"])
        if deleted and affected_paper_ids:
            updates = [
                {
                    "paper_id": affected_id,
                    "neighbors": select_top_neighbors(
                        self._exact_similarity_scores(affected_id, 0.65),
                        limit=3,
                        min_score=0.65,
                    ),
                }
                for affected_id in affected_paper_ids
            ]
            self._sync_nominations(updates)
        return deleted
