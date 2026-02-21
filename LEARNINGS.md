# TB12 Learnings: PostgreSQL + pgvector Memory Architecture

## Run notes
- PostgreSQL 16 and `pgvector` 0.8.0 were installed locally.
- Database: `tb12_memory`
- Schema: explicit fact table with `truth_value`, `condition_text`, temporal fields, provenance, vector, and FTS.

## Evaluation summary
- Run command: `PYTHONPATH=src python3 scripts/test_tb12_memory.py`
- Aggregate results (TB12):
  - Precision: **1.000**
  - Recall: **0.952**
  - Retrieval top-3: **1.000**
- TB5 baseline:
  - Precision: 0.588
  - Recall: 0.476
  - Retrieval top-3: 0.417
- Result: all TB12 success criteria were met in this run.
- `OPENAI_API_KEY` was not set, so embeddings were skipped and retrieval ran in FTS + lexical hybrid mode.

## Schema effectiveness
- Explicit `truth_value` and `condition_text` make negation/conditional handling queryable and auditable.
- `valid_from` supports temporal normalization (for example, “last year” mapping).
- Provenance (`source_turn_id`, `extractor_version`) improves traceability.

## Extraction quality
- Extraction uses OpenRouter (`google/gemini-2.5-flash`) with a deterministic rule fallback.
- Rule fallback specifically covers negation, conditionals, and multi-fact splits to avoid silent drop-offs.
- Strengths observed:
  - Negation and conditional extraction is now explicit via `truth_value` and `condition_text`.
  - Multi-fact utterances were split consistently.
  - Temporal phrase “last year” maps to `valid_from`.
- Remaining weakness:
  - Some fact normalization remains heuristic (for example, compressing phrasing variants into canonical labels).

## Retrieval quality
- Retrieval combines vector similarity and Postgres FTS via reciprocal rank fusion.
- If `OPENAI_API_KEY` is unavailable, vector embeddings are skipped and FTS-only retrieval remains active.
- This run used FTS + lexical overlap ranking (no embeddings) and still hit top-3 target.
- The largest gain came from explicit truth/predicate fields plus query-intent lexical fallback.

## Comparison to TB5
- TB5 issues (negation, conditionals, temporal details, multi-fact extraction) are directly encoded in schema + extraction logic.
- Improvements vs TB5:
  - Precision: +0.412
  - Recall: +0.476
  - Retrieval top-3: +0.583
- Biggest practical improvement was retrieval reliability for questions that depend on negation and conditional context.

## Recommendation
- PostgreSQL + pgvector is a viable MVP direction because it combines durable ACID storage, explicit logic-aware schema, and hybrid retrieval in a single stack.
- Recommendation: **use PostgreSQL for MVP**.
- Next improvements:
  - Add stricter scoring and a broader gold dataset to reduce metric inflation from fuzzy matching.
  - Enable embeddings once `OPENAI_API_KEY` is available, then compare FTS-only vs vector+FTS on the same test set.
