# Mycel Pre-Implementation Deep Dive

Date: 2026-02-19
Scope reviewed: `reference/DESIGN.md`, `reference/ROADMAP.md`, `reference/PITCH.md`, `reference/OPENCLAW-ANALYSIS.md`, `reference/ISSUES.md`

## 1) Current State Assessment

### What exists today
- This repo currently contains strategy/design artifacts only. There is no implementation code, test suite, infra-as-code, or runnable prototype.
- The strongest artifacts are:
  - A coherent architectural concept (`Temporal` as orchestration backbone + Telegram interface + memory layers + model routing org).
  - A phased roadmap with rough sequencing.
  - A seeded issue backlog (20 issues) aligned to phases.

### What is well-defined
- Product intent and differentiation are clear: personal, durable, memory-centric assistant, not a generic chatbot.
- Core architectural shape is clear:
  - Telegram ingress
  - Long-lived `ConversationWorkflow`
  - Child workflows for tools, follow-ups, memory updates
  - Async memory update path
- Cost-conscious model routing concept (“The Organization”) is explicit and actionable.
- Error philosophy is directionally strong: remediation-first, not apology-first.

### What is underspecified (critical)
- Determinism boundaries for Temporal workflows are not concretely specified (what code is allowed in workflow context vs activity context).
- Workflow lifecycle rules are missing:
  - idempotency strategy
  - signal/update contract schema
  - duplicate Telegram update handling
  - message ordering guarantees
- Tool safety model is underspecified (especially `exec`, filesystem scope, network policy, escalation).
- Memory data contract is missing:
  - canonical memory schema
  - source attribution/provenance
  - confidence scoring/TTL/conflict policy
  - deletion/retention policy
- Operational SLOs are absent (availability target, latency targets, retry budgets, alert thresholds).
- No explicit migration plan from OpenClaw state to Mycel state.

### Dependency maturity check (current state)

#### 1. `temporalio` Python SDK
- Latest version: `1.23.0` (released Feb 18, 2026 on PyPI).
- Python requirement: `>=3.10`.
- Async support quality: mature enough for production use, with explicit support for async workflows/activities, testing utilities, and workflow sandboxing.
- Important caveats from official SDK docs/repo:
  - Sandbox is best-effort and explicitly *not* a security boundary.
  - Known incompatibility with `gevent.monkey.patch_all()`.
  - Protobuf 4.x strongly recommended; protobuf 3.x can cause sandbox/global-state issues.
- Active issue surface is non-trivial (100+ open issues in repo). Recent open bugs include worker polling behavior and sandbox edge cases. This indicates maturity with ongoing sharp edges, not instability.
- Assessment: **production-capable, but high-discipline required around determinism, async behavior, and worker lifecycle.**

#### 2. `mem0ai` (Mem0 OSS)
- Latest PyPI version: `1.0.4` (released Feb 17, 2026).
- Package requires Python `>=3.9,<4.0`.
- What it provides (OSS): memory extraction/search/update APIs with pluggable LLM/embedder/vector store; defaults include OpenAI + local Qdrant + SQLite history.
- Self-hosting: yes, clearly supported by docs (OSS path + Docker Compose + configurable providers).
- “Production-ready” nuance:
  - Platform docs position managed Mem0 as production-ready with HA/autoscaling.
  - OSS docs position OSS as self-hostable and extensible, but infra reliability is your responsibility.
- Risk signal: active OSS issue volume includes bugs in metadata filtering, provider-specific graph behavior, telemetry behavior, and integration edge cases.
- Assessment: **usable and fast-moving, but OSS appears operationally “you own the sharp edges.” Not experimental, but not turnkey production without hardening.**

#### 3. `python-telegram-bot`
- Latest version: `22.6` (Jan 24, 2026 on PyPI).
- Async maturity: strong. Library is fully asyncio-native (since v20 line) and widely used.
- Polling vs webhook tradeoffs (official docs):
  - `run_polling()` is simplest for local/dev and small deployments.
  - `run_webhook()` requires webhook setup (`python-telegram-bot[webhooks]` extra), HTTPS/public endpoint constraints, and infra readiness.
  - Both convenience runners block event loop until stop signal; for multi-framework orchestration, manual startup/shutdown is recommended.
