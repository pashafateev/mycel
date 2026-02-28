# Phase 1 MVP Plan

## Scope (High Level)
- Telegram message in -> Temporal workflow -> OpenRouter LLM -> reply out.
- Durable, restart-safe conversation flow (`ContinueAsNew`, retries, clean shutdown).
- Baseline error handling for transient vs persistent failures.
- TODO: Confirm exact Phase 1 cutline for tools and memory from existing roadmap/issues.
- TODO: Confirm final Python package path (`src/mycel/` vs alternative) before scaffolding.

## First Steps
- [ ] Create branch `phase/01-mvp` from `main`.
- [ ] Create `src/mycel/` skeleton and test layout.
- [ ] Port OpenRouter client/activity patterns from TB3 and TB4 (non-streaming first; streaming behind flag).
- [ ] Port durable follow-up timer/restart patterns from TB9.
- [ ] Adopt TB10 command/namespace routing for coexistence-safe bot command handling.
