# TB11b Learnings (Hard Verification with Real Context)

## Snapshot
- Dataset: 20 real-context prompts (memory synthesis, multi-doc reasoning, judgment/tone, adversarial).
- Intern model: `google/gemini-2.5-flash-lite-preview-06-17` (fallback to current compatible Lite ID when unavailable).
- Senior model: `google/gemini-2.5-flash`.
- Judge model: `google/gemini-2.5-flash`.

## Key Results
- Intern accuracy: 55.0% (11/20).
- Senior baseline accuracy: 70.0% (14/20).
- Catch rate: 77.8% (7/9 bad intern outputs caught).
- False escalation rate: 9.1% (1/11 correct intern outputs escalated).
- Cost ratio (Path B intern+verify+escalations vs Path A senior-only): 218.7%.

## Success Criteria Check
- Catch rate >80%: FAIL (77.8%).
- Cost <50% of senior-only: FAIL (218.7%).
- False escalation <15%: PASS (9.1%).

## Intern Accuracy vs TB11 Trivia
- TB11 trivia intern result (provided baseline): 95%.
- TB11b real-context intern result: 55%.
- Interpretation: real workspace context causes a large drop in cheap-model reliability, especially when answers require synthesis across multiple files and operational nuance.

## Which Categories Broke the Intern
- `multi_document_reasoning`: 0/5 (worst category). Frequent failure was shallow synthesis and missing cross-file constraints.
- `judgment_tone`: 3/5. Main misses were wellbeing-boundary adherence (late-night pushback, unsolicited outreach rule).
- `memory_recall_synthesis`: 4/5 after longer context injection, but one key miss remained on hosting nuance.
- `tricky_adversarial`: 4/5. Generally robust, but one false-premise trap slipped (`Mem0 passed with flying colors`).

## Is Verification More Valuable for Context-Heavy Tasks?
- Yes for safety, mixed for economics.
- Verification caught most bad intern outputs (77.8%) and kept false escalations low (9.1%).
- But current design is not cost-effective because senior verification on every prompt plus escalations costs more than senior-only generation.
- Net: verification adds quality protection, but this configuration is not yet a cost-saving layer.

## Security and Hallucination Findings
- Security: intern correctly refused API key exfiltration prompt.
- Missing-context hallucination: intern correctly handled missing Feb 15 context by not fabricating details.
- Remaining hallucination risk: some incorrect confident synthesis remained in multi-document prompts.

## Updated MVP Recommendation
- Do not ship this exact “always verify everything” configuration for cost-sensitive MVP.
- Keep routing + verification, but gate verification selectively:
  - Auto-verify only high-risk categories (multi-doc synthesis, commitments, sensitive policy/security answers).
  - Allow low-risk direct intern responses when confidence is high and prompt class is simple.
  - Escalate quickly on contradiction signals, missing-context uncertainty, or policy-sensitive requests.
- Expand evaluator strictness for multi-doc reasoning and add targeted training/examples for cross-file synthesis.
- Keep adversarial and security checks in the eval suite; they are high-value and currently effective.
