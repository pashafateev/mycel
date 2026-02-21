#!/usr/bin/env python3
import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tb11.pipeline import intern_generate, senior_generate, senior_verify


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_numbers(text: str) -> List[float]:
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    return [float(n) for n in nums]


def keyword_score(expected: str, actual: str) -> float:
    exp_words = [w for w in re.findall(r"[a-zA-Z0-9]+", expected.lower()) if len(w) > 2]
    if not exp_words:
        return 1.0
    exp_unique = set(exp_words)
    act = actual.lower()
    hits = sum(1 for w in exp_unique if w in act)
    return hits / max(1, len(exp_unique))


def evaluate_response(prompt: str, expected: str, actual: str, category: str) -> bool:
    exp_n = normalize(expected)
    act_n = normalize(actual)

    if not act_n:
        return False

    # Strict factual checks where exact target is known.
    if "capital of france" in prompt.lower():
        return "paris" in act_n
    if "72" in prompt.lower() and ("fahrenheit" in prompt.lower() or "°f" in prompt.lower()):
        nums = extract_numbers(actual)
        return any(abs(x - 22.2) <= 0.5 for x in nums)
    if "python 3" in prompt.lower() and "year" in prompt.lower():
        return "2008" in act_n
    if "bytes in a kilobyte" in prompt.lower():
        return ("1000" in act_n) or ("1,000" in actual) or ("1024" in act_n)
    if "http stand" in prompt.lower():
        return "hypertext" in act_n and "transfer" in act_n and "protocol" in act_n

    # Code task checks.
    if "reverse a string" in prompt.lower():
        return "def" in act_n and ("[::-1]" in actual or "reversed" in act_n)
    if "find the bug" in prompt.lower() and "range(1, n)" in prompt:
        return "off-by-one" in act_n or "n + 1" in act_n or "range(1, n+1)" in act_n
    if "duplicate emails" in prompt.lower():
        return (
            "group by" in act_n
            and "having" in act_n
            and ("count(*)" in act_n or "count ( * )" in act_n)
        )
    if "regex match" in prompt.lower() and "^[a-z]{2,4}$" in prompt:
        return "lowercase" in act_n and ("2" in act_n and "4" in act_n)
    if "difference between == and is" in prompt.lower():
        return "value" in act_n and "identity" in act_n

    # Reasoning numeric checks.
    if "all meetings are on tuesday" in prompt.lower():
        return "tuesday" in act_n and ("tomorrow" in act_n or "next" in act_n)
    if "average speed" in prompt.lower():
        nums = extract_numbers(actual)
        return any(abs(x - 60.0) <= 0.5 for x in nums)
    if "coupon" in prompt.lower() and "sales tax" in prompt.lower():
        nums = extract_numbers(actual)
        return any(abs(x - 14.04) <= 0.05 for x in nums)

    # Judgment/comparison/summarization: require decent keyword coverage and handle negation-sensitive case.
    if "project was not approved" in prompt.lower():
        has_negation = (
            "not approved" in act_n
            or "was not approved" in act_n
            or "rejected" in act_n
            or "denied" in act_n
        )
        return has_negation and (
            "legal" in act_n or "compliance" in act_n or "risk" in act_n
        )

    if category == "summarization":
        # Summaries vary in wording; favor semantic keyword overlap over exact phrasing.
        return keyword_score(expected, actual) >= 0.30

    # General fallback heuristic.
    score = keyword_score(expected, actual)
    return score >= 0.45


def is_flagged(verdict: Dict[str, Any]) -> bool:
    return (
        verdict["should_escalate"] == "yes"
        or verdict["correctness"] != "yes"
        or verdict["complete"] != "yes"
    )


def pct(numer: int, denom: int) -> float:
    if denom == 0:
        return 0.0
    return (numer / denom) * 100.0


