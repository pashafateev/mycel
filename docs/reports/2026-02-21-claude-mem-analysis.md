# claude-mem Memory Architecture Analysis

Repo analyzed: https://github.com/thedotmack/claude-mem (local clone)

## Architecture Diagram (text)

```text
Claude/Cursor/OpenClaw lifecycle events
  -> CLI adapters normalize hook payloads
  -> Hook handlers (session-init, observation, summarize, session-complete)
  -> Worker HTTP API (:37777)
  -> SessionManager + PendingMessageStore queue (SQLite)
  -> Memory agent (Claude SDK / Gemini / OpenRouter) consumes queued events
  -> XML output parser (observations + summary)
  -> Atomic write to SQLite (observations/session_summaries/user_prompts)
  -> Async sync to Chroma (vector docs)
  -> Retrieval path:
       search/timeline/get_observations/save_memory MCP tools
       -> worker search orchestrator
       -> Chroma semantic + SQLite metadata hydrate/fallback
  -> Next session context injection from SQLite observations/summaries
```

## Key Files and What They Do

- `src/services/sqlite/SessionStore.ts`: Primary schema + migrations + writes for `sdk_sessions`, `observations`, `session_summaries`, `user_prompts`, `pending_messages`.
- `src/services/sqlite/SessionSearch.ts`: SQLite filter queries; keeps FTS tables but current code comments mark text search as deprecated in favor of Chroma for query text.
- `src/services/worker/http/routes/SessionRoutes.ts`: API endpoints for init/observation/summarize/complete; privacy/tag stripping + skip-tools logic.
- `src/services/worker/SessionManager.ts`: Event-driven queueing, persistent pending message flow.
- `src/services/queue/SessionQueueProcessor.ts`: Claim-confirm queue iterator + stale processing self-heal.
- `src/services/worker/SDKAgent.ts`: Main auto-memory loop using Anthropic Agent SDK (or provider variants) to convert tool events into structured memory XML.
- `src/sdk/prompts.ts` + `plugin/modes/code.json`: Memory extraction/summarization prompts and taxonomy (types/concepts).
- `src/sdk/parser.ts`: XML parser for `<observation>` and `<summary>` blocks.
- `src/services/worker/agents/ResponseProcessor.ts`: Atomic store of parsed outputs; async Chroma sync + SSE broadcast.
- `src/services/sync/ChromaSync.ts`: Semantic indexing/querying via Chroma MCP bridge; granular field-level vector docs.
- `src/services/worker/search/SearchOrchestrator.ts` + strategies: retrieval strategy selection and fallback logic.
- `src/services/context/ContextBuilder.ts` + `src/services/context/ObservationCompiler.ts`: Context injection from recent observations/summaries.
- `src/services/worker/http/routes/MemoryRoutes.ts`: `save_memory` manual memory insert endpoint.
- `src/servers/mcp-server.ts`: MCP tools (`search`, `timeline`, `get_observations`, `save_memory`) mapped to worker HTTP API.

## 1) Data Model

### System of record
- **SQLite** at `~/.claude-mem/claude-mem.db` in WAL mode.

### Core tables
- `sdk_sessions`: maps `content_session_id` to `memory_session_id`, tracks session metadata.
- `observations`: structured units (`type`, `title`, `subtitle`, `facts[]`, `narrative`, `concepts[]`, `files_read[]`, `files_modified[]`, `prompt_number`, timestamps).
- `session_summaries`: summary checkpoint fields (`request`, `investigated`, `learned`, `completed`, `next_steps`, `notes`, files).
- `user_prompts`: cleaned prompt text per prompt number.
- `pending_messages`: durable queue for observation/summarize tasks.

### Search/index sidecar
- **Chroma vector DB** for semantic retrieval (collection names `cm__*`), with metadata including `sqlite_id`, `doc_type`, `project`.
- FTS5 virtual tables still maintained, but latest code path treats query-text search as Chroma-first and SQLite as metadata/filter path.

## 2) How Summarization Works and Is Stored

1. `Stop` hook calls `/api/sessions/summarize` with `last_assistant_message`.
2. Worker enqueues summarize task in `pending_messages`.
3. Memory agent receives generated prompt from `buildSummaryPrompt(...)` (XML schema required).
4. Parser extracts `<summary>`.
5. `ResponseProcessor` performs **atomic transaction** via `storeObservations(...)` to write observations + optional summary once.
6. Summary row saved in `session_summaries`; optionally indexed to Chroma (`doc_type=session_summary`).

Important design choice: parser stores summaries even with partial/missing fields (nullable normalized to empty strings before storage), favoring write-through over strict validation.

## 3) Retrieval: Keyword, Vector, or Hybrid?

- **Primary for query text:** Vector semantic (Chroma).
- **SQLite path:** metadata filters (project/type/concept/files/date), hydration by IDs, timeline queries.
- **Hybrid:** metadata prefilter in SQLite + semantic ranking in Chroma + intersection + hydrate.

So today it is effectively **vector-first with SQL-filter/hydration**, not classic keyword-first.

## 4) Automatic Fact Extraction / Auto-memory

