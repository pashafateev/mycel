# Tracer Bullet Results

## Executive Summary
Across 10 tracer bullets, 9 passed and 1 was partial (TB5 Mem0 extraction quality). Core architectural assumptions were validated: Telegram + Temporal can coexist in one async process, Temporal provides durable long-running orchestration (including restart-safe timers), OpenRouter integration can be made resilient, routing/detection quality is production-viable with LLM-backed classifiers, and constrained tool execution is practical. The main plan change is memory: TB5 did not meet extraction/retrieval reliability targets, so Phase 1 should use file-based memory plus targeted custom extraction.

## Results Table
| TB | Name | Status | Key Metric | One-line Finding |
|---|---|---|---|---|
| TB1 | Telegram + Temporal Coexistence | Pass | `pytest`: 1 passed | Single-process asyncio coexistence works with explicit lifecycle control. |
| TB2 | Telegram Idempotency + Ordering | Pass | 35 replayed updates -> 30 signals | Duplicate updates were dropped correctly; out-of-order delivery was detectable without blocking. |
| TB3 | OpenRouter Resilience | Pass | Real calls + fault injection all handled | Retryable/non-retryable error mapping and Temporal retry behavior worked as designed. |
| TB4 | OpenRouter Streaming | Pass | Interrupted streams recoverable via retries | Buffered SSE streaming in activity is viable; transcript hygiene guards prevented invalid payload tails. |
| TB5 | Mem0 Extraction Quality | Partial | Precision 0.588, Recall 0.476, Top-3 hit rate 0.417 | Mem0 setup/storage worked, but extraction/retrieval quality and operation reliability were below bar. |
| TB6 | Model Routing Classifier | Pass | Real LLM accuracy 95%, 0 high-risk misroutes | LLM routing significantly improved safety/accuracy vs keyword-only baseline. |
| TB7 | Promise Detection | Pass | Precision 1.0, Recall 0.8, F1 0.889 (real LLM) | Detection is reliable for explicit commitments; soft commitments remain the main miss pattern. |
| TB8 | Tool Exec Safety Envelope | Pass | No lingering/zombie processes after timeout kill/reap tests | Strict constrained execution is feasible; unrestricted generic exec should not ship in MVP. |
| TB9 | Durable Follow-up Timers | Pass | 3/3 reminders delivered exactly once after restart | `workflow.sleep()` timers survived server restart with persisted Temporal state. |
| TB10 | End-to-End Happy Path (Two-Bot Transition) | Pass | 0/20 double-handled commands | Namespace split worked for deterministic command routing with explicit shared-command arbitration. |

## Per-TB Details

### TB1 - Telegram + Temporal Coexistence
- What was tested: Running Telegram bot polling loop and Temporal worker in one asyncio process.
- Key results: Workflow signal/query verification passed (`1 passed`); explicit Telegram lifecycle sequence avoided loop ownership conflicts.
- Surprises/gotchas: `WorkflowHandle.signal` expected one payload argument; environment constraints required Python 3.9-compatible typing and non-editable install path.
- Production delta: Move to webhooks where appropriate, add observability, RPC timeout/circuit-breaker handling, and production process supervision.

### TB2 - Idempotency + Ordering Contract
- What was tested: Dedupe of Telegram updates and ordering metadata propagation into workflow signals.
- Key results: Replay test delivered 35 updates (30 unique + duplicates) and produced exactly 30 workflow signals; Temporal integration processed 10 unique updates and returned 10 unique responses.
- Surprises/gotchas: Out-of-order arrivals are normal and must be expected even when dedupe is correct.
- Production delta: Replace in-memory dedupe with durable shared store keyed by `(bot_id, update_id)`; add duplicate/out-of-order/latency metrics.

### TB3 - OpenRouter Resilience
- What was tested: Temporal activity (`call_llm`) retry behavior and error normalization for OpenRouter failures.
- Key results: Real OpenRouter calls were successful; fault injection for timeout, invalid model, and empty prompt was handled correctly; transient failures mapped to retryable classes and non-transient failures remained non-retryable.
- Surprises/gotchas: Retry counts depend on activity attempt metadata unless exported to a separate metrics sink.
- Production delta: Add provider fallback chain, adaptive throttling/circuit breaker, structured telemetry, and model-specific timeout budgets.

### TB4 - Streaming + Transcript Hygiene
- What was tested: SSE streaming via OpenRouter inside a Temporal activity, plus transcript validation before calls.
- Key results: Streaming implementation buffered deltas and returned a complete response payload; interrupted streams were normalized to retryable errors and recovered through Temporal retries.
- Surprises/gotchas: Temporal activities cannot yield partial chunks to workflow callers, so buffering in activity is required.
- Production delta: Ship streaming behind a feature flag with dedicated metrics for chunk parse failures, disconnects, and partial token accounting.