- Assessment: **mature and appropriate choice; integration design should avoid event-loop ownership conflicts with Temporal worker runtime.**

#### 4. OpenRouter API
- Core capability: model multiplexing + provider routing + fallbacks + standardized chat API + streaming.
- Streaming: supported (`stream: true`) with SSE; mid-stream errors come as stream events (HTTP status may remain 200 after stream starts).
- Routing reliability mechanics: configurable provider ordering/fallbacks; default load balancing includes outage-aware behavior.
- Rate limits (official docs): explicit limits on `:free` variants (20 RPM, 50/day or 1000/day if credits threshold met), plus DDoS protections.
- Availability signal (status page snapshot 2026-02-19):
  - Chat API 90-day uptime shown around `99.88%`
  - Multiple recent incidents including short chat/generation outages and a Feb 17, 2026 “401 errors across API surfaces” incident.
- Assessment: **high leverage, but external reliability and provider variance must be treated as first-class failure mode.**

#### 5. Other dependencies in design
- `httpx`: mature async HTTP client; low-risk dependency.
- SQLite (graph edges): stable and sufficient for MVP, but graph query complexity can hit ceiling quickly as relationships grow.
- `gh` CLI + coding agent integrations (`codex`, `claude-code`): feasible but operationally brittle unless permissions, auth refresh, and sandboxing are defined tightly.
- Temporal Server local/self-hosted: technically straightforward for dev, but production ops requires dedicated backup/upgrade/runbook planning.

## 2) Gap Analysis

### Missing design elements needed before implementation
1. **Canonical contracts**
- Message envelope schema for workflow signals/updates.
- Tool-call contract (input/output/error taxonomy).
- Memory record schema (entity, fact, confidence, source, timestamp, supersedes).

2. **Determinism and workflow boundaries**
- Explicit “never in workflow code” list (network, time, randomness, filesystem, env reads).
- Activity retry classes and non-retryable exception matrix.
- Continue-as-new policy thresholds (history size, turn count, payload size).

3. **Security model beyond `allowed_users`**
- Secret management pattern.
- Tool-level allow/deny policy (commands, paths, domains).
- Prompt injection and tool exfiltration defenses.
- Audit trail requirements.

4. **Operational model**
- Deploy topology (single process vs split bot/worker).
- Metrics/logging/tracing standards.
- Incident response runbooks.

5. **Economics model**
- Real token budget assumptions per activity class.
- Cost guardrails (daily cap, per-workflow cap, auto-downgrade behavior).

### Issues that should exist but don’t
- Data model and schema governance issue (workflow events + memory facts).
- Security hardening issue (tool policy, secret handling, injection defenses).
- Observability issue (metrics/traces/log correlation + dashboards).
- Test strategy issue (workflow replay, integration tests, fault injection).
- Disaster recovery issue (Temporal DB backup/restore, Mem0/vector backup).
- OpenClaw migration issue (state mapping, phased cutover).
- Dependency pin/upgrade policy issue.

### Existing issues that are underscoped
- #3 Temporal workflow: should explicitly include idempotency, signal contracts, replay-safe coding standards.
- #4 OpenRouter adapter: should include streaming error semantics, provider fallback policy, quota handling.
- #6 Tools: should include threat model + policy engine and audit logging, not only functionality.
- #8 Memory foundation: should include schema, conflict resolution, retention/deletion policy.
- #9 Model routing: should include eval dataset definition + regression gates.
- #11 Coding agent integration: should include credential boundary and rollback strategy.
- #20 Evals: should begin in Phase 1, not Phase 2-only.

### Existing issues potentially overscoped (for MVP)
- #11 coding-agent integration may be too large before baseline reliability is proven.
- #19 Zettelkasten graph may be large if Mem0 quality is not yet validated in production traffic.

### Deferred decisions that should be made now
- Polling vs webhook for MVP (and migration trigger criteria).
- Temporal deployment target for MVP (local server vs Temporal Cloud).
- Memory system of record (Mem0 vs workspace markdown vs graph DB) and precedence on conflicts.
- Hard limits and policies for `exec` tool.
- Model fallback chain per critical activity and outage strategy.

## 3) Risk Register

