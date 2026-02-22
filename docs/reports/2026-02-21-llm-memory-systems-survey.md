# LLM Memory Systems Survey (beyond Mem0 + raw Postgres/Qdrant)

Date: February 22, 2026
Scope: Systems/patterns for (a) summarizing conversation history into usable long-term memory and (b) automatic memory extraction robust to negation, conditionals, and temporal validity.
Target context: Mycel (single user, Temporal workflows, cost-sensitive).

## Shortlist (8 options)

## 1) Zep Cloud (managed) / Graphiti-backed memory service
- What it is + maturity:
  - Managed agent memory/context assembly product from Zep.
  - Mature and actively used in production; Zep and Graphiti benchmarked in the Zep paper (2025) and Graphiti has large OSS adoption.
- How it stores:
  - Temporal knowledge graph (entities/edges/episodes), plus hybrid retrieval (semantic + full-text + graph/time-aware search).
  - Managed API, no direct infra ops required.
- Summarization approach:
  - Builds user/context blocks from graph state; supports user-summary customization and context assembly APIs.
  - Summarization is graph-derived rather than only rolling transcript compression.
- Auto memory extraction approach:
  - Extracts facts/relationships from incoming episodes/messages and updates graph incrementally.
  - Can ingest unstructured chat and structured business JSON.
- Negation / conditional / temporal support:
  - Strong temporal validity support (fact lifecycle + invalidation, historical state tracking).
  - Negation and state flips are represented as relationship changes over time.
  - Conditionals are partially supported (if-then intent is often stored as qualified fact; complex logic still app-defined).
- Python friendliness:
  - Strong (Python SDK + ecosystem integrations).
- Fit for Mycel:
  - Good if you want fastest time-to-value.
  - Tradeoff: recurring vendor cost for one-user scenario may be high versus self-hosted pattern.
  - Fit score: 4/5.

## 2) Graphiti OSS (self-hosted temporal KG framework)
- What it is + maturity:
  - Open-source temporal knowledge graph framework from Zep team.
  - Very active OSS project as of 2026, Apache-2.0.
- How it stores:
  - Graph database-backed temporal graph model (entities, edges, episodes; bi-temporal semantics in ecosystem implementations).
- Summarization approach:
  - Summaries are generated from graph neighborhoods/episodes (you control prompts and assembly).
- Auto memory extraction approach:
  - Incremental entity/relation extraction with schema reuse and graph updates on each new episode.
- Negation / conditional / temporal support:
  - Temporal: first-class.
  - Negation/changes: handled via edge updates/invalidation and historical edges.
  - Conditional: needs schema/prompt design (not a built-in logic engine).
- Python friendliness:
  - Strong (Python-first OSS with docs/examples).
- Fit for Mycel:
  - Excellent for cost-sensitive single-user if you can run graph infra and extraction jobs.
  - Pairs well with Temporal workflows for asynchronous extraction/compaction.
  - Fit score: 5/5.

## 3) Letta (MemGPT-style architecture)
- What it is + maturity:
  - Production framework from MemGPT creators; MemGPT-style memory hierarchy (core + recall + archival).
  - Good maturity for agent products.
- How it stores:
  - Core memory blocks (in-context), recall memory (conversation logs/search), archival memory (often vector DB), optional local memory filesystem.
- Summarization approach:
  - Mix of always-visible core blocks and archival retrieval; memory edits can be agent-driven and asynchronous (sleeptime).
- Auto memory extraction approach:
  - Tool-mediated memory updates (`memory_*`, archival tools, conversation search tools); can auto-update from interaction.
- Negation / conditional / temporal support:
  - Better than plain vector memory because editable memory blocks + recall by date.
  - Temporal support is moderate (date search, hierarchy) but not as explicit as temporal KG fact validity.
  - Conditional semantics depend on prompt/tools; no guaranteed formal conditional model.
- Python friendliness:
  - Strong.
- Fit for Mycel:
  - Very good for assistant-style memory with less custom architecture work.
  - For strict temporal truth maintenance, may still need a fact layer on top.
  - Fit score: 4/5.

