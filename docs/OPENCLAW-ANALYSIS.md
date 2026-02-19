# OpenClaw Deep Research Analysis for Mycel

## 1. What OpenClaw Does Well (Learn From)

OpenClaw has several hard-earned design decisions we should copy or adapt.

- Session serialization and queue discipline are solid. OpenClaw enforces one active run per session key and uses lane-based queues, which prevents transcript corruption and tool race conditions (`openclaw-docs/concepts/queue.md`, `openclaw-docs/concepts/agent-loop.md`).
- It treats session state as first-class infrastructure, not an afterthought. The split between `sessions.json` metadata and JSONL transcripts is pragmatic and debuggable (`openclaw-docs/concepts/session.md`, `openclaw-docs/reference/session-management-compaction.md`).
- Compaction + pruning separation is correct. Persistent compaction summaries and transient tool-result pruning are distinct mechanisms with distinct goals (`openclaw-docs/concepts/compaction.md`, `openclaw-docs/concepts/session-pruning.md`).
- They built explicit hygiene layers for real provider quirks. The transcript hygiene matrix is exactly the kind of “battle scars codified” layer many systems skip (`openclaw-docs/reference/transcript-hygiene.md`).
- Safety boundaries are modeled as separate layers (tool policy vs sandbox vs elevated exec), which is architecturally clean even if operationally heavy (`openclaw-docs/gateway/sandboxing.md`, `openclaw-docs/gateway/sandbox-vs-tool-policy-vs-elevated.md`).
- Heartbeat/cron/hook semantics are documented clearly and have delivery contracts, which reduces hidden behavior (`openclaw-docs/gateway/heartbeat.md`, `openclaw-docs/automation/cron-jobs.md`, `openclaw-docs/automation/webhook.md`).
- Multi-agent isolation rules (workspace/session/auth) are explicit, including caveats where isolation is incomplete (`openclaw-docs/concepts/multi-agent.md`, `openclaw-docs/tools/subagents.md`).

## 2. What OpenClaw Gets Wrong (Fix)

OpenClaw solves many hard problems, but it also shows where complexity has gotten ahead of product value.

- Prompt and context overhead is too high by default. It injects many bootstrap files plus tools/skills metadata every run, and even its own docs warn this drives token burn and compaction pressure (`openclaw-docs/concepts/system-prompt.md`, `openclaw-docs/concepts/context.md`, `openclaw-docs/reference/token-use.md`).
- “Safety in prompt” is not safety in runtime. The docs explicitly state safety guardrails are advisory and hard enforcement must come from runtime controls; this is correct but easy to misconfigure (`openclaw-docs/concepts/system-prompt.md`).
- Historical transcript-fixup complexity indicates fragility. They had to remove duplicate hygiene layers after regressions (notably `call_id|fc_id` pairing), showing how easy it is to break model-provider compatibility (`openclaw-docs/reference/transcript-hygiene.md`).
- Session defaults are continuity-first, not safety-first. `dmScope: main` as default can leak context in multi-user DM setups unless explicitly changed (`openclaw-docs/concepts/session.md`).
- Exec behavior can be surprising/safe-ish but risky in practice. Sandboxing is off by default, and host execution semantics are nuanced enough that users will misread them (`openclaw-docs/tools/exec.md`, `openclaw-docs/gateway/sandboxing.md`).
- Feature overlap creates cognitive load: heartbeat, cron, hooks, webhooks, subagents, queues, sessions, send policy, per-channel routing each solve adjacent scheduling/orchestration problems with different knobs (`openclaw-docs/gateway/heartbeat.md`, `openclaw-docs/automation/cron-vs-heartbeat.md`, `openclaw-docs/automation/hooks.md`, `openclaw-docs/concepts/queue.md`).
- Configuration surface is enormous and hard to reason about globally (`openclaw-docs/gateway/configuration-reference.md`).

## 3. What We Dont Need (Cut)

For a single-user Telegram-first Mycel, OpenClaw has major bloat we should deliberately remove.

Quantified docs footprint (current OpenClaw docs corpus):

- `channels/`: 29 files, 8,454 lines
- `gateway/`: 30 files, 7,924 lines
- `tools/`: 24 files, 5,133 lines
- `concepts/`: 28 files, 4,567 lines
- `providers/`: 27 files, 2,782 lines
- `automation/`: 8 files, 2,406 lines
- Total across those areas: 31,266 lines

Cut list for v1:

- Multi-channel matrix. Keep Telegram only (`openclaw-docs/channels/telegram.md`) and drop Discord/Slack/Signal/etc.
- Provider zoo. Keep OpenRouter as abstraction, with 1-2 fallback profiles, not 20+ provider-specific paths (`openclaw-docs/providers/openrouter.md`, `openclaw-docs/concepts/model-providers.md`).
- Plugin/hook ecosystems for v1. Use explicit Temporal workflows and typed events instead of general-purpose runtime extension points.
- Browser automation in v1 unless mission-critical. It is operationally heavy (`openclaw-docs/tools/browser.md`).
- Multi-agent routing/personalities for v1. Our project is one user, one assistant identity.
- Deep node/device pairing surfaces and cross-device presence.

## 4. Architecture Comparison

OpenClaw architecture (gateway-centric, in-process orchestration):

- One long-lived Gateway process owns channels, session state, queueing, tool runtime, and scheduling (`openclaw-docs/concepts/architecture.md`, `openclaw-docs/concepts/agent-loop.md`).
- Persistence is file-centric (`sessions.json` + JSONL transcripts), with queue lanes handling concurrency (`openclaw-docs/reference/session-management-compaction.md`, `openclaw-docs/concepts/queue.md`).
- Reliability relies on retries, compaction, and operational scripts, but not durable workflow execution boundaries.

