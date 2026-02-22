from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mem0 import Memory

from tb12b.extraction import Fact


@contextmanager
def _without_openrouter_env() -> Any:
    original = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        yield
    finally:
        if original is not None:
            os.environ["OPENROUTER_API_KEY"] = original


class Mem0MemoryStore:
    def __init__(self, namespace: str = "tb12b", extractor_version: str = "tb12b-v1"):
        self.namespace = namespace
        self.extractor_version = extractor_version
        self.user_id = f"{namespace}-eval"
        self.memory = self._build_memory()

    def _build_memory(self) -> Memory:
        xai_key = os.getenv("XAI_API_KEY")
        faiss_path = Path(".mem0") / self.namespace / "faiss"
        faiss_path.mkdir(parents=True, exist_ok=True)

        config = {
            "vector_store": {
                "provider": "faiss",
                "config": {
                    "collection_name": f"{self.namespace}_facts",
                    "path": str(faiss_path.resolve()),
                    "embedding_model_dims": 384,
                },
            },
            "embedder": {
                "provider": "fastembed",
                "config": {
                    "model": "BAAI/bge-small-en-v1.5",
                    "embedding_dims": 384,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "grok-4-1212",
                    "api_key": xai_key,
                    "openai_base_url": "https://api.x.ai/v1",
                },
            },
            "version": "v1.1",
        }

        with _without_openrouter_env():
            return Memory.from_config(config)

    def reset(self) -> None:
        self.memory.delete_all(user_id=self.user_id)

    def insert_turn_with_facts(
        self,
        convo_id: str,
        role: str,
        content: str,
        facts: list[Fact],
    ) -> dict[str, Any]:
        inserted = 0
        for fact in facts:
            text = f"{fact.subject} {fact.predicate} {fact.object_text}".strip()
            metadata = {
                "convo_id": convo_id,
                "role": role,
                "source_text": content,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object_text": fact.object_text,
                "truth_value": fact.truth_value,
                "condition_text": fact.condition_text,
                "valid_from": None,
                "valid_to": None,
                "confidence": fact.confidence,
                "extractor_version": self.extractor_version,
            }
            with _without_openrouter_env():
                self.memory.add(
                    text,
                    user_id=self.user_id,
                    metadata=metadata,
                    infer=False,
                )
            inserted += 1

        return {"inserted": inserted}

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        with _without_openrouter_env():
            raw = self.memory.search(
                query,
                user_id=self.user_id,
                limit=30,
                rerank=False,
            )

        rows = raw.get("results", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return []

        parsed: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") or {}
            parsed.append(
                {
                    "id": item.get("id"),
                    "subject": meta.get("subject", "user"),
                    "predicate": meta.get("predicate", "states"),
                    "object_text": meta.get("object_text", item.get("memory", "")),
                    "truth_value": meta.get("truth_value", "unknown"),
                    "condition_text": meta.get("condition_text"),
                    "confidence": float(meta.get("confidence", 0.7)),
                    "score": float(item.get("score", 0.0)),
                    "source": "mem0",
                }
            )

        return parsed[:top_k]