### Yes, it does auto-memory
- Every eligible `PostToolUse` event is queued.
- Agent converts tool input/output into structured `<observation>` XML.
- Parser stores extracted fields automatically.
- `Stop` creates summary checkpoints automatically.

### Manual memory also exists
- `save_memory` endpoint/tool inserts a synthetic `discovery` observation.

### If asking “does it extract stable user facts/profile memory?”
- **Not really.** It extracts *work observations* from tool activity rather than explicit durable user/profile facts with confidence/conflict handling.

### What would be needed for stronger auto-memory
- Dedicated fact schema (`entity`, `attribute`, `value`, `source`, `confidence`, `valid_from/to`, `status`).
- Idempotent upsert/dedup at fact level (hash + semantic near-duplicate checks).
- Contradiction resolution and fact aging.
- Separate pipelines for procedural/project memory vs personal/user facts.
- Quality gates (classifier/rules) before persisting long-lived facts.

## 5) Claude-specific vs General

### Claude-specific
- Hook lifecycle integration and formats geared to Claude Code (`session_id`, transcript path, hook events).
- Primary auto-memory engine defaults to Anthropic Agent SDK (`SDKAgent`).
- Plugin packaging/modes around Claude ecosystem.

### General/reusable
- Storage model (SQLite schema + pending queue + observation/summary abstractions).
- Provider abstraction exists (`GeminiAgent`, `OpenRouterAgent`) with shared `ResponseProcessor`.
- Retrieval/search architecture and MCP wrapper are generally reusable.
- Privacy tag stripping, skip-tools filtering, queue orchestration, context rendering are model-agnostic.

## 6) Strengths vs Weaknesses

## Strengths (why summaries often feel good)
- Strong prompt structure + constrained XML output taxonomy.
- Continuous event-driven capture from tool stream, not just end-of-session recap.
- Durable queue + atomic storage path improves data survival.
- Progressive disclosure retrieval flow (`search -> timeline -> get_observations`) is token-efficient.
- Granular vector docs (facts/narrative/summary fields split) can improve semantic recall.

## Weaknesses (why auto-memory can feel not amazing)
- Over-capture/duplication risk in high-throughput sessions (multiple open issues e.g. #1158, #1061, #1137).
- Heavy operational complexity around worker/process/chroma lifecycle (many reliability issues).
- Vector dependency fragility (Windows/chroma/python/packaging issues; e.g. #1199, #1196, #1185, #1146).
- Limited dedup/importance scoring in core auto pipeline; “save everything” bias can reduce precision.
- Recency filtering (90-day window) can hide older but relevant knowledge.
- Not designed as canonical fact graph; mostly event summaries/observations.

## 7) Replicating Good Parts in Mycel (Python + Temporal + Postgres)

## Feasibility
- **Good parts are very replicable.** Most value is in pipeline design, prompt schema, and retrieval flow, not Claude-specific APIs.

## Suggested Mycel architecture (Postgres as SoR)

- Use Postgres tables:
  - `sessions`, `events`, `observations`, `session_summaries`, `user_prompts`, `pending_tasks`, `facts` (new).
- Use `pgvector` for semantic search (replace Chroma sidecar).
- Keep JSONB arrays (`facts`, `concepts`, `files_*`) with GIN indexes.
- Temporal workflows:
  - `IngestEventWorkflow` (tool events/user prompts)
  - `ObservationExtractionWorkflow` (LLM XML/JSON extraction)
  - `SummaryWorkflow` (checkpoint summary)
  - `IndexingWorkflow` (embeddings + vector upsert)
  - `RecoveryWorkflow` (stuck task healing, dedup sweeps)
- Retrieval API in 3 layers (same winning pattern): index -> timeline -> hydrate.

## Effort estimate (rough)
- 1-2 weeks: core ingestion + observation/summary extraction + Postgres schema + API.
- +1 week: high-quality retrieval (hybrid filters + vector ranking + timeline).
- +1-2 weeks: hardening (dedup, retries, temporal recovery policies, quality metrics).

## What to copy directly
- XML/structured extraction contract with strict parser.
- Durable queue semantics (claim-confirm equivalent in Temporal activity state).
- Progressive disclosure retrieval UX.
- Privacy/tag filtering at ingestion edge.

## What to improve in Mycel
- Postgres-first single-store (avoid dual-store drift/ops burden).
- First-class dedup/idempotency keys at ingest and observation levels.
- Fact table with confidence/conflict resolution for true long-term memory.
- Better scoring (importance/novelty/redundancy) before persistence.
- Explicit SLO monitoring: duplicate rate, stuck-task rate, retrieval precision.

## Issue Scan Notes (known limitations)

Recent issues indicate memory quality is often constrained more by runtime reliability than schema design:
- Duplicate/overcapture: #1158, #1061, #1137
- Observation pipeline failures: #1091, #1058
- Chroma/search reliability and platform issues: #1199, #1196, #1185, #1146, #1123, #1110
- Resource/process leakage affecting stability: #1089, #1077, #1068

This explains why architecture is conceptually strong, but “auto-memory quality” can degrade in practice.
