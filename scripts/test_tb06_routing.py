#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tb06 import classify_task  # noqa: E402

TIERS = ["intern", "junior", "senior", "executive"]
SUCCESS_ACCURACY = 0.80
SUCCESS_HIGH_RISK = 0.10


def load_dataset(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if len(data) != 40:
        raise ValueError(f"Expected 40 examples, got {len(data)}")
    return data


def evaluate(dataset: List[Dict[str, str]]) -> Dict[str, object]:
    confusion = {truth: {pred: 0 for pred in TIERS} for truth in TIERS}
    per_tier_totals = defaultdict(int)
    per_tier_correct = defaultdict(int)
    misroutes = []
    method_counts = defaultdict(int)
    errors = []

    for item in dataset:
        truth = item["tier"]
        prompt = item["prompt"]
        result = classify_task(prompt)

        pred = result.tier if result.tier in TIERS else "junior"
        confusion[truth][pred] += 1
        per_tier_totals[truth] += 1
        method_counts[result.method] += 1

        if truth == pred:
            per_tier_correct[truth] += 1

        if result.error:
            errors.append({"id": item["id"], "error": result.error})

        if truth in {"senior", "executive"} and pred in {"intern", "junior"}:
            misroutes.append(
                {
                    "id": item["id"],
                    "truth": truth,
                    "predicted": pred,
                    "confidence": result.confidence,
                    "prompt": prompt,
                }
            )

    total = len(dataset)
    correct = sum(per_tier_correct.values())
    overall_accuracy = correct / total if total else 0.0

    per_tier_accuracy = {}
    for tier in TIERS:
        tier_total = per_tier_totals[tier]
        per_tier_accuracy[tier] = (per_tier_correct[tier] / tier_total) if tier_total else 0.0

    high_risk_sensitive_denominator = sum(per_tier_totals[t] for t in ("senior", "executive"))
    high_risk_rate_sensitive = (
        len(misroutes) / high_risk_sensitive_denominator if high_risk_sensitive_denominator else 0.0
    )
    high_risk_rate_total = len(misroutes) / total if total else 0.0

    return {
        "overall_accuracy": overall_accuracy,
        "per_tier_accuracy": per_tier_accuracy,
        "confusion_matrix": confusion,
        "high_risk_misroutes": misroutes,
        "high_risk_rate_sensitive": high_risk_rate_sensitive,
        "high_risk_rate_total": high_risk_rate_total,
        "method_counts": dict(method_counts),
        "errors": errors,
        "total": total,
    }


def print_report(results: Dict[str, object]) -> None:
    overall_accuracy = results["overall_accuracy"]
    high_risk = results["high_risk_misroutes"]
    high_risk_rate_sensitive = results["high_risk_rate_sensitive"]
    high_risk_rate_total = results["high_risk_rate_total"]

    print("TB6 Routing Classifier Eval")
    print("=" * 40)
    print(f"Dataset size: {results['total']}")
    print(f"Method usage: {results['method_counts']}")
    print(f"Overall accuracy: {overall_accuracy:.2%}")
    print("Per-tier accuracy:")
    for tier, acc in results["per_tier_accuracy"].items():
        print(f"  - {tier:9s}: {acc:.2%}")

    print("\nConfusion matrix (truth x predicted):")
    headers = "          " + " ".join([f"{tier:>10s}" for tier in TIERS])
    print(headers)
    for truth in TIERS:
        row = [results["confusion_matrix"][truth][pred] for pred in TIERS]
        row_text = " ".join([f"{count:10d}" for count in row])
        print(f"{truth:>10s} {row_text}")

    print("\nHigh-risk misroutes (truth senior/executive -> predicted intern/junior):")
    print(f"  Count: {len(high_risk)}")
    print(f"  Rate (of total dataset): {high_risk_rate_total:.2%}")
    print(f"  Rate (of sensitive tiers only): {high_risk_rate_sensitive:.2%}")
    if high_risk:
        for case in high_risk:
            print(
                f"  - {case['id']}: truth={case['truth']} predicted={case['predicted']} "
                f"confidence={case['confidence']:.2f} prompt={case['prompt']}"
            )

    print("\nSuccess criteria:")
    accuracy_ok = overall_accuracy >= SUCCESS_ACCURACY
    high_risk_ok = len(high_risk) <= 4 and high_risk_rate_total <= SUCCESS_HIGH_RISK
    print(f"  - Overall accuracy >= 80%: {'PASS' if accuracy_ok else 'FAIL'}")
    print(f"  - High-risk misroutes <= 10% (<=4): {'PASS' if high_risk_ok else 'FAIL'}")

    if results["errors"]:
        unique_errors = len({entry['error'] for entry in results['errors']})
        print(f"\nClassifier warnings/errors captured: {len(results['errors'])} (unique: {unique_errors})")
        first = results["errors"][0]
        print(f"  Example: {first['id']} -> {first['error']}")


def main() -> int:
    dataset = load_dataset(ROOT / "data" / "tb06_routing_dataset.json")
    results = evaluate(dataset)
    print_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
