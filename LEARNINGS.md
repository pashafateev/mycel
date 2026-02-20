# TB7 Learnings: Promise Detection Reliability

## Setup Notes
- Dataset: `data/tb07_promise_dataset.json` (30 utterances, 10 per category)
- Detector: `src/tb07/detector.py`
- Eval runner: `scripts/test_tb07_promises.py`
- Runtime path used in this run: keyword fallback (`OPENROUTER_API_KEY` not set)

## Accuracy Results
- Confusion matrix: TP=10, FP=0, FN=0, TN=20
- Precision: 1.00
- Recall: 1.00
- F1: 1.00

Success criteria:
- Precision >= 0.85: PASS
- Recall >= 0.75: PASS

## Per-Category Behavior
- `explicit_commitment`: trigger rate 1.00, accuracy 1.00
- `soft_ambiguous`: trigger rate 0.00, accuracy 1.00
- `non_commitment`: trigger rate 0.00, accuracy 1.00

Soft/ambiguous handling in current classifier:
- Conservative by design: soft modal language (`should`, `might`, `maybe`, `could`, `I'd like`) does **not** auto-trigger FollowUp.
- This reduces reminder spam risk but can miss rare “softly phrased but real” commitments.

## Hardest Utterance Types
- In this dataset, no misses were observed.
- Expected hardest real-world cases are hybrid statements such as:
  - "Maybe I'll check later" (contains both hedging and intent)
  - "I should follow up tomorrow" (self-directed intent without explicit commitment)
  - "Let’s revisit next week" (group intent, unclear ownership)

## False Positive Analysis
- False positives observed: none.
- User annoyance risk from false positives in this run: low.
- Residual risk remains for real conversations where soft language includes time anchors and action verbs.

## Recommendation
- For now: auto-trigger FollowUp only on explicit commitments.
- For soft/ambiguous statements: require a confirmation step before scheduling ("Do you want me to set a follow-up for this?").
- Next validation step: rerun with OpenRouter path enabled and compare model-vs-fallback precision/recall on expanded examples.
