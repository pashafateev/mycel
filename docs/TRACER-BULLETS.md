# Mycel Tracer Bullet Plan

## 1) Project State Assessment

## Where Mycel is right now
- Strong design and roadmap clarity, but implementation is still at pre-build stage.
- Two PoCs already validated Temporal basics:
- Bridge PoC (TypeScript + Temporal): compiled, 2/2 integration tests passed, mock end-to-end turn worked.
- Python PoC (pure Python + Temporal): compiled, 3/3 tests passed, including `ContinueAsNew` and memory activity scheduling.
- Architecture decision is made: pure Python is the target, bridge only as temporary migration aid if needed.

## What has been proven
- Temporal can run core conversation workflow mechanics in both bridge and pure Python paths.
- Python Temporal path supports turn handling and workflow lifecycle primitives (`ContinueAsNew`, scheduled memory activity).
- Temporal hosting path is clear for build phase: local `start-dev` + SQLite persistence.

## What has not been proven yet
- Telegram bot runtime and Temporal worker can coexist cleanly in one asyncio process without lifecycle conflicts.
- Telegram update ordering/idempotency behavior under retries/duplicates.
- OpenRouter reliability in real workflow activities (429/5xx/401/stream interruption handling).
- Mem0 OSS quality and stability for real extraction + retrieval in this use case.
- Cheap-model routing reliability for correct tier selection.
- Promise detection quality (precision/recall) good enough to avoid reminder spam or missed commitments.
- Safe tool execution boundaries (exec allowlist, timeout, failure recovery).
- Two-bot coexistence UX (Mycel + OpenClaw serving same Telegram user during transition).

## Biggest remaining unknowns (from deep-dive + docs)
- Determinism boundaries and workflow contract discipline in real app code.
- Operational reliability of external dependencies (OpenRouter incidents, Mem0 OSS edge cases).
- Memory data quality controls (confidence/provenance/conflict handling) before scale.
- Session serialization and race prevention in Telegram-driven traffic.

---

## 2) Recommended Tracer Bullets (Execution Order)

## TB1 — Single-Process Telegram + Temporal Coexistence
- **What it proves**: Bot polling/webhook lifecycle and Temporal worker can run together without event loop ownership conflicts.
- **Scope** (1.5-3h):
- Build minimal app with one Telegram command (`/ping`) that signals a Temporal workflow and replies `pong`.
- Run both in one process with explicit startup/shutdown (no blocking convenience runner conflicts).
- **Success criteria**:
- 20 `/ping` messages sent over ~10 minutes, 0 deadlocks, 0 dropped replies, clean Ctrl+C shutdown.
- **What you learn if it fails**:
- Need split-process architecture early (bot process + worker process) or different lifecycle wiring.
- **Dependencies**: First; all Telegram-facing bullets depend on this.

## TB2 — Telegram Idempotency + Ordering Spike
- **What it proves**: Duplicate/out-of-order Telegram updates won’t corrupt conversation state.
- **Scope** (2-4h):
- Capture 30 real/simulated updates; replay with deliberate duplicates and shuffled order.
- Add minimal dedupe key strategy (`update_id`/message idempotency key) in signal envelope.
- **Success criteria**:
- No duplicate assistant replies; conversation state remains consistent after replay.
- **What you learn if it fails**:
- Need stronger message envelope contract and per-session serialization gate before broader build.
- **Dependencies**: After TB1.

## TB3 — OpenRouter Activity Resilience (Non-Streaming First)
- **What it proves**: Real model calls through Temporal activity are stable enough for MVP latency/error profile.
- **Scope** (2-3h):
- Implement one `call_llm` activity using OpenRouter.
- Run 25 calls with forced fault injection scenarios (timeout, 429 retry, synthetic 500 path).
- Log latency + retries + final outcome.
- **Success criteria**:
- >=95% successful completion with retry policy; p95 end-to-end activity latency under 8s in normal path.
- **What you learn if it fails**:
- Need stricter fallback chain or direct-provider escape hatch before committing to OpenRouter-only path.
- **Dependencies**: Can run after TB1; independent from TB2.