## 4) LangGraph + LangChain long-term memory (store + checkpointer + profile/collection patterns)
- What it is + maturity:
  - General agent orchestration framework with thread persistence, cross-thread stores, TTLs, and memory design patterns.
  - Very mature ecosystem.
- How it stores:
  - Checkpointer (thread state) + memory store (JSON documents in namespaces), with optional semantic indexing.
  - Can be backed by DB implementations in production.
- Summarization approach:
  - User-defined: profile memory (continuously updated schema) or collection memory (append/retrieve); can run on hot path or background jobs.
- Auto memory extraction approach:
  - Usually implemented via extraction nodes/tools; Trustcall-style JSON patching improves structured updates.
- Negation / conditional / temporal support:
  - Temporal supported via TTL/persistence strategy and explicit fields; not automatic truth maintenance.
  - Negation/conditional quality depends on extraction schema/prompts + patch validation.
- Python friendliness:
  - Excellent.
- Fit for Mycel:
  - Excellent for Temporal-workflow alignment (clear node-based extraction/summarization jobs).
  - Most cost-controllable if you keep schemas narrow and background updates batched.
  - Fit score: 5/5.

## 5) LlamaIndex Memory (new `Memory` class + chat stores + memory blocks)
- What it is + maturity:
  - LlamaIndex-native memory abstractions; older buffers deprecated in favor of unified `Memory`.
  - Mature in retrieval ecosystem; memory API evolving but practical.
- How it stores:
  - Short-term FIFO chat queue + optional long-term memory blocks; pluggable chat stores (in-memory/file/DB-backed via integrations).
- Summarization approach:
  - Token-based flushing from short-term to long-term; optional summarization/compression strategies.
- Auto memory extraction approach:
  - Long-term blocks can process flushed messages for extraction; vector memory and retrieval can be combined.
- Negation / conditional / temporal support:
  - Baseline support unless you design typed memory schemas + time metadata.
  - No strong built-in temporal truth model; requires custom extraction and conflict handling.
- Python friendliness:
  - Excellent.
- Fit for Mycel:
  - Good if you already use LlamaIndex stack.
  - For robust temporal/negation correctness, needs extra policy layer.
  - Fit score: 3.5/5.

## 6) Haystack conversational memory pattern (ChatMessageStore + retrievers + custom extraction pipeline)
- What it is + maturity:
  - Haystack offers composable components; conversational memory primitives exist but parts are in experimental package.
  - Good core maturity, memory-specific pieces less opinionated.
- How it stores:
  - ChatMessageStore + retrievers; plus document stores (including pgvector integrations).
- Summarization approach:
  - Mostly custom pipeline stage (LLM summarizer component) rather than opinionated built-in long-term memory lifecycle.
- Auto memory extraction approach:
  - Tool/agent loops can call extraction components and write structured docs/messages.
- Negation / conditional / temporal support:
  - Depends on your extraction schema; no first-class temporal fact validity model.
- Python friendliness:
  - Strong.
- Fit for Mycel:
  - Decent if already on Haystack; otherwise more plumbing for memory correctness.
  - Fit score: 3/5.

## 7) Event-sourced Fact Store pattern (custom, Temporal-native)
- What it is + maturity:
  - Architecture pattern (not a single library): append immutable memory events, materialize latest facts/profiles asynchronously.
  - Very mature pattern in distributed systems, highly compatible with Temporal.
- How it stores:
  - Append-only event log (SQL/table/topic), projections for current profile and retrieval index (vector/FTS optional), plus validity windows (`valid_from`, `valid_to`, `supersedes`).
- Summarization approach:
  - Periodic workflow compaction into profile summaries and episodic digests.
  - Multi-resolution summaries (daily/weekly/entity-specific) are straightforward.
- Auto memory extraction approach:
  - Extraction worker emits typed events: `fact_asserted`, `fact_negated`, `preference_changed`, `intent_with_condition`, `expired`.
  - Deterministic projection logic resolves contradictions.
