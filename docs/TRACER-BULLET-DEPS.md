# Tracer Bullet Dependency Map (Mycel)

## 1) Dependency Graph

### Hard Dependencies (blocking)
| From | To | Why hard-blocking |
|---|---|---|
| TB1 | TB2 | TB2 depends on working Telegram+Temporal runtime.
| TB1 | TB9 | TB9 reminder delivery test needs runtime integration baseline.
| TB2 | TB9 | TB9 exact-once reliability depends on idempotency/ordering contract.
| TB1 | TB10 | Two-bot coexistence only meaningful after baseline bot runtime works.
| TB3 | TB4 | TB4 streaming hygiene extends TB3 base OpenRouter activity.

### Soft Dependencies (informing, not blocking)
| From | To | Why soft |
|---|---|---|
| TB3 | TB5 | OpenRouter activity patterns can inform Mem0 extraction call strategy.
| TB3 | TB6 | Error/latency profile can tune routing thresholds.
| TB3 | TB7 | Detector model/provider choice can reuse TB3 adapter learnings.
| TB8 | TB10 | Tool policy can inform coexistence UX/command safety, but not required.

### Independent (no required upstream)
- TB1 (root runtime spike)
- TB3 (after TB1 per plan intent, but technically independent of TB2/TB9/TB10)
- TB5 (can run standalone eval harness)
- TB6 (standalone classifier eval)
- TB7 (standalone detector eval)
- TB8 (independent if run in local harness; depends on TB1 only if tested through bot path)

### ASCII Graph
Legend: `-->` hard dependency, `-.->` soft dependency

```text
                TB3 ------------------> TB4
                 |  -.-> TB5
                 |  -.-> TB6
                 |  -.-> TB7
                 |
TB1 ------------> TB2 ------------> TB9
 |                
 |---------------> TB10 <.-.-.- TB8
 |
 '---> TB8   (only if TB8 tested via bot path; otherwise TB8 is independent)

TB5, TB6, TB7 are mutually independent.
```

## 2) Maximum Parallelism Plan (theoretical, ignoring resource conflicts)

Assumed hard-edge set for maximum concurrency math:
- `TB1 -> TB2 -> TB9`
- `TB1 -> TB10`
- `TB3 -> TB4`
- TB5/TB6/TB7/TB8 independent

### Max simultaneous bullets
- **7 at once** (after TB1 completes): `TB2 TB3 TB5 TB6 TB7 TB8 TB10`

### Wave diagram (ASAP scheduling)
```text
Wave 1: [TB1]
Wave 2: [TB2 | TB3 | TB5 | TB6 | TB7 | TB8 | TB10]   (7 parallel)
Wave 3: [TB4 | TB9]
```

### Theoretical minimum total time
Using scope ranges from plan (`h`):
- TB1: 1.5-3
- Wave 2 duration = max(TB2 2-4, TB3 2-3, TB5 2-4, TB6 1-3, TB7 1-2, TB8 2-4, TB10 1-2) = **2-4**
- Wave 3 duration = max(TB4 1-3, TB9 1.5-3) = **1.5-3**

Total theoretical minimum = **5.0-10.0h** (best-case lower bound to worst-case upper bound).

## 3) Practical Parallelism Plan (with shared-resource constraints)

### Resource conflicts
| Resource | Conflicting bullets | Constraint |
|---|---|---|
| Telegram bot identity / update stream | TB1, TB2, TB9, TB10 | Do not run simultaneously on same bot token/chat if validating ordering/idempotency.
| Telegram test account/chat history | TB2, TB9, TB10 | Avoid concurrent runs to prevent cross-test contamination.
| Temporal server state (local SQLite namespace) | TB1, TB2, TB9 (+possibly TB8 bot-path) | Prefer isolated task queues/namespaces or run sequentially for clean reliability signals.
| OpenRouter key/rate limits | TB3, TB4, TB6, TB7 (if LLM-based) | Parallelism possible, but throttle to avoid synthetic 429 noise.
| Mem0 store/index | TB5 (primary), others if sharing memory backend | Keep TB5 isolated dataset/namespace for clean precision/recall eval.

### Codex session independence
| Pair | Can run in separate Codex sessions? | Notes |
|---|---|---|
| TB5 + TB3 | Yes | Independent codepaths; only coordinate API key rate limits.
| TB6 + TB7 | Yes | Fully independent eval datasets/harnesses.
| TB2 + TB9 | No (practically) | Same Telegram/Temporal reliability chain; run sequentially.
| TB10 + (TB2 or TB9) | No (practically) | Shared Telegram user/intent collisions invalidate results.
| TB8 + TB3/TB5/TB6/TB7 | Yes | If TB8 uses local harness, no runtime interference.

## 4) Revised Execution Plan (practical waves)

### Recommended waves
| Wave | Bullets | Parallel session guidance | Est. wall-clock | Unlocks |
|---|---|---|---|---|
| 1 | TB1 | Single env/session | 1.5-3h | Runtime baseline for Telegram-facing chain |
| 2 | TB2 + TB3 + TB5 + TB6 + TB7 + TB8 | TB2 in dedicated Telegram/Temporal env; run TB3/TB5/TB6/TB7/TB8 in parallel sessions | 2-4h (dominated by longest in set) | Idempotency contract + LLM/memory/routing/tool safety signals |
| 3 | TB4 + TB9 | TB4 in OpenRouter session; TB9 in dedicated Telegram/Temporal env | 1.5-3h | Streaming decision + durable follow-up confidence |
| 4 | TB10 | Dedicated Telegram coexistence env | 1-2h | Transition feasibility decision |

### Practical total
- **6.0-12.0h** wall-clock (wave-max sum), assuming enough parallel Codex sessions and isolated test resources.

## 5) Critical Path

### Longest hard-dependent chain
```text
TB1 -> TB2 -> TB9
```
- Duration: **5.0-10.0h** (1.5-3 + 2-4 + 1.5-3)
- This is the minimum irreducible time floor regardless of additional parallelism.

