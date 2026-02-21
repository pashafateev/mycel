from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

import psycopg
from openai import OpenAI
from pgvector.psycopg import register_vector

from tb12.extraction import Fact, infer_valid_from

DEFAULT_DSN = os.getenv("TB12_DATABASE_URL", "postgresql://admin@localhost:5432/tb12_memory")


class MemoryStore:
    def __init__(self, dsn: str = DEFAULT_DSN, extractor_version: str = "tb12-v1"):
        self.dsn = dsn
        self.extractor_version = extractor_version
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.embed_client = OpenAI(api_key=self.openai_key) if self.openai_key else None

    def connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self.dsn)
        register_vector(conn)
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
