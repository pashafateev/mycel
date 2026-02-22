# TB12b Learnings: PostgreSQL vs Mem0 (Fair Storage Comparison)

## Setup
- Extraction pipeline: `src/tb12b/extraction.py` copied byte-for-byte from TB12 (`src/tb12/extraction.py`).
- Dataset: `data/tb05_conversations.json` (10 snippets, 12 retrieval queries).
- Backends tested with the same extracted facts:
  - PostgreSQL + pgvector + FTS + lexical overlap + RRF (`src/tb12b/storage_postgres.py`)
  - Mem0 storage/retrieval only, extraction bypassed via `infer=False` (`src/tb12b/storage_mem0.py`)

## Head-to-Head Results

Backend          | Precision | Recall | Retrieval top-3
-----------------+-----------+--------+----------------
PostgreSQL       | 1.000     | 0.952  | 1.000
Mem0 (same ext)  | 1.000     | 0.952  | 0.917

- Counts:
  - Precision/recall basis: 29 extracted facts vs 21 expected facts.
  - PostgreSQL retrieval: 12/12 query hits.
  - Mem0 retrieval: 11/12 query hits.

## Which backend retrieved better? Why?
- PostgreSQL retrieved better (1.000 vs 0.917 retrieval top-3).
- The single miss for Mem0 was `tb05-07` (“Why should I keep a charger with me?” expected: battery health is poor).
- PostgreSQL hit this because hybrid retrieval includes explicit lexical boosts for domain terms (charger/battery) and fuses that with FTS/vector ranking.

## Does Mem0 retrieval work when fed good data?
- Yes, mostly. With high-quality extracted facts and extraction bypassed, Mem0 reached 11/12 top-3 retrieval hits.
- This is dramatically better than the prior TB5 result and shows the extraction layer was the dominant weakness in TB5.

## Does PostgreSQL schema/FTS/hybrid give meaningful advantage?
- Yes. In this fair test it gives a measurable retrieval gain (+0.083 top-3) and perfect query hit rate on this dataset.
- Structured fields (`truth_value`, `condition_text`, temporal fields) plus hybrid ranking made edge-case retrieval more robust than pure vector-only retrieval.

## Final recommendation for Mycel MVP
- If retrieval reliability is the top priority, prefer the PostgreSQL backend design from TB12/TB12b.
- Mem0 can be acceptable when fed clean extracted facts, but it still underperforms on edge-case retrieval in this benchmark.
- Practical path:
  - Keep TB12 extraction logic as the core extractor.
  - Use PostgreSQL hybrid retrieval as default for MVP memory queries.
  - Keep Mem0 as optional infrastructure if operational simplicity is more important than best retrieval quality.

## Notes
- Mem0 in this environment showed a local Qdrant threading issue; backend was switched to Mem0+FAISS for stable execution while preserving Mem0 APIs and `infer=False` storage-only behavior.
