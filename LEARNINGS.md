# LEARNINGS: Pure Python Mycel PoC

## What Worked Well
- Python-first architecture maps cleanly to the design doc: Telegram ingress, Temporal workflow orchestration, activities for side effects.
- `temporalio` workflow model fits the "promises are durable work" concept well.
- Signal + Query gave a straightforward request/reply pattern for chat turns without introducing extra storage.
- Continue-As-New was easy to express and keeps history bounded.
- Async composition is natural in Python: activity calls, bot handlers, and service lifecycle are all `async`.

## What Was Hard or Surprising
- Temporal workflow determinism boundaries are strict. It is easy to accidentally write non-deterministic code in workflow methods.
- "Fire-and-forget" activity patterns need care. If you truly need durable background completion guarantees, child workflows are often cleaner than detached activities.
- There is no single built-in "chat RPC" primitive. You need to choose between Update handlers, Signal+Query polling, or an external response channel.
- Minor lifecycle complexity appears quickly when bot + worker run in one process.

## temporalio Python SDK Ergonomics
- Positive:
  - Native async/await ergonomics are good.
  - Type hints and decorators are clear for workflows/activities.
  - Retry policies are easy to attach per activity call.
- Constraints:
  - Workflow sandboxing and replay-safe coding impose discipline (no arbitrary I/O/time/random/env in workflow code).
  - Data contracts should be explicit and stable early; replay/versioning issues will surface otherwise.
- Update vs Signal+Query:
  - This PoC uses Signal+Query because it is simple and explicit.
  - Update handlers can be cleaner for direct request/reply semantics, but Signal+Query remains robust and easy to reason about for long-lived conversation workflows.

## python-telegram-bot + Temporal Coexistence
- It is viable in one asyncio loop if bot lifecycle is managed manually (`initialize/start/updater.start_polling`), not convenience wrappers that own the loop.
- Worker and bot can coexist as separate tasks; graceful shutdown and cancellation need explicit handling.
- For production, separate processes (or containers) are likely cleaner for fault isolation and scaling.

## Honest Assessment: Is Pure Python Viable?
- Yes for MVP and likely for production if engineering discipline is high around determinism, schema/versioning, and observability.
- The stack is coherent and developer-friendly enough to move quickly.
- Biggest risk is not language/runtime; it is operational rigor (workflow contracts, retries, tooling security, memory quality controls).

## What the Deep-Dive Got Right vs Wrong
- Right:
  - Determinism and lifecycle contracts are real risk areas.
  - Event-loop ownership conflicts are real if lifecycle is not designed deliberately.
  - Reliability/observability/security concerns are more urgent than advanced intelligence features.
- Less accurate / overstated:
  - The Python integration itself is not the bottleneck. The core architecture is straightforward to express in Python.
  - For a PoC, complexity is manageable without heavy abstraction layers.

## What Must Change for Production Readiness
- Add canonical schemas and versioning for signals/queries/activity payloads.
- Add replay tests, integration tests, and failure injection (timeouts, retries, server restarts).
- Add structured logs + tracing IDs tied to workflow/task IDs.
- Add strict tool safety policy (allowlists, command/path constraints, audit trail).
- Add clear memory governance (confidence, provenance, retention/deletion, contradiction workflow).
- Add deployment split and runbooks (bot vs worker processes, health checks, backup/restore).

## Comparison Notes for Bridge PoC Team
- Pure Python PoC demonstrates low ceremony and fast iteration; Temporal concepts remain intact.
- Signal+Query is a practical baseline contract for conversation turn routing.
- Continue-As-New and retry policy behavior are easy to encode and observable.
- If Bridge team optimizes for stronger boundaries, prioritize:
  - explicit contract schemas,
  - worker/bot separation,
  - stronger observability and security scaffolding.

## Environment Limitations Encountered in This PoC Session
- Could not install new packages from PyPI due network restrictions in the sandbox.
- Import check result:
  - `telegram`: available
  - `httpx`: available
  - `temporalio`: missing in this environment
  - `yaml` (`PyYAML`): missing in this environment
- Code is written to be runnable once dependencies are installed in a normal environment.

## Round 2 Findings (Real Dependencies + Tests)

### Dependency Install Experience
- Successfully installed: `temporalio`, `python-telegram-bot`, `httpx`, `pyyaml`, `pytest`, `pytest-asyncio`.
- Installed versions in this environment:
  - `temporalio==1.18.2`
  - `python-telegram-bot==22.5` (already present)
  - `httpx==0.28.1` (already present)
  - `PyYAML==6.0.3`
  - `pytest==8.4.2`
  - `pytest-asyncio==1.2.0`
- No package version conflicts occurred.
- Packaging caveat: this host has old `pip`/tooling (Python 3.9 + `pip 21.2.4`), and local `pip install .` produced an `UNKNOWN-0.0.0` wheel instead of clean project metadata.

### Import Verification Results
- `python3 -c "import temporalio; import telegram; import httpx; import yaml; print('all imports OK')"` passed.
- `python -c ...` could not be used because `python` is not on PATH in this environment (`python3` is available).

### Code Fixes Needed (Round 1 Blind Spots)
- Temporal SDK introspects workflow/query type hints at import time. On Python 3.9, `str | None` caused collection/import failure.
- Fixed by replacing PEP 604 unions with `typing.Optional`/`typing.Union` in:
  - `src/mycel/workflows/conversation.py`
  - `src/mycel/types.py`
  - `src/mycel/config.py`
- Added `pytest-asyncio` to dev dependencies in `pyproject.toml`.

### Integration Test Results
- Added `tests/test_workflow.py` with `temporalio.testing.WorkflowEnvironment` + real worker registration for mock activities.
- Added `tests/conftest.py` to ensure `src/` is importable in this repo layout.
- Test coverage added:
  - Send a message and receive a workflow reply (`query` polling).
  - Continue-As-New after configured N turns.
  - Memory update activity scheduling after a turn.
- Result: `python3 -m pytest -v` => `3 passed`.

### Worker/Bot Startup Attempt
- Worker startup attempt (`PYTHONPATH=src python3 -m mycel.worker --config config/example.yaml`) did not complete within a 12s guard; connection to Temporal at `localhost:7233` is not available here.
- Bot startup attempt (`PYTHONPATH=src python3 -m mycel.bot --config config/example.yaml`) failed fast with `telegram.error.InvalidToken` because `TELEGRAM_BOT_TOKEN` is unset/invalid in `config/example.yaml`.

### temporalio.testing Ergonomics
- Overall good:
  - `WorkflowEnvironment.start_time_skipping()` is practical and fast.
  - Running a real worker in tests gives meaningful confidence with low ceremony.
- Nuance:
  - Continue-As-New assertions are run-aware. Default workflow handles can reflect the current run; to assert Continue-As-New event presence, history must be fetched for the original run ID.

### Revised Honest Assessment
- Pure Python + Temporal remains a strong fit for this architecture.
- With real SDK installed, the main issues are not architectural; they are operational/runtime details:
  - Python version/toolchain consistency,
  - packaging/install ergonomics,
  - run-aware testing patterns for Continue-As-New,
  - environment config hygiene for external systems (Temporal endpoint, Telegram token).