### Technical risks
1. **Temporal complexity risk**
- Likelihood: Medium
- Impact: High
- Why: Determinism/replay mistakes are easy early.
- Mitigation: strict workflow/activity coding guide, replay tests, code review checklist.

2. **OpenRouter/provider behavior variance**
- Likelihood: High
- Impact: High
- Why: cross-provider quirks, intermittent outages, 401/429/502/503 pathways.
- Mitigation: resilient adapter, retries/backoff/circuit breakers, fallback model list, user-facing degraded mode.

3. **Mem0 OSS operational drift**
- Likelihood: Medium
- Impact: Medium-High
- Why: fast-moving OSS with active bug surface; provider/vector permutations can break unexpectedly.
- Mitigation: pin versions, start with narrow provider set, nightly memory integrity checks.

4. **Event-loop ownership conflicts**
- Likelihood: Medium
- Impact: Medium
- Why: Telegram app lifecycle and Temporal workers are both async-heavy.
- Mitigation: explicit process model; avoid convenience runners in combined runtime if needed.

### Architectural risks
1. **Over-indexing on memory before data quality controls**
- Likelihood: High
- Impact: High
- Why: automatic extraction can accumulate wrong/conflicting facts quickly.
- Mitigation: confidence thresholds, provenance, contradiction review loop, purge APIs.

2. **Premature graph layer complexity**
- Likelihood: Medium
- Impact: Medium
- Why: linked graph adds complexity before core assistant value is proven.
- Mitigation: ship retrieval-first memory, defer advanced linking until quality metrics exist.

3. **Model routing cost assumptions may be optimistic**
- Likelihood: High
- Impact: Medium-High
- Why: routing overhead, retries, tool loops, and memory passes add hidden token cost.
- Mitigation: enforce per-activity token budgets and cost telemetry from day 1.

### Operational risks
1. **Limited production observability at launch**
- Likelihood: High
- Impact: High
- Mitigation: require structured logs + workflow IDs + distributed tracing before MVP cutover.

2. **Backup/restore blind spots**
- Likelihood: Medium
- Impact: High
- Mitigation: define backup targets and restore drills for Temporal DB + Mem0/vector + workspace.

3. **Secret/auth expiry failure loops**
- Likelihood: Medium
- Impact: Medium
- Mitigation: preflight health checks for Telegram/OpenRouter/GitHub tokens and clear remediation UX.

### Cost risks
- Current design estimate (~$0.68/day) likely excludes:
  - retries and fallback model usage
  - memory extraction/linking token overhead under realistic turn lengths
  - tool-result summarization loops
- Risk level: **Medium-High** until measured with real traces.

### Timeline risks
- “~1 week MVP” is likely **aggressive** if MVP includes robust error remediation + memory integration + Temporal correctness.
- Realistic range for a stable internal MVP is closer to **2–3 weeks** unless scope is narrowed:
  - Week 1: Telegram + Temporal + single-model + minimal tools
  - Week 2: reliability/error handling + observability + basic memory
  - Week 3: hardening + migration + evals

## 4) Blind Spots

### Security beyond allowed users
- No explicit prompt-injection defense for tool calls.
- No command/path/domain allowlists for tool execution.
- No secret redaction policy in logs/workflow history.
- No data governance policy (PII handling, retention, delete-on-request).

### Testing strategy gap
- Need a multi-layer plan:
  - deterministic workflow replay tests
  - activity unit tests with mocked providers
  - integration tests with Telegram update fixtures
  - chaos/failure injection (OpenRouter 429/503, Temporal restart, Mem0 timeout)
  - cost regression tests (token/call budgets)

### Local developer experience gap
- Missing explicit `make dev`/`just dev` workflow for:
  - starting Temporal
  - running worker/bot
  - hot-reload + fixture replay
  - inspecting workflow history quickly

### Persistence and backup gap
- Mem0/vector store persistence location and backup cadence are undefined.
- SQLite graph backup/compaction strategy undefined.
- Workspace file backup/versioning policy undefined.

### Failure modes not covered
- Temporal server unavailable/recovering.
- OpenRouter wide outage or model-specific unavailability.
- Telegram webhook delivery failures / long-poll drift.
- Partial workflow completion with user-visible ambiguity.

