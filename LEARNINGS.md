# TB11 Learnings: Intern + Verification Layer

## Verdict
The verification layer is **partially successful** in this spike.

- It **meets quality gating goals** in this run:
  - Catch rate: **100.0%** (target >80%)
  - False escalation rate: **10.5%** (target <15%)
- It **does not meet the strict cost goal**:
  - Path B cost is **57.6% of Path A** (target was <50%)

## Run Summary (20 prompts)
From `data/tb11_verification_results.json`:

- Intern-only accuracy: **95.0%**
- Senior-only accuracy: **90.0%**
- Intern+verification accuracy: **95.0%**
- Intern-bad outputs: **1**
- Bad outputs caught by verifier: **1/1**

## Cost Savings Breakdown
- Path A (senior handles all):
  - Tokens: **6,258**
  - Estimated cost: **$0.014479**
- Path B (intern + verify + redo flagged):
  - Tokens: **16,218**
  - Estimated cost: **$0.008338**
- Delta:
  - Absolute savings: **$0.006141**
  - Relative savings vs Path A: **42.4%**

Interpretation: meaningful savings, but not enough to hit the TB11 success bar (<50% of senior-only).

## Latency Impact
- Path A total latency: **44,611.9 ms**
- Path B total latency: **60,194.7 ms**
- Path B vs Path A: **134.9%**

Interpretation: verification adds material wall-clock latency because every request adds a second model call, and some add a third (redo/escalation).

## Category-Level Impact
- `summarization`:
  - Intern: **80%**
  - Final: **80%**
  - Catch: **100%** on bad intern outputs
  - Most verification value observed here.
- `simple_facts`:
  - Intern: **100%**
  - Final: **100%**
  - Some unnecessary flags observed.
- `reasoning`:
  - Intern: **100%**
  - Final: **100%**
  - Verifier occasionally escalated correct responses.
- `code_tasks`:
  - Intern: **100%**
  - Final: **100%**
  - No verifier-driven gains in this run.

## Edge Cases / Failure Modes
- **Verifier style-over-substance bias** on summarization:
  - `sum_5` was flagged as partially complete due to phrasing/conciseness preferences, not factual failure.
- **False escalations on nuanced but acceptable answers**:
  - `fact_4` (kilobyte nuance) and `reason_3` (polling vs webhooks tradeoff framing).
- **Operational fragility**:
  - The exact requested intern model ID was invalid in OpenRouter; fallback handling was required.
  - Intermittent OpenRouter 5xx errors required retry/failover logic.

## Recommendation
Use verification in MVP **only as a selective policy**, not as a universal default.

- Keep intern-only for low-risk/simple categories.
- Apply verifier primarily to categories with known miss patterns (summarization and selected reasoning prompts).
- Escalate only when verifier confidence is low or correctness is `no`, to reduce false escalations and cost.

With selective verification, quality protection can be retained while improving the current cost (<50%) and latency outcomes.
