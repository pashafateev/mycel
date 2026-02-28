# Integration Policy: Tracer Bullets -> Phase 1

## Purpose
Tracer bullets are reference spikes for de-risking architecture and behavior. They inform Phase 1 implementation but are not the Phase 1 codebase.

## Policy
- Tracer bullets live under `src/tb0X` (or equivalent TB modules) and are **not merged wholesale** into MVP.
- Phase 1 implementation happens on a clean `phase/01-mvp` branch created from `main`.
- When Phase 1 needs a proven capability, port only the minimal code needed from TB modules into `src/mycel/` (or the chosen real package path).
- Preserve behavior with focused tests when porting; avoid copying exploratory scaffolding.
- Keep TB modules as regression harnesses during Phase 1. Revisit moving them under `experiments/` after MVP stabilizes.

## Working Method
1. Identify the concrete capability needed for MVP.
2. Locate the TB branch/module that proved it.
3. Re-implement or minimally port into `src/mycel/` with production naming and boundaries.
4. Add/keep behavior-focused tests that lock in what the TB proved.
5. Record source TB branch + commit in code comments or commit message for traceability.

## Non-Goals
- Do not fast-forward or merge `tb/*` branches into Phase 1.
- Do not import test harness internals unless they are required for durable behavior tests.
