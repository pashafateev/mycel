# TB5 Learnings: Mem0 OSS Fact Extraction Quality

## Mem0 setup experience
- `pip install mem0ai` was straightforward.
- Local embeddings required an extra install: `pip install fastembed`.
- Local vector storage was easy (`qdrant` with local path).
- Pure no-key extraction was not possible in this environment (no local Ollama).
- `OPENROUTER_API_KEY` was not available in shell, so evaluation used an available key via OpenAI-compatible endpoint (`XAI_API_KEY` + `OPENAI_BASE_URL=https://api.x.ai/v1`).
- Mem0 OSS bug found: provider `xai` in `mem0ai==1.0.4` crashes (`xai_base_url` attr missing).

## Extraction quality observations
- Dataset: `data/tb05_conversations.json` (10 snippets, 21 expected facts, includes negation/implied/multi-fact cases).
- Run command: `python3 scripts/test_tb05_extraction.py`.
- Aggregate extraction metrics:
  - Precision: **0.588** (10/17)
  - Recall: **0.476** (10/21)
- Pattern observed:
  - Mem0 usually extracted compact facts.
  - It frequently missed nuance (negation, conditionals, temporal detail, implied state).
  - Multi-fact utterances were partially extracted.

## Retrieval quality observations
- Retrieval top-3 hit rate: **0.417** (5/12 queries).
- Misses were concentrated around:
  - commitment/reminder wording
  - implied facts
  - facts requiring normalization from paraphrase

## Storage/persistence behavior
- Local Qdrant persistence worked in `.tb05_mem0/qdrant`.
- Extracted memories were retrievable via `get_all`/`search` after `add`.
- Critical reliability issue: Mem0 `add()` logged SQLite thread errors for every snippet and returned empty `results` even when memories were stored:
  - `SQLite objects created in a thread can only be used in that same thread`
- This makes operation-level success signaling unreliable without extra verification.

## What would need to change for production
- Fix or patch Mem0 threading/history bug so `add()` result integrity is trustworthy.
- Add extraction guardrails before write:
  - confidence threshold
  - provenance fields (source turn/message)
  - explicit negation/conditional handling
- Add post-extraction validation/rules for high-value memory classes (commitments, reminders, identity/preferences).
- Add retrieval evaluation with semantic scorer + broader gold set before rollout.

## Recommendation
- For MVP: **stick with file-based memory** and add lightweight custom extraction for critical fact types.
- Revisit Mem0 after:
  - threading bug is resolved,
  - extraction precision/recall reaches TB5 thresholds,
  - retrieval top-3 reliability improves materially.
