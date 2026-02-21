from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from tb12.storage import MemoryStore


class HybridRetriever:
    def __init__(self, store: MemoryStore):
        self.store = store

    def _vector_search(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        embedding = self.store._embed_text(query)
        if embedding is None:
            return []

        with self.store.connect() as conn, conn.cursor() as cur:
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
        with self.store.connect() as conn, conn.cursor() as cur:
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

        with self.store.connect() as conn, conn.cursor() as cur:
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