- Negation / conditional / temporal support:
  - Strongest if designed well: explicit event types and validity intervals make negation/conditionals/temporal first-class.
- Python friendliness:
  - Excellent (your code, your schema).
- Fit for Mycel:
  - Best long-term fit for correctness + cost control (1 user).
  - Initial engineering cost higher than turnkey frameworks.
  - Fit score: 5/5.

## 8) Recency-aware RAG memory pattern (time-weighted retrieval + temporal metadata filters)
- What it is + maturity:
  - Pattern combining vector retrieval with recency scoring and time filters; available in LangChain via time-weighted retriever concepts and widely reproducible.
  - Mature as a pattern, moderate as “productized memory system”.
- How it stores:
  - Usually vector store + metadata (`timestamp`, `expires_at`, `source`, `confidence`, `negated_by`).
- Summarization approach:
  - Rolling summary + selective recall (query-dependent) with recency-biased ranking.
- Auto memory extraction approach:
  - LLM extraction into small memory documents keyed by entity/topic; background dedupe/merge.
- Negation / conditional / temporal support:
  - Temporal recency is good.
  - True negation/conditional handling is only moderate unless you add explicit conflict-resolution rules and validity fields.
- Python friendliness:
  - Excellent.
- Fit for Mycel:
  - Low-cost and simple to start, but easy to get subtle contradictions over long horizons.
  - Fit score: 3.5/5.

## Recommended direction for Mycel

1. Primary recommendation: Option 7 (Event-sourced Fact Store) + Option 8 retrieval layer.
- Why: best control over negation/conditional/temporal correctness, cheap at 1-user scale, native fit with Temporal workflows.

2. Fastest robust alternative: Option 2 (Graphiti OSS).
- Why: gives temporal memory semantics out of the box with less custom logic than pure event-sourcing.

3. If you want minimal infra effort: Option 1 (Zep managed).
- Why: strong quality and temporal handling, but likely overkill on recurring cost for a single user.

## Practical extraction schema (works across options)
Use typed memory records/events instead of plain “fact text”:
- `entity_id`
- `attribute`
- `value`
- `polarity` (`asserted` | `negated`)
- `condition` (nullable expression, e.g. `if_traveling=true`)
- `valid_from`
- `valid_to` (nullable)
- `confidence`
- `source_turn_id`
- `supersedes_record_id` (nullable)

This schema is the key lever for correctly handling negation, conditionality, and temporal validity in any framework.

## Sources
- Zep paper (arXiv): https://arxiv.org/abs/2501.13956
- Zep Graphiti OSS repo: https://github.com/getzep/graphiti
- Zep docs (memory/graph retrieval): https://help.getzep.com/docs
- Zep Mem0 migration capability table: https://help.getzep.com/mem0-to-zep
- Letta memory management: https://docs.letta.com/concepts/memory-management
- Letta MemGPT architecture: https://docs.letta.com/guides/agents/architectures/memgpt
- MemGPT paper (arXiv): https://arxiv.org/abs/2310.08560
- LlamaIndex memory guide: https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/memory/
- LlamaIndex chat stores: https://docs.llamaindex.ai/en/stable/module_guides/storing/chat_stores/
- LangGraph memory (Python): https://docs.langchain.com/oss/python/langgraph/add-memory
- LangGraph memory overview (profile/collection patterns): https://docs.langchain.com/oss/javascript/langgraph/memory
- LangGraph TTL configuration: https://docs.langchain.com/langgraph-platform/configure-ttl
- Trustcall (structured extraction/patching): https://github.com/hinthornw/trustcall
- Haystack ChatMessageStore API: https://docs.haystack.deepset.ai/reference/experimental-chatmessage-store-api
- Haystack ChatMessageRetriever API: https://docs.haystack.deepset.ai/reference/experimental-retrievers-api
- LangChain time-weighted retriever source docs: https://api.python.langchain.com/en/latest/_modules/langchain/retrievers/time_weighted_retriever.html
- Temporal durable execution overview: https://temporal.io/

