# Mycel Memory Alternatives Research (Feb 21, 2026)

## Executive summary
Mycel’s hardest problem is not just storage or vector search. It is **high-fidelity fact extraction with logic** (negation, conditionals, temporal validity) plus durable retrieval at personal scale. Most memory systems in this survey are strong at persistence + search, but weak at truth-maintenance semantics unless you add an explicit fact schema and extraction/validation pipeline.

The strongest options for your constraints (offline-capable, Temporal-friendly, personal-scale cost, durable) are: **(1) PostgreSQL + pgvector + FTS + structured fact tables**, **(2) Qdrant + relational metadata/fact ledger**, and **(3) Kuzu (graph + vector + FTS) for explicit relationship/temporal reasoning**. Hosted-first options like Pinecone are technically good but weaker fit for local/offline ownership and cost control at your scale.

Given Mem0 TB5 results (precision 58.8%, recall 47.6%, thread-safety issues), the architecture decision should prioritize: deterministic extraction pipeline + confidence/provenance + conflict handling, with vector DB as retrieval substrate. The retrieval store is necessary but not sufficient; your quality gains will come from schema + extraction rules + evaluation loop.

## Comparison table
| Option | Architecture | Auto fact extraction | Retrieval quality mode | Python + Temporal integration | Cost at personal scale | Durability | Key limitations | Fit (1-10) |
|---|---|---|---|---|---|---|---|---|
| PostgreSQL + pgvector | Relational + vector + native FTS | No (you build) | Hybrid (vector + tsvector/BM25-like ranking) | Excellent (`psycopg`, SQLAlchemy, strong transactions) | Very low self-host; managed optional | Strong WAL + PITR + ACID | You own schema/tuning | **9.2** |
| Qdrant | Vector DB with payload filters, sparse+dense | No (you build) | Dense+sparse+RRF, strong hybrid tooling | Excellent (`qdrant-client`, async/sync) | OSS free; cloud starts free tier | WAL + snapshots + restore | Needs sidecar for rich relational logic | **8.8** |
| Kuzu | Embedded graph DB + vector + FTS extensions | No (you build) | Graph traversal + vector + FTS | Good Python API, embeddable | OSS MIT, very low infra cost | ACID + disk persistence | Concurrency/process-mode constraints; younger ecosystem | **8.5** |
| Weaviate | Vector-native DB with BM25/hybrid and modules | No (mostly retrieval infra) | Built-in vector/BM25 hybrid | Good Python client (v4+) | OSS/self-host or cloud from ~$25/mo | Persistent volumes + backups | Operational complexity; memory/resource planning needed | 7.8 |
| Milvus (Lite/Standalone) | Vector DB; full-text BM25 support (not fully in Lite) | No | Vector + BM25/hybrid (deployment-dependent) | Mature `pymilvus` | OSS/self-host; managed via Zilliz | WAL-backed + object storage architecture | More ops overhead than personal-scale needs | 7.6 |
| Neo4j (with vector indexes) | Graph DB + vector indexes | No | Graph traversal + vector semantic index | Very mature Python driver | Community free/self-host; Aura paid | ACID; managed backups in Aura tiers | Cost for managed; graph modeling overhead | 7.4 |
| LangGraph/LangChain memory stack | Framework-level short/long-term memory APIs | Partial patterns only; not turnkey truth extraction | Depends on backing store | Excellent for workflow orchestration | Mostly OSS; store costs separate | Depends on checkpointer/store backend | Not a DB; requires backend and custom semantics | 7.2 |
| Haystack + DocumentStore backends | Pipeline framework over many stores | No (you compose) | Sparse/dense/hybrid via backend retrievers | Strong Python integration | OSS framework; backend cost varies | Depends on backend | More RAG pipeline than personal-memory truth model | 6.8 |
| ChromaDB | Embedded/hosted vector store | No | Semantic retrieval (+ ecosystem hybrid options) | Easy Python local use | OSS free; cloud optional | Persistent client on disk available | Production caveats + recent memory management issue report | 6.5 |
| Pinecone (hosted) | Managed vector DB (dense/sparse/hybrid) | No | Strong semantic + hybrid | Excellent Python SDK | Free starter, paid minimums for prod tiers | Managed service + backups | No local/offline mode; cost/control mismatch for Mycel | 6.2 |

## Detailed writeups

