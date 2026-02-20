# Tracer Bullet Branching Strategy

## Branch Structure

Branches follow the dependency graph — dependent bullets branch off their parent, not main.

```
main
 │
 ├── tb/01-telegram-temporal-coexistence
 │    ├── tb/02-telegram-idempotency        (branches off tb/01)
 │    │    └── tb/09-durable-followup       (branches off tb/02)
 │    └── tb/10-two-bot-coexistence         (branches off tb/01)
 │
 ├── tb/03-openrouter-resilience
 │    └── tb/04-openrouter-streaming        (branches off tb/03)
 │
 ├── tb/05-mem0-extraction-quality          (branches off main)
 ├── tb/06-model-routing-classifier         (branches off main)
 ├── tb/07-promise-detection                (branches off main)
 └── tb/08-tool-exec-safety                 (branches off main)
```

## Three Chains + Four Independents

| Chain | Branches | Why chained |
|-------|----------|-------------|
| Telegram runtime | 01 → 02 → 09 | Each builds on the previous runtime/contracts |
| Telegram transition | 01 → 10 | Needs the bot setup from TB1 |
| OpenRouter | 03 → 04 | Streaming extends the base adapter |
| Independent | 05, 06, 07, 08 | No shared code, fork from main |

## Execution Waves (with parallelism)

```
Wave 1:  [TB1]                                            1.5-3h
              │
Wave 2:  [TB2] + [TB3 | TB5 | TB6 | TB7 | TB8]          2-4h
          │       ↑ parallel Codex sessions
Wave 3:  [TB4 | TB9]                                      1.5-3h
              │
Wave 4:  [TB10]                                           1-2h
```

## Rules

1. **Each branch gets a LEARNINGS.md** documenting findings, success/fail criteria results
2. **Branches are throwaway by default** — exist to learn, not to merge
3. **Dependent branches build on parent** — TB2 branches off TB1, TB4 off TB3, etc.
4. **Independent branches fork from main** — TB5/6/7/8 have no shared code
5. **If code is worth keeping**, cherry-pick or refactor into a `feat/` branch later
6. **After all bullets complete**, consolidate into `docs/TRACER-BULLET-RESULTS.md`
7. **Delete `tb/*` branches** once learnings are captured

## Critical Path

```
TB1 → TB2 → TB9 = 5-10h (irreducible minimum)
```

Total with parallelism: ~6-12h wall-clock across 4 waves.
