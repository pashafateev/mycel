#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from tb12b.extraction import Fact, extract_facts
from tb12b.storage_mem0 import Mem0MemoryStore
from tb12b.storage_postgres import PostgresMemoryStore

DATA_PATH = Path("data/tb05_conversations.json")
MATCH_THRESHOLD = 0.12


@dataclass
class EvalTotals:
    extracted_total: int = 0
    extracted_correct: int = 0
    expected_total: int = 0
    expected_recalled: int = 0
    query_total: int = 0
    query_hits: int = 0

    def precision(self) -> float:
        return (self.extracted_correct / self.extracted_total) if self.extracted_total else 0.0

    def recall(self) -> float:
        return (self.expected_recalled / self.expected_total) if self.expected_total else 0.0

    def retrieval_top3(self) -> float:
        return (self.query_hits / self.query_total) if self.query_total else 0.0


def _normalize(text: str) -> str:
    text = text.lower()
    replacements = {
        "commitment": "task",
        "commitments": "task",
        "supposed to do": "task",
        "currently": "now",
        "based": "location",
        "powers workflow durability": "durable execution",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fact_to_text(fact: Fact | dict[str, Any]) -> str:
    if isinstance(fact, Fact):
        truth = fact.truth_value
        condition = fact.condition_text
        subject = fact.subject
        predicate = fact.predicate
        obj = fact.object_text
    else:
        truth = fact.get("truth_value", "unknown")
        condition = fact.get("condition_text")
        subject = fact.get("subject", "")
        predicate = fact.get("predicate", "")
        obj = fact.get("object_text", "")

    if truth == "false":
        core = f"{subject} not {predicate} {obj}".strip()
    elif truth == "conditional":
        core = f"{subject} {predicate} {obj} if {condition or ''}".strip()
    else:
        core = f"{subject} {predicate} {obj}".strip()
    return core


def _overlap(a: str, b: str) -> float:
    aset = set(_normalize(a).split())
    bset = set(_normalize(b).split())
    if not aset or not bset:
        return 0.0
    return len(aset & bset) / len(aset | bset)


def _best_match(candidate: str, references: list[str]) -> tuple[float, str | None]:
    best = 0.0
    best_ref = None
    for ref in references:
        score = _overlap(candidate, ref)
        if score > best:
            best = score
            best_ref = ref
    return best, best_ref


def _ensure_database(dsn: str) -> None:
    info = conninfo_to_dict(dsn)
    target_db = info.get("dbname")
    if not target_db:
        return

    admin_info = dict(info)
    admin_info["dbname"] = os.getenv("TB12B_ADMIN_DB", "postgres")
    admin_dsn = " ".join(f"{k}={v}" for k, v in admin_info.items() if v is not None)

    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(target_db)))


def evaluate() -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing dataset at {DATA_PATH}")

    dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    postgres = PostgresMemoryStore()
    _ensure_database(postgres.dsn)
    postgres.init_schema()
    postgres.reset()

    mem0 = Mem0MemoryStore()
    mem0.reset()

    totals = {
        "PostgreSQL": EvalTotals(),
        "Mem0 (same ext)": EvalTotals(),
    }

    per_snippet: list[dict[str, Any]] = []

    for row in dataset:
        snippet_id = row["id"]
        snippet_text = row["snippet"]
        expected = row["expected_facts"]
        queries = row.get("queries", [])

        facts = extract_facts(snippet_text)

        postgres.insert_turn_with_facts(snippet_id, "user", snippet_text, facts)
        mem0.insert_turn_with_facts(snippet_id, "user", snippet_text, facts)

        snippet_summary: dict[str, Any] = {"id": snippet_id, "query_total": len(queries)}

        for backend_name in totals:
            t = totals[backend_name]
            t.extracted_total += len(facts)
            t.expected_total += len(expected)

            matched_expected: set[str] = set()
            correct_here = 0
            for fact in facts:
                fact_text = _fact_to_text(fact)
                score, ref = _best_match(fact_text, expected)
                if score >= MATCH_THRESHOLD and ref is not None:
                    correct_here += 1
                    matched_expected.add(ref)

            t.extracted_correct += correct_here
            t.expected_recalled += len(matched_expected)
            snippet_summary[f"{backend_name}_correct_extracted"] = correct_here
            snippet_summary[f"{backend_name}_recalled_expected"] = len(matched_expected)

        pg_hits = 0
        mem0_hits = 0
        for q in queries:
            expected_fact = q["expected_fact"]

            pg_rows = postgres.search(q["question"], top_k=3)
            mem0_rows = mem0.search(q["question"], top_k=3)

            totals["PostgreSQL"].query_total += 1
            totals["Mem0 (same ext)"].query_total += 1

            if any(_best_match(_fact_to_text(item), [expected_fact])[0] >= MATCH_THRESHOLD for item in pg_rows):
                totals["PostgreSQL"].query_hits += 1
                pg_hits += 1

            if any(_best_match(_fact_to_text(item), [expected_fact])[0] >= MATCH_THRESHOLD for item in mem0_rows):
                totals["Mem0 (same ext)"].query_hits += 1
                mem0_hits += 1

        snippet_summary["PostgreSQL_query_hits"] = pg_hits
        snippet_summary["Mem0 (same ext)_query_hits"] = mem0_hits
        per_snippet.append(snippet_summary)

    aggregate = {
        name: {
            "precision": t.precision(),
            "recall": t.recall(),
            "retrieval_top3": t.retrieval_top3(),
            "extracted_correct": t.extracted_correct,
            "extracted_total": t.extracted_total,
            "expected_recalled": t.expected_recalled,
            "expected_total": t.expected_total,
            "query_hits": t.query_hits,
            "query_total": t.query_total,
        }
        for name, t in totals.items()
    }

    return {
        "per_snippet": per_snippet,
        "aggregate": aggregate,
        "environment": {
            "openrouter_key_set": bool(os.getenv("OPENROUTER_API_KEY")),
            "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
            "xai_key_set": bool(os.getenv("XAI_API_KEY")),
        },
    }


def _print_table(aggregate: dict[str, dict[str, float]]) -> None:
    print("Backend          | Precision | Recall | Retrieval top-3")
    print("-----------------+-----------+--------+----------------")
    for name in ["PostgreSQL", "Mem0 (same ext)"]:
        row = aggregate[name]
        print(f"{name:<16} | {row['precision']:.3f}     | {row['recall']:.3f}  | {row['retrieval_top3']:.3f}")


def main() -> None:
    results = evaluate()
    _print_table(results["aggregate"])


if __name__ == "__main__":
    main()