## 1) PostgreSQL + pgvector (+ FTS + structured facts)
### Name and overview
`pgvector` is an open-source extension for PostgreSQL maintained by the pgvector project (widely adopted ecosystem). It adds vector types, operators, and ANN indexes (HNSW, IVFFlat) while preserving PostgreSQL’s transactional strengths.

### Architecture
- Core: Postgres tables for canonical facts/events.
- Vector: `vector`/`halfvec` fields + HNSW/IVFFlat index.
- Keyword: PostgreSQL full-text search (`tsvector`, `tsquery`, ranking).
- Hybrid: reciprocal rank fusion or weighted blending in SQL.

### Fact extraction
No automatic extraction. Best practice for Mycel: extraction worker writes to normalized tables:
- `facts(subject, predicate, object, truth_value, confidence, valid_from, valid_to, source_turn_id, extractor_version)`
- `events(commitment/reminder/decision)`
- `contradictions`/`supersessions`

### Retrieval quality
- Exact and ANN search supported.
- Native hybrid pattern documented (vector + FTS).
- Strong filtering, joins, temporal predicates.
- No vendor-provided “assistant fact extraction accuracy benchmark”; quality is mostly your extraction/eval loop.

### Python integration
Excellent: `psycopg`, SQLAlchemy, async drivers, and `pgvector-python`. Easy to wrap in Temporal activities with transactional boundaries.

### Cost
Very cost-effective for 1 user/100 msgs/day. Single local Postgres instance is enough.

### Durability
Strong durability from PostgreSQL WAL/crash recovery and PITR options.

### Limitations
- Requires schema design and index tuning.
- If extraction is weak, DB quality won’t save output quality.

### Fit for Mycel
**9.2/10**. Best balance of correctness, durability, offline capability, and Temporal-friendly transactional workflows.

## 2) Qdrant
### Name and overview
Qdrant is an OSS vector database/semantic search engine with a mature Python client and cloud/OSS deployment options.

### Architecture
- Collections of points (vectors + payload).
- Dense/sparse vectors in one system, plus hybrid query patterns and reranking workflows.
- WAL-backed storage and snapshot/restore tooling.

### Fact extraction
No automatic extraction. You must implement extraction + write pipeline.

### Retrieval quality
- Strong semantic retrieval.
- Supports sparse+dense hybrid patterns and reranking tutorials.
- Good filtering by payload metadata.

### Python integration
Very good Python SDK (sync + async, typed models). Clean to integrate in Temporal activities.

### Cost
OSS self-host is free; managed cloud has free starter capacity and scales as needed.

### Durability
WAL + snapshots + restore mechanisms documented.

### Limitations
- Less natural for relational constraints/temporal logic than SQL-first designs.
- You likely need relational sidecar (SQLite/Postgres) for commitments/negation state semantics.

### Fit for Mycel
**8.8/10**. Excellent retrieval engine; pair with relational fact ledger for truth/temporal correctness.

## 3) Kuzu (graph + vector + FTS)
### Name and overview
Kuzu is an embedded graph database (MIT licensed) focused on analytical graph queries, with ACID transactions and Cypher. Recent releases added vector and FTS improvements.

### Architecture
- Embedded in-process graph DB file.
- Extensions for vector index (HNSW) and full-text search.
- Graph traversal useful for linked concepts and relationship-heavy memory.

### Fact extraction
No turnkey extraction. You design extraction into graph entities/edges (e.g., `:User-[:PREFERS {valid_from,...}]`), including negations and temporal validity.

### Retrieval quality
- Combines graph traversal with vector similarity and FTS.
- Useful for explicit reasoning chains and provenance-rich queries.

### Python integration
Official Python API is straightforward. Embedded mode works well in local workflows; Temporal activities can open connections and execute Cypher transactions.

### Cost
Very low infra cost (embedded OSS).

### Durability
ACID + disk persistence.

### Limitations
- Concurrency/process mode constraints documented (careful with read-write/read-only multi-process patterns).
- Smaller ecosystem than Postgres/Qdrant.

### Fit for Mycel
**8.5/10**. Great if you want explicit knowledge graph reasoning and are willing to own data modeling complexity.

## 4) Weaviate
### Name and overview
Weaviate is a mature vector database platform (OSS + cloud), with integrated hybrid search features.

### Architecture
- Vector-native storage with BM25 and hybrid fusion.
- REST/GraphQL/gRPC APIs.
- Modules for embedding/reranking integrations.

