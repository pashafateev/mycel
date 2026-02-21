#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any

from tb12.extraction import Fact, extract_facts
from tb12.retrieval import HybridRetriever
from tb12.storage import MemoryStore

DATA_PATH = Path("data/tb05_conversations.json")
BASELINE = {"precision": 0.588, "recall": 0.476, "retrieval_top3": 0.417}
MATCH_THRESHOLD = 0.12


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


def evaluate() -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing dataset at {DATA_PATH}")

    dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    store = MemoryStore()
    store.init_schema()
    store.reset()
    retriever = HybridRetriever(store)

    extracted_total = 0
    extracted_correct = 0
    expected_total = 0
    expected_recalled = 0
    query_total = 0
    query_hits = 0
    per_snippet: list[dict[str, Any]] = []

    for row in dataset:
        snippet_id = row["id"]
        snippet_text = row["snippet"]
        expected = row["expected_facts"]
        queries = row.get("queries", [])

        facts = extract_facts(snippet_text)
        store.insert_turn_with_facts(snippet_id, "user", snippet_text, facts)

        extracted_total += len(facts)
        expected_total += len(expected)

        matched_expected: set[str] = set()
        correct_here = 0
        for fact in facts:
            fact_text = _fact_to_text(fact)
            score, ref = _best_match(fact_text, expected)
            if score >= MATCH_THRESHOLD and ref is not None:
                correct_here += 1
                matched_expected.add(ref)

        extracted_correct += correct_here
        expected_recalled += len(matched_expected)

        query_hits_here = 0
        for q in queries:
            query_total += 1
            expected_fact = q["expected_fact"]
            retrieved = retriever.search(q["question"], top_k=3)
            if any(_best_match(_fact_to_text(item), [expected_fact])[0] >= MATCH_THRESHOLD for item in retrieved):
                query_hits += 1
                query_hits_here += 1

        per_snippet.append(
            {
                "id": snippet_id,
                "expected_count": len(expected),
                "extracted_count": len(facts),
                "correct_extracted": correct_here,
                "recalled_expected": len(matched_expected),
                "query_hits": query_hits_here,
                "query_total": len(queries),
            }
        )

    precision = (extracted_correct / extracted_total) if extracted_total else 0.0
    recall = (expected_recalled / expected_total) if expected_total else 0.0
    retrieval_top3 = (query_hits / query_total) if query_total else 0.0

    return {
        "per_snippet": per_snippet,
        "aggregate": {
            "precision": precision,
            "recall": recall,
            "retrieval_top3": retrieval_top3,
            "extracted_correct": extracted_correct,
            "extracted_total": extracted_total,
            "expected_recalled": expected_recalled,
            "expected_total": expected_total,
            "query_hits": query_hits,
            "query_total": query_total,
            "baseline": BASELINE,
            "embeddings_enabled": bool(os.getenv("OPENAI_API_KEY")),
        },
    }


def main() -> None:
    results = evaluate()
    print("TB12 Evaluation Results")
    print("=" * 80)
    for row in results["per_snippet"]:
        print(
            f"{row['id']}: extracted {row['correct_extracted']}/{row['extracted_count']} correct, "
            f"recall {row['recalled_expected']}/{row['expected_count']}, "
            f"retrieval {row['query_hits']}/{row['query_total']}"
        )

    agg = results["aggregate"]
    print("-" * 80)
    print(f"Precision: {agg['precision']:.3f} (TB5 baseline: {agg['baseline']['precision']:.3f})")
    print(f"Recall: {agg['recall']:.3f} (TB5 baseline: {agg['baseline']['recall']:.3f})")
    print(f"Retrieval top-3: {agg['retrieval_top3']:.3f} (TB5 baseline: {agg['baseline']['retrieval_top3']:.3f})")
    print(f"Embeddings enabled: {agg['embeddings_enabled']}")


if __name__ == "__main__":
    main()
