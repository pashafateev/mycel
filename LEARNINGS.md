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