### OpenClaw migration gap
- No explicit cutover mechanics:
  - parallel run period
  - memory import strategy
  - session continuity mapping
  - rollback trigger criteria

## 5) Recommendations (Before Writing Code)

### Ordered pre-code decisions/actions
1. Finalize **runtime architecture contract** (process layout, workflow boundaries, determinism rules).
2. Define **security policy** for tools/secrets/logging before implementing any exec/web tools.
3. Lock **MVP scope** to reliability-first:
- Telegram + Temporal + one conversation workflow + one model tier + minimal toolset.
4. Define **data contracts** for workflow events, memory records, and error classes.
5. Establish **observability baseline** (structured logs, trace IDs, Temporal IDs, error dashboards).
6. Implement **evaluation harness early** (quality + cost + latency), not as Phase 2 add-on.
7. Decide **OpenRouter resilience policy** (fallback order, retry budget, degraded mode messaging).
8. Decide **Mem0 strategy**:
- start with OSS pinned versions and narrow provider matrix, or adopt platform if reliability > control.
9. Define **backup/restore + DR runbooks** before production usage.
10. Write **migration playbook from OpenClaw** with rollback criteria.

### Suggested design additions
- Add a “Non-Functional Requirements” section to DESIGN.md:
  - SLO/SLA targets
  - max response latency target
  - acceptable data loss target
- Add a “Security Architecture” section:
  - trust boundaries, threat model, policy enforcement points
- Add an “Operational Readiness Checklist” gate before any cutover.

### New issues to file
1. Workflow/data contracts + schema versioning
2. Determinism standards + Temporal replay test suite
3. Tool security policy engine (allowlists + audit logs)
4. Observability baseline (metrics, traces, correlation IDs)
5. DR/backup strategy for Temporal + memory stores
6. OpenClaw migration/cutover plan
7. Cost guardrails + budget enforcement
8. Local dev bootstrap and fixture replay tooling

### Dependency alternatives worth considering
- Memory layer alternative for MVP: simpler custom memory store (SQLite + embeddings) to reduce moving parts, then evaluate Mem0 re-introduction after baseline stability.
- OpenRouter fallback strategy: keep direct provider adapters (OpenAI/Anthropic) as optional emergency bypass path (feature-flagged).
- Graph store: keep SQLite for MVP; defer Neo4j/Memgraph until concrete graph-query use cases justify ops overhead.

## Appendix: Dependency Snapshot (2026-02-19)
- `temporalio`: 1.23.0 (PyPI)
- `mem0ai`: 1.0.4 (PyPI)
- `python-telegram-bot`: 22.6 (PyPI)
- OpenRouter status snapshot:
  - chat uptime (90d): 99.88%
  - recent incidents include API inaccessibility and 401 surface errors

## Sources
- Design docs reviewed:
  - `reference/DESIGN.md`
  - `reference/ROADMAP.md`
  - `reference/PITCH.md`
  - `reference/OPENCLAW-ANALYSIS.md`
  - `reference/ISSUES.md`
- Dependency/official references:
  - Temporal PyPI: https://pypi.org/project/temporalio/
  - Temporal Python SDK repo/docs: https://github.com/temporalio/sdk-python
  - Mem0 PyPI: https://pypi.org/project/mem0ai/
  - Mem0 OSS overview: https://docs.mem0.ai/open-source/overview
  - Mem0 Platform vs OSS: https://docs.mem0.ai/platform/platform-vs-oss
  - Mem0 OSS config: https://docs.mem0.ai/open-source/configuration
  - PTB PyPI: https://pypi.org/project/python-telegram-bot/
  - PTB Application docs: https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html
  - OpenRouter API overview: https://openrouter.ai/docs/api-reference/overview
  - OpenRouter provider routing: https://openrouter.ai/docs/guides/routing/provider-selection
  - OpenRouter streaming: https://openrouter.ai/docs/api/reference/streaming
  - OpenRouter limits: https://openrouter.ai/docs/api/reference/limits
  - OpenRouter models API: https://openrouter.ai/docs/api-reference/models/get-models
  - OpenRouter status: https://status.openrouter.ai/
  - Telegram Bot API (getUpdates/webhooks): https://core.telegram.org/bots/api
