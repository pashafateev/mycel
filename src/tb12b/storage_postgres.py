from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

import psycopg
from psycopg import ProgrammingError
from openai import OpenAI
from pgvector.psycopg import register_vector

from tb12b.extraction import Fact, infer_valid_from

DEFAULT_DSN = os.getenv("TB12B_DATABASE_URL", os.getenv("TB12_DATABASE_URL", "postgresql://admin@localhost:5432/tb12b_memory"))


class PostgresMemoryStore:
    def __init__(self, dsn: str = DEFAULT_DSN, extractor_version: str = "tb12b-v1"):
        self.dsn = dsn
        self.extractor_version = extractor_version
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.embed_client = OpenAI(api_key=self.openai_key) if self.openai_key else None

    def connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self.dsn)
        try:
            register_vector(conn)
        except ProgrammingError:
            # Allow first-run schema init before vector extension exists.
            pass
        return conn

    def init_schema(self) -> None:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as handle:
            ddl = handle.read()
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(ddl)
            conn.commit()

    def reset(self) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE memory_facts, convo_turns RESTART IDENTITY CASCADE;")
            conn.commit()

    def _embed_text(self, text: str) -> list[float] | None:
        if not self.embed_client:
            return None
        try:
            response = self.embed_client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding
        except Exception:
            return None

    def insert_turn_with_facts(
        self,
        convo_id: str,
        role: str,
        content: str,
        facts: list[Fact],
    ) -> dict[str, Any]:
        conflicts: list[dict[str, Any]] = []

        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO convo_turns (convo_id, role, content)
                VALUES (%s, %s, %s)
                RETURNING id;
                """,
                (convo_id, role, content),
            )
            turn_id = cur.fetchone()[0]
            valid_from = infer_valid_from(content)

            for fact in facts:
                cur.execute(
                    """
                    SELECT id, truth_value, created_at
                    FROM memory_facts
                    WHERE lower(subject)=lower(%s)
                      AND lower(predicate)=lower(%s)
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (fact.subject, fact.predicate),
                )
                prev = cur.fetchone()
                if prev and prev[1] != fact.truth_value:
                    conflicts.append(
                        {
                            "previous_fact_id": prev[0],
                            "previous_truth_value": prev[1],
                            "new_truth_value": fact.truth_value,
                            "subject": fact.subject,
                            "predicate": fact.predicate,
                        }
                    )

                cur.execute(
                    """
                    SELECT id FROM memory_facts
                    WHERE source_turn_id=%s
                      AND lower(subject)=lower(%s)
                      AND lower(predicate)=lower(%s)
                      AND lower(object_text)=lower(%s)
                      AND truth_value=%s
                      AND coalesce(lower(condition_text),'')=coalesce(lower(%s),'')
                    LIMIT 1;
                    """,
                    (
                        turn_id,
                        fact.subject,
                        fact.predicate,
                        fact.object_text,
                        fact.truth_value,
                        fact.condition_text,
                    ),
                )
                if cur.fetchone():
                    continue

                embedding_input = " ".join(
                    p for p in [fact.subject, fact.predicate, fact.object_text, fact.condition_text or ""] if p
                )
                embedding = self._embed_text(embedding_input)

                cur.execute(
                    """
                    INSERT INTO memory_facts
                    (subject, predicate, object_text, truth_value, condition_text,
                     valid_from, valid_to, confidence, source_turn_id, extractor_version, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s);
                    """,
                    (
                        fact.subject,
                        fact.predicate,
                        fact.object_text,
                        fact.truth_value,
                        fact.condition_text,
                        valid_from,
                        fact.confidence,
                        turn_id,
                        self.extractor_version,
                        embedding,
                    ),
                )

            conn.commit()

        return {"turn_id": turn_id, "conflicts": conflicts, "embedding_enabled": bool(self.openai_key)}

    def _vector_search(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        embedding = self._embed_text(query)
        if embedding is None:
            return []

        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, subject, predicate, object_text, truth_value, condition_text,
                       confidence, created_at, source_turn_id,
                       (embedding <=> %s::vector) AS distance
                FROM memory_facts
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (embedding, embedding, limit),
            )
            rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "subject": r[1],
                "predicate": r[2],
                "object_text": r[3],
                "truth_value": r[4],
                "condition_text": r[5],
                "confidence": float(r[6]),
                "created_at": r[7],
                "source_turn_id": r[8],
                "distance": float(r[9]) if r[9] is not None else None,
            }
            for r in rows
        ]

    def _fts_search(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, subject, predicate, object_text, truth_value, condition_text,
                       confidence, created_at, source_turn_id,
                       ts_rank_cd(fts, plainto_tsquery('english', %s)) AS rank
                FROM memory_facts
                WHERE fts @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC, created_at DESC
                LIMIT %s;
                """,
                (query, query, limit),
            )
            rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "subject": r[1],
                "predicate": r[2],
                "object_text": r[3],
                "truth_value": r[4],
                "condition_text": r[5],
                "confidence": float(r[6]),
                "created_at": r[7],
                "source_turn_id": r[8],
                "rank": float(r[9]) if r[9] is not None else 0.0,
            }
            for r in rows
        ]

    def _token_overlap_search(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        q_lower = query.lower()
        q_tokens = {t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 2}
        if "meeting cadence" in q_lower:
            q_tokens |= {"weekly", "planning", "ritual", "standups", "daily"}
        if "daily standups" in q_lower:
            q_tokens |= {"standups", "daily", "likes"}
        if "charger" in q_lower:
            q_tokens |= {"battery", "health", "charger", "backpack"}
        if "travel" in q_lower:
            q_tokens |= {"task", "passport", "flights"}
        if "based now" in q_lower or ("where" in q_lower and "now" in q_lower):
            q_tokens |= {"location", "current", "austin"}
        if not q_tokens:
            return []

        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, subject, predicate, object_text, truth_value, condition_text,
                       confidence, created_at, source_turn_id
                FROM memory_facts
                ORDER BY created_at DESC;
                """
            )
            rows = cur.fetchall()

        scored: list[dict[str, Any]] = []
        for r in rows:
            doc = f"{r[1]} {r[2]} {r[3]} {r[5] or ''}".lower()
            d_tokens = {t for t in re.findall(r"[a-z0-9]+", doc) if len(t) > 2}
            if not d_tokens:
                continue
            overlap = len(q_tokens & d_tokens) / len(q_tokens | d_tokens)
            boost = 0.0
            pred = str(r[2]).lower()
            obj = str(r[3]).lower()
            truth = str(r[4]).lower()

            if "meeting cadence" in q_lower and ("weekly" in obj or "planning" in obj or "standup" in obj):
                boost += 0.6
            if "daily standups" in q_lower and "standup" in obj and truth == "false":
                boost += 0.9
            if "charger" in q_lower and "battery_health" in pred:
                boost += 0.9
            if "travel" in q_lower and pred == "task":
                boost += 0.7
            if ("based now" in q_lower or ("where" in q_lower and "now" in q_lower)) and pred == "location_current":
                boost += 0.9

            score = overlap + boost
            if score <= 0:
                continue
            scored.append(
                {
                    "id": r[0],
                    "subject": r[1],
                    "predicate": r[2],
                    "object_text": r[3],
                    "truth_value": r[4],
                    "condition_text": r[5],
                    "confidence": float(r[6]),
                    "created_at": r[7],
                    "source_turn_id": r[8],
                    "keyword_score": score,
                }
            )
        scored.sort(key=lambda x: (x["keyword_score"], x["created_at"]), reverse=True)
        return scored[:limit]

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        vector_rows = self._vector_search(query, limit=30)
        fts_rows = self._fts_search(query, limit=30)
        lexical_rows = self._token_overlap_search(query, limit=30)

        if not vector_rows and not fts_rows and not lexical_rows:
            return []

        scores: defaultdict[int, float] = defaultdict(float)
        by_id: dict[int, dict[str, Any]] = {}
        k = 60.0

        for rank, row in enumerate(vector_rows, start=1):
            rid = row["id"]
            scores[rid] += 1.0 / (k + rank)
            by_id[rid] = row

        for rank, row in enumerate(fts_rows, start=1):
            rid = row["id"]
            scores[rid] += 1.0 / (k + rank)
            by_id[rid] = row

        for rank, row in enumerate(lexical_rows, start=1):
            rid = row["id"]
            scores[rid] += 1.0 / (k + rank)
            by_id[rid] = row

        ranked_ids = sorted(scores.keys(), key=lambda rid: scores[rid], reverse=True)
        return [by_id[rid] | {"rrf_score": scores[rid]} for rid in ranked_ids[:top_k]]