## TB4 — OpenRouter Streaming + Transcript Hygiene Spike
- **What it proves**: Streaming and transcript validation won’t break turn execution (including orphan reasoning guard).
- **Scope** (1-3h):
- Add optional streaming mode for one model.
- Validate no orphan reasoning items before send (rule from `openai-reasoning-items-reference.md`).
- Test 10 streamed turns including one interrupted stream.
- **Success criteria**:
- 10/10 turns end in valid final reply or clean recoverable error; no malformed replay payloads.
- **What you learn if it fails**:
- Ship non-streaming first and isolate streaming behind feature flag.
- **Dependencies**: After TB3.

## TB5 — Mem0 Fact Extraction Quality (Small Gold Set)
- **What it proves**: Mem0 OSS is usable for high-value memory without major hallucinated/low-value facts.
- **Scope** (2-4h):
- Prepare 10 short conversation snippets with expected facts (work prefs, commitments, project facts).
- Run extraction + store + retrieve queries.
- Score precision/recall manually.
- **Success criteria**:
- Precision >=0.8 and recall >=0.7 on expected facts; retrieval returns correct fact in top 3 for >=8/10 queries.
- **What you learn if it fails**:
- Keep only file-based memory for MVP or add stricter confidence/provenance filter before writing to Mem0.
- **Dependencies**: Independent of TB1-4; can run in parallel after TB3 starts.

## TB6 — Cheap Model Routing Classifier Eval
- **What it proves**: Intern-tier classifier is reliable enough to control cost without routing critical tasks too low.
- **Scope** (1-3h):
- Build 40 labeled prompts across tiers (intern/junior/senior/executive).
- Run chosen cheap model classifier + confidence score.
- Compute confusion matrix.
- **Success criteria**:
- Overall accuracy >=80%; high-risk misroutes (should be senior/executive but predicted intern/junior) <=10%.
- **What you learn if it fails**:
- Use rule-based + LLM hybrid routing initially, or default-up one tier for safety.
- **Dependencies**: Can run after TB3; independent of Telegram runtime.

## TB7 — Promise Detection Reliability Eval
- **What it proves**: Commitment detection can trigger FollowUp workflows without annoying false positives.
- **Scope** (1-2h):
- Build 30 utterance dataset: explicit commitments, soft language, non-commitment chatter.
- Run detector model and score precision/recall.
- **Success criteria**:
- Precision >=0.85, recall >=0.75.
- **What you learn if it fails**:
- Restrict trigger to explicit linguistic patterns first, add confirmation step before scheduling reminders.
- **Dependencies**: Can run with TB6.

## TB8 — Tool Execution Safety Envelope (Exec)
- **What it proves**: `exec` can be constrained enough for personal use without runaway or opaque failures.
- **Scope** (2-4h):
- Implement minimal policy: command allowlist, path scope, timeout, output cap.
- Run 15 commands: allowed, blocked, timeout, non-zero exit.
- Verify error mapping to remediation-friendly categories.
- **Success criteria**:
- 100% blocked commands denied with clear reason; long-running command always times out cleanly; no process leaks.
- **What you learn if it fails**:
- Defer generic `exec`; expose only high-level safe tools for MVP.
- **Dependencies**: After TB1 (if tested via bot) or independent via local activity harness.

## TB9 — Durable Follow-Up Through Restart/Sleep
- **What it proves**: Promise Keeper core value actually survives downtime (with SQLite persistence) and recovers correctly.
- **Scope** (1.5-3h):
- Schedule 3 short reminders (2-5 min).
- Restart Temporal server mid-wait; optionally sleep machine briefly.
- Confirm reminders fire after recovery and are not duplicated.
- **Success criteria**:
- All reminders delivered exactly once post-restart; no lost timers.
- **What you learn if it fails**:
- Local-hosted daily-driver assumption is weak; prioritize VPS Temporal earlier.
- **Dependencies**: After TB1 and TB2.

## TB10 — Two-Bot Transition Coexistence (Mycel + OpenClaw)
- **What it proves**: Parallel transition is practical without user confusion or command collisions.
- **Scope** (1-2h):
- Run both bots against same Telegram user for 30 minutes.
- Define command namespaces (`/m_...` vs `/oc_...`) and notification style.
- **Success criteria**:
- No accidental double handling of same intent; user can intentionally route to either bot.
- **What you learn if it fails**:
- Need hard traffic split strategy (time window or command-based gate) before transition.
- **Dependencies**: After TB1.

