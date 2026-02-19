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