### Fact extraction
Not a turnkey personal-memory extractor. You still build extraction/classification pipeline.

### Retrieval quality
Strong built-in hybrid (`vector + BM25`) and configurable fusion/search strategies.

### Python integration
Mature Python client (v4); async client available.

### Cost
Self-host possible; cloud serverless starts around entry paid tier.

### Durability
Persistent volume config + native backup capabilities.

### Limitations
Known-issues page is active; requires version hygiene and ops tuning. Resource planning/memory management can matter.

### Fit for Mycel
**7.8/10**. Technically strong retrieval, but heavier operational surface than needed for personal-scale assistant.

## 5) Milvus (and Milvus Lite)
### Name and overview
Milvus is a widely used OSS vector DB; `pymilvus` includes Milvus Lite for local embedding-in-app scenarios.

### Architecture
- Vector collections, ANN indexes.
- Full-text/BM25 + hybrid search features (availability varies by deployment; Lite has limits).
- Cloud-native distributed architecture for larger scale.

### Fact extraction
No automatic extraction layer for personal facts.

### Retrieval quality
Strong vector retrieval; hybrid support is improving/available depending on topology and version.

### Python integration
Good with `pymilvus`, including local Lite mode.

### Cost
OSS self-host; managed via Zilliz options.

### Durability
WAL-oriented architecture and persistent storage patterns are documented in platform design notes.

### Limitations
For personal scale, can be overkill operationally compared with pgvector/Qdrant.

### Fit for Mycel
**7.6/10**. Powerful, but complexity/perf profile is better for larger workloads.

## 6) Neo4j (graph + vector indexes)
### Name and overview
Neo4j is a mature graph database with native vector indexes and strong enterprise tooling.

### Architecture
- Property graph model with Cypher query language.
- Vector indexes + graph traversal.
- Managed Aura and self-managed options.

### Fact extraction
No turnkey extraction pipeline. You define schema and ingestion logic.

### Retrieval quality
Good for relationship-aware retrieval; vector search available for semantic nearest-neighbor lookups.

### Python integration
Excellent official Python driver with connection pooling.

### Cost
Community Edition is free for self-host. Aura paid tiers can be expensive relative to personal-scale needs.

### Durability
ACID transactions; managed backups on paid Aura tiers.

### Limitations
Graph modeling overhead; may be too much unless you actively exploit graph reasoning.

### Fit for Mycel
**7.4/10**. Strong if you prioritize explicit graph reasoning, weaker on cost simplicity and local lightweight operation versus Postgres/Kuzu.

## 7) LangGraph/LangChain memory stack
### Name and overview
LangChain/LangGraph provide memory abstractions (short-term thread memory, long-term stores, checkpointers) rather than a full memory DB.

### Architecture
- Agent state + checkpointers (SQLite/Postgres/etc).
- Optional store interface for cross-thread memory.
- You bring your own retrieval backend and extraction logic.

### Fact extraction
Partial framework support only. No out-of-box high-accuracy negation/conditional fact extractor.

### Retrieval quality
Depends entirely on selected backing store and retrieval pipeline.

### Python integration
Excellent Python ergonomics and active ecosystem.

### Cost
OSS; backend infra determines cost.

### Durability
Depends on chosen checkpointer/store (e.g., SQLite/Postgres durable, in-memory not).

### Limitations
Framework complexity can grow quickly; abstractions may obscure state behavior unless carefully instrumented.

### Fit for Mycel
**7.2/10** as a framework layer. Valuable orchestration glue, but not enough by itself as the memory system of record.

## 8) Haystack
### Name and overview
Haystack is an OSS Python framework for building retrieval/agent pipelines with many DocumentStore integrations.

### Architecture
- Modular pipeline components.
- Multiple retrievers and hybrid retrievers via backend stores.
- Integrates with pgvector, Weaviate, Pinecone, Chroma, OpenSearch, etc.

### Fact extraction
No specialized personal-memory extractor by default.

### Retrieval quality
Good building blocks for hybrid retrieval and reranking, depending on selected backend.

### Python integration
Strong and Python-native.

### Cost
Framework is OSS; costs depend on chosen storage/providers.

### Durability
Delegated to backend store.

### Limitations
More focused on RAG pipelines than persistent personal-memory truth management.

