#!/usr/bin/env python3
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

from mem0 import Memory

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tb05.mem0_setup import build_mem0_config  # noqa: E402

DATA_PATH = REPO_ROOT / "data" / "tb05_conversations.json"
SIMILARITY_THRESHOLD = 0.45

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "do",
    "for",
    "from",
    "i",
    "if",
    "in",
    "is",
    "it",
    "my",
    "now",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
}


def normalize_tokens(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


def jaccard_similarity(a: str, b: str) -> float:
    ta = set(normalize_tokens(a))
    tb = set(normalize_tokens(b))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_facts(stored_facts: List[str], expected_facts: List[str]) -> Tuple[int, int, List[Tuple[str, float, str]]]:
    matched_expected = set()
    correct_stored = 0
    debug_rows: List[Tuple[str, float, str]] = []

    for fact in stored_facts:
        best_score = -1.0
        best_expected = ""
        best_idx = -1
        for idx, expected in enumerate(expected_facts):
            score = jaccard_similarity(fact, expected)
            if score > best_score:
                best_score = score
                best_expected = expected
                best_idx = idx

        if best_score >= SIMILARITY_THRESHOLD:
            correct_stored += 1
            matched_expected.add(best_idx)
        debug_rows.append((fact, best_score, best_expected))

    return correct_stored, len(matched_expected), debug_rows


def load_dataset(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    dataset = load_dataset(DATA_PATH)
    mem0_config, llm_backend = build_mem0_config(str(REPO_ROOT))

    print("TB5 Mem0 Extraction Eval")
    print(f"dataset: {DATA_PATH}")
    print(f"snippets: {len(dataset)}")
    print(f"llm backend: {llm_backend}")
    print(f"similarity threshold: {SIMILARITY_THRESHOLD}")
    print()

    memory = Memory.from_config(mem0_config)
    user_id = "tb05-eval-user"

    total_expected = 0
    total_stored = 0
    total_correct_stored = 0
    total_matched_expected = 0
    query_total = 0
    query_hits = 0
    thread_issue_count = 0

    for item in dataset:
        snippet_id = item["id"]
        run_id = f"{snippet_id}-{uuid.uuid4().hex[:8]}"
        snippet = item["snippet"]
        expected_facts = item["expected_facts"]
        queries = item["queries"]

        add_result = memory.add(snippet, user_id=user_id, run_id=run_id)
        stored_records = memory.get_all(user_id=user_id, run_id=run_id, limit=50).get("results", [])
        stored_facts = [r.get("memory", "") for r in stored_records if r.get("memory")]

        # mem0 1.0.4 thread issue: add results can be empty despite successful storage.
        if not add_result.get("results") and stored_facts:
            thread_issue_count += 1

        correct_stored, matched_expected, debug_rows = match_facts(stored_facts, expected_facts)

        snippet_query_hits = 0
        for q in queries:
            query_total += 1
            results = memory.search(q["question"], user_id=user_id, run_id=run_id, limit=3).get("results", [])
            result_facts = [r.get("memory", "") for r in results if r.get("memory")]
            hit = any(
                jaccard_similarity(candidate, q["expected_fact"]) >= SIMILARITY_THRESHOLD
                for candidate in result_facts
            )
            if hit:
                query_hits += 1
                snippet_query_hits += 1

        snippet_precision = (correct_stored / len(stored_facts)) if stored_facts else 0.0
        snippet_recall = matched_expected / len(expected_facts)
        snippet_retrieval = (snippet_query_hits / len(queries)) if queries else 0.0

        total_expected += len(expected_facts)
        total_stored += len(stored_facts)
        total_correct_stored += correct_stored
        total_matched_expected += matched_expected

        print(f"[{snippet_id}] {snippet}")
        print(f"  stored facts ({len(stored_facts)}):")
        for fact, score, expected in debug_rows:
            print(f"    - {fact}")
            print(f"      best_match={score:.2f} -> {expected}")
        print(
            f"  metrics: precision={snippet_precision:.2f} recall={snippet_recall:.2f} "
            f"retrieval_top3={snippet_retrieval:.2f}"
        )
        print()

    agg_precision = (total_correct_stored / total_stored) if total_stored else 0.0
    agg_recall = (total_matched_expected / total_expected) if total_expected else 0.0
    agg_retrieval = (query_hits / query_total) if query_total else 0.0

    print("Aggregate")
    print(f"  precision: {agg_precision:.3f} ({total_correct_stored}/{total_stored})")
    print(f"  recall: {agg_recall:.3f} ({total_matched_expected}/{total_expected})")
    print(f"  retrieval_top3_hit_rate: {agg_retrieval:.3f} ({query_hits}/{query_total})")
    print(f"  add_result_thread_issue_count: {thread_issue_count}/{len(dataset)}")
    print()

    print("Success Criteria")
    precision_ok = agg_precision >= 0.8
    recall_ok = agg_recall >= 0.7
    retrieval_ok = agg_retrieval >= 0.8

    print(f"  precision >= 0.8: {'PASS' if precision_ok else 'FAIL'}")
    print(f"  recall >= 0.7: {'PASS' if recall_ok else 'FAIL'}")
    print(f"  retrieval top-3 >= 0.8: {'PASS' if retrieval_ok else 'FAIL'}")


if __name__ == "__main__":
    main()
