import os
from datetime import datetime

from tb12.extraction import extract_facts
from tb12.retrieval import HybridRetriever
from tb12.storage import MemoryStore

os.environ["TB12_FORCE_RULE_EXTRACTOR"] = "1"


def _store() -> MemoryStore:
    store = MemoryStore(extractor_version="tb12-tests")
    store.init_schema()
    return store


def test_negation() -> None:
    store = _store()
    store.reset()
    facts = extract_facts("I don't like X")
    assert any(f.truth_value == "false" for f in facts)


def test_conditional() -> None:
    store = _store()
    store.reset()
    facts = extract_facts("If X then Y")
    assert any(f.truth_value == "conditional" and f.condition_text for f in facts)


def test_temporal() -> None:
    store = _store()
    store.reset()
    facts = extract_facts("I moved to Austin last year")
    store.insert_turn_with_facts("t-temporal", "user", "I moved to Austin last year", facts)

    with store.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT valid_from FROM memory_facts ORDER BY id DESC LIMIT 1;")
        valid_from = cur.fetchone()[0]
    assert isinstance(valid_from, datetime)


def test_multi_fact() -> None:
    store = _store()
    store.reset()
    facts = extract_facts("I like Python but not TypeScript")
    likes_python = any(f.object_text.lower().startswith("python") and f.truth_value == "true" for f in facts)
    not_ts = any("typescript" in f.object_text.lower() and f.truth_value == "false" for f in facts)
    assert likes_python
    assert not_ts
    assert len(facts) >= 2


def test_contradiction_latest() -> None:
    store = _store()
    store.reset()
    first = extract_facts("I like coffee")
    second = extract_facts("I don't like coffee")

    store.insert_turn_with_facts("t-contradiction", "user", "I like coffee", first)
    result = store.insert_turn_with_facts("t-contradiction", "user", "I don't like coffee", second)
    assert result["conflicts"]

    with store.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT truth_value
            FROM memory_facts
            WHERE lower(subject)='user' AND lower(predicate)='likes' AND lower(object_text) LIKE 'coffee%'
            ORDER BY created_at DESC, id DESC
            LIMIT 1;
            """
        )
        latest_truth = cur.fetchone()[0]
    assert latest_truth == "false"
