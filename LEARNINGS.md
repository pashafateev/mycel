# TB6 Learnings: Model Routing Classifier Eval

## Results
- Dataset: `data/tb06_routing_dataset.json` (40 prompts, 10 per tier)
- Classifier path used: keyword fallback (`OPENROUTER_API_KEY` was not set)
- Overall accuracy: **90.00%** (36/40)
- Per-tier accuracy:
  - intern: 100% (10/10)
  - junior: 100% (10/10)
  - senior: 80% (8/10)
  - executive: 80% (8/10)
- High-risk misroutes (senior/executive routed to intern/junior):
  - 3 cases
  - 7.50% of total dataset (passes <=10% / <=4)
  - 15.00% of sensitive-tier subset (3/20)

## Hardest Tiers To Distinguish
- Senior vs Executive is the hardest boundary.
- Most misses were under-routing ambiguous strategy prompts to `junior` when strong architecture terms were absent.
- Clear architecture/migration keywords were usually routed correctly to `executive`.

## Cost Per Classification Call
- Intern-tier target pricing in `docs/DESIGN.md`: ~$0.10 / 1M tokens.
- Estimated call shape (small classifier prompt): ~350 input + ~20 output = ~370 tokens total.
- Estimated cost per call: `370 / 1_000_000 * $0.10 = $0.000037` (~0.0037 cents).
- Estimated cost for 40 eval calls: ~$0.0015.
- Note: this run used fallback mode, so no paid OpenRouter calls were made.

## Rule-Based vs LLM Routing
- Rule-based is strong for explicit intents (`summarize`, `remind`, `weather`, `architecture`).
- Rule-based is weaker on nuanced senior/executive separation and phrasing variance.
- Cheap LLM classification should outperform keyword matching for semantic ambiguity, but needs API-backed validation.

## Recommendation For MVP Routing
- Use a **hybrid policy**:
  - rules-first for obvious low-risk intern/junior intents,
  - cheap LLM classifier for ambiguous prompts,
  - conservative escalation: if confidence < 0.6, route up one tier.
- Keep a high-risk guardrail: never allow low-confidence routing from senior/executive-like prompts down to intern.
- Next step before production: rerun this exact eval with OpenRouter key enabled and compare confusion + high-risk rates against fallback baseline.