### Fit for Mycel
**6.8/10**. Useful integration layer, but not primary memory architecture.

## 9) ChromaDB
### Name and overview
Chroma is an open-source retrieval database with local persistent client and cloud options.

### Architecture
- In-memory or persistent client on local disk.
- Collection-based vector storage with filtering.

### Fact extraction
No automatic extraction semantics.

### Retrieval quality
Good semantic retrieval for lightweight scenarios.

### Python integration
Very easy local Python setup.

### Cost
OSS free for local use; cloud exists.

### Durability
Persistent client stores to disk and loads on startup.

### Limitations
Docs position persistent local mode as local-dev/testing oriented for production; recent issue reports highlight operational caveats in some usage patterns.

### Fit for Mycel
**6.5/10**. Fast to prototype, but lower confidence for long-lived production memory core.

## 10) Pinecone (hosted)
### Name and overview
Pinecone is a fully managed vector database with strong hosted UX and SDKs.

### Architecture
- Serverless dense/sparse indexes.
- Hybrid search patterns and integrated model workflows.
- Managed backup/restore for serverless indexes.

### Fact extraction
No extraction pipeline included for your fact logic.

### Retrieval quality
Strong semantic and hybrid retrieval capabilities.

### Python integration
Mature Python SDK with async/grpc options.

### Cost
Free starter available; standard/enterprise impose monthly minimums and usage-based billing.

### Durability
Managed persistence with backup/restore features.

### Limitations
No local/offline deployment path; plan limits/minimums and cloud dependency conflict with your ownership/offline requirement.

### Fit for Mycel
**6.2/10**. Good service quality, poor alignment with local-first personal assistant requirements.

## Final recommendation
### Recommended architecture for Mycel (Phase 1)
**Pick: PostgreSQL + pgvector + FTS, with a strict fact/event schema and extraction validator loop.**

Why this wins:
1. Best durability and correctness envelope for commitments/temporal facts.
2. Hybrid retrieval and relational constraints in one system (no heavy multi-store complexity at MVP).
3. Excellent Python + Temporal fit with transaction boundaries and idempotent activities.
4. Cheapest sustainable operation at personal scale.
5. Easiest path to later graph augmentation (Kuzu/Neo4j sidecar) without replatforming everything.

### Runner-up patterns
- Qdrant + Postgres fact ledger if you prioritize vector feature velocity.
- Kuzu-first if graph reasoning is core from day 1.

## Implementation sketch (top choice)
### Phase 1 goals
- Durable storage of extracted facts/events.
- High-precision extraction for critical classes: preferences, commitments, decisions, constraints.
- Hybrid retrieval for question answering.
- Temporal correctness and negation support.

### Data model (minimal)
```sql
-- canonical source of truth for raw conversation turns
CREATE TABLE convo_turns (
  id BIGSERIAL PRIMARY KEY,
  convo_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- normalized memory facts
CREATE TABLE memory_facts (
  id BIGSERIAL PRIMARY KEY,
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_text TEXT NOT NULL,
  truth_value TEXT NOT NULL CHECK (truth_value IN ('true','false','conditional','unknown')),
  condition_text TEXT,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  confidence REAL NOT NULL,
  source_turn_id BIGINT NOT NULL REFERENCES convo_turns(id),
  extractor_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  embedding VECTOR(1536)
);

CREATE INDEX ON memory_facts USING hnsw (embedding vector_cosine_ops);

-- keyword/hybrid search support
ALTER TABLE memory_facts ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(subject,'') || ' ' || coalesce(predicate,'') || ' ' || coalesce(object_text,''))
  ) STORED;
CREATE INDEX memory_facts_fts_idx ON memory_facts USING GIN (fts);
```

### Retrieval query pattern
```sql
-- pseudo: vector top-k + keyword top-k then fuse in app layer
-- vector
SELECT id, 1 - (embedding <=> :query_vec) AS sem_score
FROM memory_facts
WHERE (valid_to IS NULL OR valid_to > now())
ORDER BY embedding <=> :query_vec
LIMIT 30;

-- keyword
SELECT id, ts_rank_cd(fts, plainto_tsquery('english', :q)) AS kw_score
FROM memory_facts
WHERE fts @@ plainto_tsquery('english', :q)
  AND (valid_to IS NULL OR valid_to > now())
ORDER BY kw_score DESC
LIMIT 30;
```

