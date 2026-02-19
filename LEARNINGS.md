# Bridge PoC Learnings (TypeScript OpenClaw + Temporal)

Date: 2026-02-19

## What worked well
- The bridge pattern is straightforward: OpenClaw-facing HTTP layer can stay in TypeScript while Temporal handles durable turn processing.
- Temporal Update handlers map cleanly to "new user message" semantics.
- Query-based polling for assistant replies is simple and easy to reason about for a PoC.
- `ContinueAsNew` is easy to add and clearly demonstrates bounded workflow history.
- Mock activities were enough to validate routing + response flow without any API keys.

## What was hard / surprising
- Workflow code constraints are real: anything non-deterministic has to stay in activities or outside workflow runtime.
- It is easy to accidentally return mutable state directly from queries; you need discipline around state shape and growth.
- The TS SDK split between client/worker/workflow contexts requires care in file organization to avoid importing the wrong runtime dependencies.
- Polling queries from the bridge work for PoC, but feel clunky compared with push/callback patterns for production UX.

## Temporal TypeScript SDK ergonomics
- Workflow sandboxing is useful guardrails, but it forces mental overhead:
  - no filesystem/network/time randomness in workflow code
  - explicit activity boundaries for anything side-effectful
- Determinism constraints are manageable once accepted, but you need coding conventions from day 1.
- Update handlers feel good for conversational turns:
  - synchronous acceptance path (`turn_id`)
  - async processing loop in workflow
- Query handlers are simple for status/history reads.
- `ContinueAsNew` ergonomics are good, but you must explicitly design carried state and decide how much history to keep.

## Honest viability assessment for Mycel
- Yes, TypeScript + Temporal is viable for this architecture.
- It is a good fit if you want:
  - durable conversation state
  - explicit lifecycle control (updates, queries, timers, child workflows)
  - clear boundaries between ingress (OpenClaw) and orchestration (Temporal)
- Main tradeoff: higher architectural rigor. You get durability and replay guarantees, but lose "just write normal app code" simplicity.

## What must change for production readiness
- Replace polling reply retrieval with event/callback or signal-driven delivery pattern.
- Add idempotency and ordering strategy for duplicate/out-of-order channel events.
- Add retries/timeouts/non-retryable error taxonomy for activities.
- Add observability baseline: structured logs, correlation IDs, Temporal metadata exposure.
- Add persistence and retention strategy for conversation snapshots and memory integration.
- Define workflow/versioning strategy for schema evolution.
- Add tests:
  - workflow replay safety
  - update/query contract tests
  - worker integration tests with mocked failures
- Harden bridge API with authn/authz and request validation.

## Notes for Python PoC team
- Concepts translate directly:
  - Update handler = user message ingress
  - Query = bridge-side reply/history fetch
  - Activity boundary = where model/tool side effects live
  - Continue-as-new = bound history growth
- Key comparison points to evaluate:
  - SDK ergonomics under determinism constraints
  - testing ergonomics (replay/integration)
  - worker lifecycle and deployment footprint
  - team familiarity and velocity in each language
- Recommendation: compare not only implementation speed, but operational clarity (debugging, versioning, observability) after ~1 week of iterative changes.

---

## Round 2 (2026-02-19): Real dependency install + compile + test + runtime check

### 1. Dependency install experience
- `npm install` succeeded immediately with full network access.
- Installed/validated key deps requested for this round:
  - `@temporalio/client`
  - `@temporalio/worker`
  - `@temporalio/workflow`
  - `@temporalio/activity`
  - `express`
  - `@temporalio/testing` (dev dependency, for integration testing)
- No version conflicts or peer dependency issues surfaced.
- Resolved Temporal SDK versions are `1.15.0` across installed packages (from lockfile resolution under semver ranges).

### 2. Compilation results
- `npx tsc --noEmit` passes with zero errors after real type resolution.
- No TypeScript contract mismatches surfaced from Temporal/Express types.
- Minor structural improvement made for testability:
  - `src/index.ts` now exports bridge helpers and only auto-starts when executed directly (`require.main === module`).
  - `src/worker.ts` now only auto-starts when executed directly and exports `runWorker`.
  - This avoids side effects when importing modules in tests.

### 3. Integration test results
- Added `test/integration.test.ts`.
- Added `npm run test:integration`.
- Test coverage in this file:
  - Imports workflow module, activity module, and bridge module.
  - Verifies core type/contracts are aligned (`ConversationWorkflowInput`, `UserMessageInput`, `UserMessageAccepted`).
  - Uses Temporal test framework (`@temporalio/testing`) + real worker runtime with mock activities.
  - Starts workflow, sends update, queries conversation items, validates routing metadata and assistant reply shape.
- Result:
  - 2/2 tests passing.
  - Temporal worker bundle compiled successfully during test run.

### 4. Runtime smoke test (real bridge + worker processes)
- `npm run dev:worker` started successfully.
- `npm run dev:bridge` started successfully on `http://localhost:3001`.
- Environment difference vs expected failure path:
  - A Temporal server was reachable at `localhost:7233` in this round’s environment, so startup did **not** fail on connection.
- Endpoint checks:
  - `GET /healthz` => `{"ok":true}`.
  - `POST /session/start` => created workflow id successfully.
  - First immediate `POST /session/send` returned transient `WorkflowNotFoundError`.
  - Subsequent `POST /session/send` succeeded and returned mock assistant reply + routing metadata.

### 5. What broke vs what worked out of the box
- Worked out of the box:
  - Dependency install.
  - TypeScript compile.
  - Temporal test framework integration.
  - Worker + bridge startup.
  - End-to-end mocked turn processing after workflow is present.
- Broke / rough edges:
  - Transient race on immediate send after start (`WorkflowNotFoundError`) observed in smoke test.
  - Bridge currently uses polling query loop for replies, which is fine for PoC but still a production limitation.

### 6. Revised honest assessment
- The TypeScript Temporal bridge is now validated with real dependencies and passing integration tests.
- Core architecture remains viable and implementation risk is moderate/controlled.
- Main remaining engineering risk for production is not SDK correctness; it is operational behavior:
  - eliminate start/send race windows,
  - move away from polling reply retrieval,
  - harden idempotency + ordering + observability.
