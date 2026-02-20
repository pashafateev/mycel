# TB1 Learnings: Telegram + Temporal Coexistence

## Outcome
- The spike code is runnable as a **single asyncio process** with both a Temporal worker and a Telegram bot running concurrently.
- Automated verification passed: `pytest` test for workflow signal/query returns expected `pong`.

## Event Loop Coexistence
- Coexistence design works by running two explicit tasks:
  - Temporal worker task (`async with Worker(...)`)
  - Telegram task (`Application.initialize/start` + `updater.start_polling`)
- A shared `asyncio.Event` (`stop_event`) controls shutdown for both tasks.
- No blocking convenience runner (`Application.run_polling()`) was used.

## Telegram Lifecycle Handling
- Manual lifecycle sequence that worked:
  1. `await app.initialize()`
  2. `await app.start()`
  3. `await app.updater.start_polling(...)`
  4. wait for shutdown signal
  5. `await app.updater.stop()`
  6. `await app.stop()`
  7. `await app.shutdown()`
- This avoids event-loop ownership conflicts with Temporal.

## Temporal Workflow/Activity Notes
- Workflow is long-running and waits for queued signals.
- Signal payload shape is `{request_id, message}`.
- Activity returns `pong: {message}`.
- Query returns response by `request_id`.
- Worker behavior: starting workflow before worker starts is acceptable; commands queue, then execute when worker polls.

## Test Learnings
- Used `temporalio.testing.WorkflowEnvironment.start_time_skipping()` plus real `Worker`.
- One bug surfaced and was fixed: `WorkflowHandle.signal` in this SDK usage expected a single signal argument payload (not multiple positional args).
- Final test result: `1 passed`.

## Dependency/Import Surprises
- Environment has older `pip` (21.2.4) and Python 3.9.
- Editable install from `pyproject.toml` (`pip install -e .`) failed in this environment.
- Adjusted to normal install and direct dependency install.
- Also changed code/type hints to be Python 3.9 compatible (`Optional[...]` instead of `X | Y`) and set `requires-python >=3.9`.

## What Would Need to Change for Production
- Replace polling with webhook deployment strategy where appropriate.
- Add structured logging/metrics/tracing around Telegram update handling and Temporal operations.
- Add idempotency keys + dedupe storage for Telegram update replay safety (TB2 scope).
- Add retries/timeouts/circuit-breakers around bot query wait and Temporal RPC failures.
- Handle multi-user/session routing explicitly (per-chat workflow IDs or session workflows).
- Add secrets/config validation, health endpoints, and supervised process management.
- Add integration tests against a real Temporal dev server + Telegram sandbox account.

---

# TB2 Learnings: Idempotency + Ordering Contract

## Outcome
- Bot-side update idempotency works with an in-memory `seen_update_ids` set keyed by Telegram `update_id`.
- Duplicate updates are dropped before signaling Temporal (no duplicate workflow work created).
- Signal envelope now includes:
  - `update_id` (dedupe key)
  - `chat_id`
  - `sequence` (Telegram `message_id`, monotonic per chat)
  - `request_id`
  - `message`
- Workflow now tracks per-chat expected sequence and logs out-of-order arrivals without blocking processing.

## Verification Results
- Standalone replay (`scripts/test_tb02_idempotency.py`):
  - Generated 30 unique updates, injected 5 duplicates, and reordered 3 messages.
  - Result: `35` replayed updates produced exactly `30` workflow signals.
  - Ordering regressions were detected in replay stream while preserving one signal per unique update.
- Temporal integration test (`tests/test_tb02_idempotency.py`):
  - Sent 10 unique updates + 3 duplicates through replay handler + real Temporal workflow.
  - Result: workflow processed exactly 10 signals and produced exactly 10 unique responses.
  - Out-of-order deliveries were observed and counted by workflow stats.

## Production Delta
- Replace in-memory dedupe with durable storage keyed by `(bot_id, update_id)` and bounded retention.
- Sequence source should be explicit for all update types (edits, callbacks, media groups), not only text message events.
- Add alerting/metrics for:
  - duplicate drop rate
  - out-of-order rate by chat/workflow
  - backlog/latency from signal enqueue to response query hit
- For horizontal scaling, move dedupe + sequence coordination to shared state (e.g., Redis/Postgres) or route each chat to a single partition owner.

---

# TB9 Learnings: Durable Follow-Ups Across Temporal Restart

## Outcome
- `workflow.sleep()` timers survived Temporal dev server restart when started with SQLite persistence:
  - `temporal server start-dev --db-filename /tmp/tb09_temporal.db --port 7233`
- Real restart sequence passed for 3 reminders (30s, 60s, 90s): all delivered exactly once and none lost.
- Delivery deltas observed were well within the 10s budget (~0.04s each in this run).

## Proof Summary (Real Restart Test)
- Script: `scripts/test_tb09_durable.py`
- Flow:
  1. Start Temporal dev server with persistent SQLite DB.
  2. Start TB9 worker.
  3. Schedule 3 reminders.
  4. Wait 15s.
  5. Stop server and worker.
  6. Restart server on same DB, restart worker.
  7. Verify exactly 3 unique deliveries persisted in SQLite.
  8. Validate `abs(delivered_at - expected_at) <= 10s`.

## Integration Test Coverage
- `tests/test_tb09_followup.py` uses `WorkflowEnvironment.start_time_skipping()`.
- Verified:
  - 60s follow-up is delivered exactly once.
  - Two reminders are both delivered once with no duplicates.

## Questions Answered
- Does `workflow.sleep` survive restart?
  - Yes, if Temporal state is persisted (SQLite DB file in dev mode here).
- How long does recovery take after restart?
  - In this spike, recovery was effectively immediate after process restart; timer firing remained near expected times.
- Any edge cases with timer resolution?
  - Small drift exists (milliseconds to low seconds possible depending on restart duration and worker reconnect), but stayed far inside 10s in this run.
- Would this work through machine sleep/wake?
  - Yes in principle: timers are server-side durable state. On wake, overdue timers fire once workers reconnect.
- Recommendation: local Temporal daily driver vs VPS?
  - Local with SQLite is good enough for development and personal daily-driver experiments.
  - For always-on reliability (machine restarts/sleep/network issues), move Temporal to a VPS or managed deployment sooner.