Our architecture (Temporal-native, workflow-centric):

- Conversation lifecycle is a durable workflow (`OUR-DESIGN.md`, `OUR-ROADMAP.md`).
- Promises/reminders become timers/workflows, not conventions (`OUR-DESIGN.md`).
- Tool calls, memory updates, coding-agent handoffs, and followups become activities/child workflows.

Mapping:

- OpenClaw `sessionKey` -> Temporal workflow ID (`mycel-{user_id}` in roadmap)
- OpenClaw queue lanes -> Temporal task queues + signal handling
- OpenClaw cron/heartbeat -> Temporal schedules + timers
- OpenClaw subagents -> Temporal child workflows
- OpenClaw compaction/retry loops -> ContinueAsNew + activity retry policies

What does not map cleanly:

- OpenClaw’s channel/account/binding complexity
- Plugin/hook generality
- Gateway/device pairing/proxy/discovery concerns

Why our approach is better for this product:

- Reliability semantics are explicit in infra (replay/timers/retries), not implicit in gateway code paths.
- Operational debugging should move from ad-hoc logs to workflow histories.
- We can keep product scope narrow while preserving correctness.

## 5. Specific Lessons for Our Implementation

### Phase 1 (MVP)

- Build transcript validation into the LLM adapter from day 1. OpenClaw had to retrofit transcript hygiene after real provider failures (`openclaw-docs/reference/transcript-hygiene.md`).
- Keep session metadata separate from transcript payloads for debuggability (`openclaw-docs/reference/session-management-compaction.md`).
- Implement deterministic run serialization per user/session immediately (`openclaw-docs/concepts/queue.md`).
- Add explicit silent-turn semantics (`NO_REPLY`) and ensure streaming does not leak it (`openclaw-docs/reference/session-management-compaction.md`).

### Phase 2 (Intelligence)

- Promise Keeper should be durable workflows, not soft reminders. OpenClaw heartbeat/cron docs show the complexity when this is bolted on later (`openclaw-docs/gateway/heartbeat.md`, `openclaw-docs/automation/cron-jobs.md`).
- Model routing must include failure/backoff behavior and profile-level failover from day 1 (`openclaw-docs/concepts/model-failover.md`).
- Memory writes should be asynchronous and explicit; pre-compaction memory flush is a useful pattern we should replicate in cleaner form (`openclaw-docs/reference/session-management-compaction.md`, `openclaw-docs/concepts/memory.md`).

### Phase 3 (Polish)

- If we introduce subagents, enforce max depth and cancellation cascade early (`openclaw-docs/tools/subagents.md`).
- If we add browser or elevated exec, keep them behind explicit policy boundaries and audit logs (`openclaw-docs/tools/browser.md`, `openclaw-docs/tools/exec.md`, `openclaw-docs/gateway/sandboxing.md`).

## 6. The System Prompt Problem

OpenClaw’s prompt assembly is comprehensive but expensive.

What they include each run:

- Tooling, safety text, skill listings, self-update instructions, workspace/runtime metadata, date/time, heartbeat behavior, reasoning settings, and injected bootstrap files (`openclaw-docs/concepts/system-prompt.md`).
- Bootstrap injection caps are high (`bootstrapMaxChars` default 20k per file, total 24k), and several files are always candidates (`AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`, `USER.md`, etc.) (`openclaw-docs/concepts/system-prompt.md`, `openclaw-docs/concepts/context.md`).
- Tool schemas also consume context even when not visible in prompt text (`openclaw-docs/concepts/context.md`).

What actually matters:

- Non-negotiable: tool contracts, hard safety/runtime constraints, current task, minimal identity/tone.
- Useful but should be on-demand: full memory narratives, long behavioral docs, large skills catalogs.
- Often wasteful in every turn: static docs blobs and long bootstrap files.

How we should do it smarter:

- Keep a very small stable core system prompt.
- Move large context into retrieval-backed “context packs” fetched only when needed.
- Enforce token budgets per context section before model call.
- Precompute and cache deterministic prompt fragments; avoid rebuilding giant strings every turn.
- Use role-specific prompt templates for intern/junior/senior/executive activities instead of one massive universal prompt.

## 7. Risk Assessment

Where our replacement can fail if we underestimate complexity:

- Provider transcript compatibility. OpenClaw’s hygiene docs are a warning: subtle ordering/id mismatches can break entire runs (`openclaw-docs/reference/transcript-hygiene.md`).
- Session race conditions. Without strict per-session serialization, tool results and message ordering will drift (`openclaw-docs/concepts/queue.md`, `openclaw-docs/concepts/agent-loop.md`).
- “Silent” background behavior leaks. `NO_REPLY`, streaming, and delivery suppression must be coherent (`openclaw-docs/reference/session-management-compaction.md`, `openclaw-docs/gateway/heartbeat.md`).
- Memory confidence/contradiction handling. OpenClaw’s memory research shows this gets complex fast (`openclaw-docs/experiments/research/memory.md`).
- Security boundary ambiguity. Tool policy, sandbox, and elevated execution must remain explicit and testable (`openclaw-docs/gateway/sandboxing.md`, `openclaw-docs/tools/exec.md`).
- Operational burden drift. If we add channels, providers, hooks, and browser early, we will recreate OpenClaw’s complexity curve.

What OpenClaw solved that we should respect:

- Real-world scheduling and delivery semantics (heartbeat/cron/hooks)
- Provider-specific edge-case normalization
- Session persistence and long-run hygiene/compaction
- Practical troubleshooting playbooks

Bottom line:

- We should replace OpenClaw’s breadth with Temporal-backed depth.
- Keep the reliability lessons, discard the general-purpose platform surface area.
- Build with strict scope discipline so “Mycel” stays personal, durable, and understandable.