### Temporal workflow decomposition (Python)
1. `IngestTurnWorkflow`: store raw turn.
2. `ExtractFactsActivity` (cheap model): produce candidate facts + negation/conditional flags.
3. `ValidateFactsActivity` (rules + optional stronger model): reject low-confidence or contradictory outputs.
4. `UpsertFactsActivity` (transaction): write facts with provenance, set superseded facts `valid_to`.
5. `RetrieveContextActivity`: hybrid search + temporal filtering + top-N selection.

### Guardrails to address TB5 failure modes
- Mandatory `truth_value` (`true/false/conditional`) and explicit `condition_text`.
- Temporal normalization (`valid_from`, `valid_to`, “next Friday” resolution timestamped with locale).
- Multi-fact utterance splitting with atomic inserts per fact.
- Contradiction detector for same `(subject, predicate)` with incompatible objects.
- Evaluation harness using your TB5 dataset on every extractor/prompt change.

## Sources
- Qdrant docs: https://qdrant.tech/documentation/overview/
- Qdrant storage/WAL: https://qdrant.tech/documentation/concepts/storage/
- Qdrant snapshots: https://qdrant.tech/documentation/concepts/snapshots/
- Qdrant Python client: https://python-client.qdrant.tech/index.html
- Qdrant pricing: https://qdrant.tech/pricing/
- Qdrant hybrid guides: https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/
- pgvector README: https://github.com/pgvector/pgvector
- pgvector Python: https://github.com/pgvector/pgvector-python
- PostgreSQL WAL reliability: https://www.postgresql.org/docs/current/wal-reliability.html
- PostgreSQL FTS intro: https://www.postgresql.org/docs/10/textsearch-intro.html
- PostgreSQL PITR: https://www.postgresql.org/docs/14/continuous-archiving.html
- Weaviate hybrid search: https://docs.weaviate.io/weaviate/search/hybrid
- Weaviate Python client: https://docs.weaviate.io/weaviate/client-libraries/python
- Weaviate persistence: https://docs.weaviate.io/deploy/configuration/persistence
- Weaviate known issues: https://docs.weaviate.io/weaviate/release-notes/known-issues
- Weaviate pricing: https://weaviate.io/pricing/
- Milvus quickstart: https://milvus.io/docs/quickstart.md/
- Milvus PyMilvus install: https://milvus.io/docs/install-pymilvus.md/
- Milvus full text search: https://milvus.io/docs/embed-with-bm25.md
- Neo4j vector indexes: https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/
- Neo4j Python driver: https://neo4j.com/docs/api/python-driver/current/api.html
- Neo4j pricing: https://neo4j.com/pricing/
- Kuzu docs overview: https://kuzudb.com/docs
- Kuzu vector extension: https://docs.kuzudb.com/extensions/vector/
- Kuzu FTS extension: https://docs.kuzudb.com/extensions/full-text-search/
- Kuzu concurrency notes: https://kuzudb.com/docs/concurrency
- LangChain short-term memory: https://docs.langchain.com/oss/python/langchain/short-term-memory
- LangGraph persistence/checkpointers: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph add memory: https://docs.langchain.com/oss/python/langgraph/add-memory
- LlamaIndex memory: https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/memory/
- LlamaIndex chat stores: https://docs.llamaindex.ai/en/stable/module_guides/storing/chat_stores/
- Haystack install/docs: https://docs.haystack.deepset.ai/docs/installation
- Haystack retrievers: https://docs.haystack.deepset.ai/docs/retrievers
- Haystack pgvector store: https://docs.haystack.deepset.ai/docs/pgvectordocumentstore
- Chroma clients/persistence: https://docs.trychroma.com/docs/run-chroma/clients
- Chroma Python reference: https://docs.trychroma.com/reference/python
- Chroma issue example (memory management caveat): https://github.com/chroma-core/chroma/issues/5843
- Pinecone hybrid search: https://docs.pinecone.io/guides/search/hybrid-search
- Pinecone Python SDK: https://docs.pinecone.io/reference/sdks/python/overview
- Pinecone limits: https://docs.pinecone.io/docs/limits
- Pinecone pricing: https://www.pinecone.io/pricing/
- Pinecone backups: https://docs.pinecone.io/guides/indexes/understanding-backups
- SQLite FTS5: https://www.sqlite.org/fts5.html
- sqlite-vec: https://alexgarcia.xyz/sqlite-vec/