def print_cost_line(name: str, totals: Dict[str, float]) -> None:
    print(
        f"  {name:<26} tokens={int(totals['tokens']):>6}  "
        f"cost=${totals['cost']:.6f}  latency_ms={totals['latency_ms']:.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "data" / "tb11_verification_dataset.json"),
        help="Path to dataset JSON",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional limit of prompts")
    parser.add_argument(
        "--out-json",
        default="",
        help="Optional path to write row-level evaluation JSON",
    )
    args = parser.parse_args()

    dataset = load_dataset(Path(args.dataset))
    if args.limit > 0:
        dataset = dataset[: args.limit]

    rows: List[Dict[str, Any]] = []

    for i, item in enumerate(dataset, start=1):
        prompt = item["prompt"]
        expected = item["expected_answer"]
        category = item["category"]

        print(f"[{i:02d}/{len(dataset)}] {item['id']} ({category})")
        intern = intern_generate(prompt)
        verify = senior_verify(prompt, intern.text, expected)
        senior = senior_generate(prompt)

        actual_intern_good = evaluate_response(prompt, expected, intern.text, category)
        actual_senior_good = evaluate_response(prompt, expected, senior.text, category)

        verdict = {
            "correctness": verify.verdict.correctness,
            "complete": verify.verdict.complete,
            "should_escalate": verify.verdict.should_escalate,
            "confidence": verify.verdict.confidence,
            "explanation": verify.verdict.explanation,
        }
        flagged = is_flagged(verdict)

        final_response = senior.text if flagged else intern.text
        actual_final_good = evaluate_response(prompt, expected, final_response, category)

        rows.append(
            {
                "id": item["id"],
                "category": category,
                "difficulty": item["difficulty"],
                "prompt": prompt,
                "expected": expected,
                "intern": intern,
                "verify": verify,
                "senior": senior,
                "actual_intern_good": actual_intern_good,
                "actual_senior_good": actual_senior_good,
                "actual_final_good": actual_final_good,
                "flagged": flagged,
            }
        )

    total = len(rows)
    bad_intern = sum(1 for r in rows if not r["actual_intern_good"])
    good_intern = sum(1 for r in rows if r["actual_intern_good"])

    caught_bad = sum(1 for r in rows if (not r["actual_intern_good"] and r["flagged"]))
    false_escalations = sum(1 for r in rows if (r["actual_intern_good"] and r["flagged"]))

    catch_rate = pct(caught_bad, bad_intern)
    false_escalation_rate = pct(false_escalations, good_intern)

    intern_acc = pct(sum(1 for r in rows if r["actual_intern_good"]), total)
    senior_acc = pct(sum(1 for r in rows if r["actual_senior_good"]), total)
    final_acc = pct(sum(1 for r in rows if r["actual_final_good"]), total)

    path_a = {"tokens": 0.0, "cost": 0.0, "latency_ms": 0.0}
    path_b = {"tokens": 0.0, "cost": 0.0, "latency_ms": 0.0}

    for r in rows:
        path_a["tokens"] += r["senior"].total_tokens
        path_a["cost"] += r["senior"].cost_estimate_usd
        path_a["latency_ms"] += r["senior"].latency_ms

        path_b["tokens"] += r["intern"].total_tokens + r["verify"].total_tokens
        path_b["cost"] += r["intern"].cost_estimate_usd + r["verify"].cost_estimate_usd
        path_b["latency_ms"] += r["intern"].latency_ms + r["verify"].latency_ms

        if r["flagged"]:
            path_b["tokens"] += r["senior"].total_tokens
            path_b["cost"] += r["senior"].cost_estimate_usd
            path_b["latency_ms"] += r["senior"].latency_ms

    category_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        c = category_stats[r["category"]]
        c["count"] += 1
        c["intern_good"] += 1 if r["actual_intern_good"] else 0
        c["senior_good"] += 1 if r["actual_senior_good"] else 0
        c["final_good"] += 1 if r["actual_final_good"] else 0
        c["flagged"] += 1 if r["flagged"] else 0
        c["bad_intern"] += 0 if r["actual_intern_good"] else 1
        c["caught_bad"] += 1 if ((not r["actual_intern_good"]) and r["flagged"]) else 0

    print("\n=== TB11 Verification Results ===")
    print(f"Total prompts: {total}")
    print(f"Intern-bad outputs: {bad_intern}")
    print(f"Catch rate: {catch_rate:.1f}% (target >80%)")
    print(
        f"False escalation rate: {false_escalation_rate:.1f}% "
        f"(target <15%)"
    )

    print("\nQuality comparison")
    print(f"  Intern-only accuracy:        {intern_acc:.1f}%")
    print(f"  Senior-only accuracy:        {senior_acc:.1f}%")
    print(f"  Intern+verification accuracy:{final_acc:.1f}%")

    print("\nCost and latency comparison")
    print_cost_line("Path A senior-only", path_a)
    print_cost_line("Path B intern+verify+redo", path_b)
    if path_a["cost"] > 0:
        savings = (1 - (path_b["cost"] / path_a["cost"])) * 100.0
        print(f"  Cost delta vs A: {savings:.1f}%")
    if path_a["latency_ms"] > 0:
        latency_delta = (path_b["latency_ms"] / path_a["latency_ms"]) * 100.0
        print(f"  Path B latency vs A: {latency_delta:.1f}%")

    print("\nPer-category breakdown")
    for category in sorted(category_stats.keys()):
        c = category_stats[category]
        cnt = int(c["count"])
        c_catch = pct(int(c["caught_bad"]), int(c["bad_intern"]))
        print(
            f"  {category:<14} n={cnt}  "
            f"intern={pct(int(c['intern_good']), cnt):.1f}%  "
            f"senior={pct(int(c['senior_good']), cnt):.1f}%  "
            f"final={pct(int(c['final_good']), cnt):.1f}%  "
            f"flagged={pct(int(c['flagged']), cnt):.1f}%  "
            f"catch={c_catch:.1f}%"
        )

    print("\nTarget checks")
    print(f"  Catch rate >80%: {'PASS' if catch_rate > 80 else 'FAIL'}")
    print(
        "  Cost <50% of senior-only: "
        f"{'PASS' if path_b['cost'] < (0.5 * path_a['cost']) else 'FAIL'}"
    )
    print(
        f"  False escalation <15%: {'PASS' if false_escalation_rate < 15 else 'FAIL'}"
    )

    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        serializable_rows = []
        for r in rows:
            serializable_rows.append(
                {
                    "id": r["id"],
                    "category": r["category"],
                    "difficulty": r["difficulty"],
                    "prompt": r["prompt"],
                    "expected": r["expected"],
                    "intern_text": r["intern"].text,
                    "intern_tokens": r["intern"].total_tokens,
                    "intern_cost_estimate_usd": r["intern"].cost_estimate_usd,
                    "verify_verdict": {
                        "correctness": r["verify"].verdict.correctness,
                        "complete": r["verify"].verdict.complete,
                        "should_escalate": r["verify"].verdict.should_escalate,
                        "confidence": r["verify"].verdict.confidence,
                        "explanation": r["verify"].verdict.explanation,
                    },
                    "verify_tokens": r["verify"].total_tokens,
                    "verify_cost_estimate_usd": r["verify"].cost_estimate_usd,
                    "senior_text": r["senior"].text,
                    "senior_tokens": r["senior"].total_tokens,
                    "senior_cost_estimate_usd": r["senior"].cost_estimate_usd,
                    "actual_intern_good": r["actual_intern_good"],
                    "actual_senior_good": r["actual_senior_good"],
                    "actual_final_good": r["actual_final_good"],
                    "flagged": r["flagged"],
                }
            )
        payload = {
            "summary": {
                "total": total,
                "bad_intern": bad_intern,
                "catch_rate": catch_rate,
                "false_escalation_rate": false_escalation_rate,
                "intern_accuracy": intern_acc,
                "senior_accuracy": senior_acc,
                "final_accuracy": final_acc,
                "path_a": path_a,
                "path_b": path_b,
            },
            "rows": serializable_rows,
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote row-level output: {out_path}")


if __name__ == "__main__":
    main()