### TB5 - Mem0 Extraction Quality
- What was tested: Mem0 OSS extraction and retrieval quality on a 10-snippet dataset with nuanced fact patterns.
- Key results: Precision `0.588` (10/17), Recall `0.476` (10/21), retrieval top-3 hit rate `0.417` (5/12).
- Surprises/gotchas: Mem0 `add()` returned empty results while still storing memories, with recurring SQLite thread errors; provider bug observed for `xai` in `mem0ai==1.0.4`.
- Production delta: Use file-based memory for Phase 1; add targeted custom extraction for critical facts; re-evaluate Mem0 after quality and reliability issues are resolved.

### TB6 - Model Routing Classifier
- What was tested: Tier routing quality for intern/junior/senior/executive request classes.
- Key results: Real LLM rerun reached `95%` accuracy with `0` high-risk misroutes (improved from keyword baseline).
- Surprises/gotchas: Senior vs executive remains the hardest semantic boundary.
- Production delta: Adopt hybrid policy (rules-first + cheap LLM for ambiguous prompts + conservative escalation on low confidence).

### TB7 - Promise Detection Reliability
- What was tested: Commitment detection for explicit, soft-ambiguous, and non-commitment utterances.
- Key results: Real LLM rerun: Precision `1.0`, Recall `0.8`, F1 `0.889`; two soft commitments were missed.
- Surprises/gotchas: Conservative logic minimizes false positives but can miss softly phrased real commitments.
- Production delta: Auto-trigger follow-up only on explicit commitments; require confirmation for soft/ambiguous statements.

### TB8 - Tool Execution Safety Envelope
- What was tested: Safety policy around command execution, including nested command risk, output flood handling, and timeout cleanup.
- Key results: Process-group kill/reap behavior was reliable; no lingering or zombie processes observed in timeout paths.
- Surprises/gotchas: `python -c` can bypass naive allowlists; shell redirection/pipes require explicit blocking.
- Production delta: Ship constrained high-level tools by default; avoid unrestricted generic exec in MVP.

### TB9 - Durable Follow-up Across Restart
- What was tested: Durability of Temporal timer-based reminders across full server/worker restart with persisted DB state.
- Key results: Three reminders (30s/60s/90s) were delivered exactly once after restart; observed delivery deltas were about `0.04s` and within 10s budget.
- Surprises/gotchas: Small drift is expected around restart/reconnect windows.
- Production delta: Use persistent Temporal deployment for always-on reliability; keep local SQLite mode for dev.

### TB10 - End-to-End Happy Path (Mycel + OpenClaw Transition)
- What was tested: Parallel two-bot routing behavior during migration period.
- Key results: 0 double-handled commands out of 20 in simulation with namespace split.
- Surprises/gotchas: Namespace split alone is not enough for shared commands (`/start`, `/help`) or unprefixed text.
- Production delta: Add first-responder arbitration for shared commands and keep Mycel as default plain-text owner during migration.

## Architecture Decisions Confirmed
- Temporal is a strong orchestration core for Mycel: long-running workflows, signals/queries, retries, and durable timers all validated.
- Single-process Telegram + Temporal runtime is feasible with explicit asyncio task/lifecycle control.
- OpenRouter integration is workable for both standard and streaming paths with explicit retry/error classification.
- LLM-backed decision points (routing and commitment detection) can meet practical reliability/safety needs with guardrails.
- Safe tool execution should be policy-first (allowlist + scope + timeout + output cap), not unrestricted shell access.

## Architecture Decisions Changed
- Memory subsystem plan changed for Phase 1: TB5 supports a file-based memory approach instead of Mem0-backed extraction/retrieval.
- Model routing should not remain keyword-only: TB6 real-LLM rerun supports hybrid routing with escalation policy.
- Commitment handling should separate explicit vs soft commitments: TB7 results support confirmation-first handling for soft language.
- Two-bot migration requires arbitration logic beyond command namespace partitioning (TB10).

## Risk Register
- Real-world Telegram scale behavior under sustained burst/replay and multi-instance horizontal scaling is not fully load-tested.
- OpenRouter sustained-rate-limit windows and provider outage behavior still need fallback-chain validation under load.
- Streaming observability and token accounting at production traffic levels remain unproven.
- Long-horizon timer behavior across longer outages (hours/days) and infra failovers needs broader soak testing.
- Prompt/data drift may reduce routing and promise-detection quality over time without periodic eval refreshes.
- Security posture for tool execution still depends on strict policy hygiene; sandbox hardening remains future work.

## Recommended Phase 1 Priorities
1. Build the production message pipeline first: TB1+TB2+TB9 core (Telegram ingress, durable workflow orchestration, idempotency, restart-safe follow-ups).
2. Ship resilient LLM activity layer next: TB3 baseline with structured telemetry and retry/failure policy.
3. Enable TB6 hybrid model routing and TB7 explicit-commitment follow-up trigger with conservative escalation/confirmation guardrails.
4. Keep memory simple in Phase 1: file-based memory + targeted extraction for commitments/preferences; defer Mem0 integration.
5. Roll out streaming (TB4) behind a feature flag once non-streaming path is stable and instrumented.
6. Keep tool execution constrained (TB8): high-level tools by default, no unrestricted generic exec.
7. Execute TB10 migration controls early if running both bots concurrently: namespace ownership + shared-command arbitration.