---

## 3) What NOT to Tracer Bullet

- **Python vs bridge architecture choice**: Already decided and empirically validated by both PoCs.
- **Temporal fundamental viability**: Already proven by passing PoCs (workflow turn, ContinueAsNew, scheduled activity).
- **Big graph memory (Zettelkasten full layer) before memory quality**: Premature; deep-dive flags this as likely complexity trap.
- **Full production hosting choice right now (Cloud vs VPS vs local)**: Hosting deep-dive already provides enough decision guidance for current phase; run local SQLite first.
- **Phase 3 features (voice, webhooks, self-mod, subagents)**: Not risk-critical for must-haves (on-the-go Telegram + work/idea management).
- **Polish docs/prompt aesthetics**: Does not de-risk architecture assumptions.

---

## 4) Execution Strategy

## Parallelization
- **Can run in parallel**:
- TB3 (OpenRouter), TB5 (Mem0), TB6 (routing), TB7 (promise detection).
- **Should stay sequential**:
- TB1 -> TB2 -> TB9 (runtime correctness chain).
- TB3 -> TB4 (streaming depends on base adapter).
- TB10 after TB1.

## Suggested batching for a busy schedule
- **Batch A (single evening, 4-6h)**: TB1 + TB2.
- **Batch B (single evening, 4-6h)**: TB3 + TB4.
- **Batch C (single evening, 4-6h)**: TB5 + TB6 + TB7 (mostly eval harness work).
- **Batch D (single evening, 3-5h)**: TB8 + TB9.
- **Batch E (quick session, 1-2h)**: TB10.

## Total estimated investment
- Roughly **16-25 hours** total, split across 4-5 focused sessions.

## Decision unlocks by tracer bullet
- TB1 unlocks: single-process vs split-process runtime choice.
- TB2 unlocks: message contract and session serialization design.
- TB3/TB4 unlock: OpenRouter-only adapter confidence vs fallback/bypass need.
- TB5 unlocks: Mem0-in-MVP vs file-memory-first fallback.
- TB6 unlocks: LLM routing vs rule-based/hybrid routing for MVP.
- TB7 unlocks: auto FollowUp creation vs explicit-confirmation trigger.
- TB8 unlocks: generic exec tool in MVP vs constrained tool set.
- TB9 unlocks: local Temporal daily-driver viability vs early VPS move.
- TB10 unlocks: parallel bot transition mechanics.

---

## 5) Kill Criteria (When to Reconsider Design Choices)

## Temporal
- Reconsider Temporal-centric architecture if TB1/TB2/TB9 show persistent event-loop conflicts, ordering bugs, or timer reliability failures that require heavy workaround complexity.
- Practical threshold: if after 2 focused attempts you still cannot get stable single-user messaging semantics, reduce Temporal scope (Temporal for reminders only) while simplifying conversation loop.

## Mem0
- Reconsider Mem0 for MVP if TB5 cannot hit minimum quality (precision >=0.8, recall >=0.7) or retrieval is unreliable without heavy custom patching.
- Fallback: file-first memory + lightweight custom extraction/retrieval, revisit Mem0 later.

## OpenRouter
- Reconsider OpenRouter-first adapter if TB3/TB4 show frequent unrecoverable failures, unstable latencies, or streaming fragility that breaks UX.
- Fallback: keep OpenRouter primary but add direct-provider emergency adapters behind a flag.

## Model Routing (cheap classifier)
- Reconsider LLM-driven routing if TB6 misses accuracy/safety targets, especially high-risk down-tier misroutes.
- Fallback: rules-first routing + manual overrides + conservative default-upgrade.

---

## Recommended First 72-Hour Checklist
- Day 1: TB1 + TB2
- Day 2: TB3 + TB4
- Day 3: TB5 + TB6 + TB7
- Day 4: TB8 + TB9
- Day 5 (short): TB10 and transition decision

This sequence maximizes learning-per-hour while protecting Pasha's limited build time and preserving optionality for the two-bot transition.
