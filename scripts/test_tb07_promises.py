#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tb07.detector import DEFAULT_MODEL, PromiseDetection, detect_promises


def safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def load_dataset(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data["items"]


def evaluate(rows: list[dict], model: str) -> dict:
    tp = fp = fn = tn = 0
    per_category = defaultdict(list)
    false_positives = []
    false_negatives = []
    source_counts = defaultdict(int)

    for row in rows:
        detection: PromiseDetection = detect_promises(row["utterance"], model=model)
        pred = detection.is_commitment
        expected = bool(row["expected_is_commitment"])

        source_counts[detection.source] += 1

        if expected and pred:
            tp += 1
        elif not expected and pred:
            fp += 1
            false_positives.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "utterance": row["utterance"],
                    "confidence": detection.confidence,
                    "extracted_text": detection.extracted_text,
                }
            )
        elif expected and not pred:
            fn += 1
            false_negatives.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "utterance": row["utterance"],
                    "confidence": detection.confidence,
                }
            )
        else:
            tn += 1

        per_category[row["category"]].append(
            {
                "expected": expected,
                "pred": pred,
                "confidence": detection.confidence,
            }
        )

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)

    category_breakdown = {}
    for category, items in per_category.items():
        total = len(items)
        correct = sum(1 for item in items if item["expected"] == item["pred"])
        triggered = sum(1 for item in items if item["pred"])
        avg_conf = mean(item["confidence"] for item in items)
        category_breakdown[category] = {
            "total": total,
            "accuracy": safe_div(correct, total),
            "trigger_rate": safe_div(triggered, total),
            "avg_confidence": avg_conf,
        }

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "category_breakdown": category_breakdown,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "source_counts": dict(source_counts),
    }


def print_results(results: dict) -> None:
    print("TB7 Promise Detection Evaluation")
    print("=" * 40)
    print(f"Confusion matrix: TP={results['tp']} FP={results['fp']} FN={results['fn']} TN={results['tn']}")
    print(f"Precision: {results['precision']:.3f}")
    print(f"Recall:    {results['recall']:.3f}")
    print(f"F1:        {results['f1']:.3f}")
    print(f"Detector source counts: {results['source_counts']}")

    print("\nPer-category breakdown")
    for category in sorted(results["category_breakdown"]):
        info = results["category_breakdown"][category]
        print(
            f"- {category}: total={info['total']} accuracy={info['accuracy']:.3f} "
            f"trigger_rate={info['trigger_rate']:.3f} avg_conf={info['avg_confidence']:.3f}"
        )

    print("\nFalse positives")
    if results["false_positives"]:
        for fp in results["false_positives"]:
            print(
                f"- #{fp['id']} [{fp['category']}] conf={fp['confidence']:.2f} "
                f"text={fp['utterance']!r} extracted={fp['extracted_text']!r}"
            )
    else:
        print("- none")

    print("\nFalse negatives")
    if results["false_negatives"]:
        for fn in results["false_negatives"]:
            print(
                f"- #{fn['id']} [{fn['category']}] conf={fn['confidence']:.2f} "
                f"text={fn['utterance']!r}"
            )
    else:
        print("- none")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TB7 promise detection evaluation")
    parser.add_argument(
        "--dataset",
        default=str(REPO_ROOT / "data" / "tb07_promise_dataset.json"),
        help="Path to dataset JSON",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}", file=sys.stderr)
        return 1

    rows = load_dataset(dataset_path)
    if len(rows) != 30:
        print(f"Expected 30 rows, found {len(rows)}", file=sys.stderr)
        return 1

    results = evaluate(rows, model=args.model)
    print_results(results)

    precision_ok = results["precision"] >= 0.85
    recall_ok = results["recall"] >= 0.75
    print("\nSuccess criteria")
    print(f"- Precision >= 0.85: {'PASS' if precision_ok else 'FAIL'}")
    print(f"- Recall >= 0.75:    {'PASS' if recall_ok else 'FAIL'}")

    return 0 if precision_ok and recall_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
