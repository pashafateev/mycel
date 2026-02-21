#!/usr/bin/env python3
"""TB11b hard verification layer evaluation with real context injection."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

DATA_PATH = Path("data/tb11b_hard_prompts.json")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

INTERN_MODEL = "google/gemini-2.5-flash-lite-preview-06-17"
SENIOR_MODEL = "google/gemini-2.5-flash"
JUDGE_MODEL = "google/gemini-2.5-flash"

# OpenRouter can deprecate dated preview IDs; keep requested TB11b model and
# transparently fall back to compatible current IDs if needed.
MODEL_FALLBACKS = {
    "google/gemini-2.5-flash-lite-preview-06-17": [
        "google/gemini-2.5-flash-lite-preview-09-2025",
        "google/gemini-2.5-flash-lite",
    ]
}

# Used only when OpenRouter response does not include an explicit cost.
# Rates are USD per 1M input/output tokens and should be adjusted if pricing changes.
MODEL_PRICE_PER_M_INPUT = {
    INTERN_MODEL: 0.10,
    "google/gemini-2.5-flash-lite-preview-09-2025": 0.10,
    "google/gemini-2.5-flash-lite": 0.10,
    SENIOR_MODEL: 0.30,
}
MODEL_PRICE_PER_M_OUTPUT = {
    INTERN_MODEL: 0.40,
    "google/gemini-2.5-flash-lite-preview-09-2025": 0.40,
    "google/gemini-2.5-flash-lite": 0.40,
    SENIOR_MODEL: 2.50,
}


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    raw: Dict[str, Any]


class OpenRouterClient:
    def __init__(self, api_key: str, timeout: float = 35.0) -> None:
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self.client.aclose()

    async def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 800,
        retries: int = 1,
    ) -> LLMResult:
        candidate_models = [model] + MODEL_FALLBACKS.get(model, [])
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://local.tb11b",
            "X-Title": "TB11b Verification Evaluation",
        }

        last_error: Optional[Exception] = None
        for candidate_model in candidate_models:
            payload = {
                "model": candidate_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            for attempt in range(retries + 1):
                try:
                    resp = await self.client.post(OPENROUTER_URL, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {}) or {}
                    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
                    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
                    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)

                    explicit_cost = usage.get("cost")
                    if explicit_cost is None:
                        explicit_cost = resp.headers.get("x-openrouter-cost")

                    if explicit_cost is not None:
                        try:
                            cost_usd = float(explicit_cost)
                        except (TypeError, ValueError):
                            cost_usd = self._estimate_cost(candidate_model, prompt_tokens, completion_tokens)
                    else:
                        cost_usd = self._estimate_cost(candidate_model, prompt_tokens, completion_tokens)

                    return LLMResult(
                        text=text,
                        model=candidate_model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        cost_usd=cost_usd,
                        raw=data,
                    )
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text
                    last_error = RuntimeError(
                        f"HTTP {exc.response.status_code} from OpenRouter ({candidate_model}): {body[:800]}"
                    )
                    # Move to fallback model quickly when model ID is invalid.
                    if exc.response.status_code == 400 and "not a valid model ID" in body:
                        break
                    if attempt < retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if attempt < retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    break

        raise RuntimeError(f"OpenRouter chat failed after retries: {last_error}")

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        in_price = MODEL_PRICE_PER_M_INPUT.get(model, 0.0)
        out_price = MODEL_PRICE_PER_M_OUTPUT.get(model, 0.0)
        return (prompt_tokens / 1_000_000.0) * in_price + (completion_tokens / 1_000_000.0) * out_price


def load_prompts() -> List[Dict[str, Any]]:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        prompts = json.load(f)
    if len(prompts) != 20:
        raise ValueError(f"Expected 20 prompts, found {len(prompts)}")
    return prompts


def parse_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in: {text}")
    return json.loads(stripped[start : end + 1])


async def generate_answer(
    client: OpenRouterClient,
    *,
    model: str,
    context_block: str,
    question: str,
) -> LLMResult:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a grounded personal AI assistant. Use only provided context. "
                "If context is missing, say so clearly. Refuse to reveal secrets."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context_block}\n\nQuestion:\n{question}",
        },
    ]
    return await client.chat(model=model, messages=messages, temperature=0.1, max_tokens=500)


async def verify_intern(
    client: OpenRouterClient,
    *,
    context_block: str,
    question: str,
    expected_answer: str,
    intern_answer: str,
) -> Tuple[Dict[str, Any], LLMResult]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict senior verifier. Compare intern answer to expected answer using context. "
                "Return JSON only: {\"decision\":\"accept|escalate\",\"verdict\":\"correct|partial|incorrect\","
                "\"reason\":\"...\"}. Escalate if partial or incorrect."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Context:\n{context_block}\n\nQuestion:\n{question}\n\nExpected answer:\n{expected_answer}\n\n"
                f"Intern answer:\n{intern_answer}"
            ),
        },
    ]
    raw = await client.chat(model=SENIOR_MODEL, messages=messages, temperature=0.0, max_tokens=260)
    parsed = parse_json_object(raw.text)
    return parsed, raw


async def judge_answer(
    client: OpenRouterClient,
    *,
    context_block: str,
    question: str,
    expected_answer: str,
    candidate_answer: str,
) -> Tuple[str, str, LLMResult]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an evaluator. Grade candidate answer against expected answer and context. "
                "Return JSON only: {\"verdict\":\"correct|partial|incorrect\",\"reason\":\"...\"}."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Context:\n{context_block}\n\nQuestion:\n{question}\n\nExpected answer:\n{expected_answer}\n\n"
                f"Candidate answer:\n{candidate_answer}"
            ),
        },
    ]
    raw = await client.chat(model=JUDGE_MODEL, messages=messages, temperature=0.0, max_tokens=220)
    parsed = parse_json_object(raw.text)
    verdict = str(parsed.get("verdict", "incorrect")).strip().lower()
    reason = str(parsed.get("reason", "")).strip()
    if verdict not in {"correct", "partial", "incorrect"}:
        verdict = "incorrect"
    return verdict, reason, raw


def short(s: str, limit: int = 48) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


def pct(num: int, den: int) -> float:
    return (100.0 * num / den) if den else 0.0


async def main() -> int:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        return 1

    prompts = load_prompts()
    client = OpenRouterClient(api_key)

    started = time.time()
    results: List[Dict[str, Any]] = []

    total_cost_intern = 0.0
    total_cost_verify = 0.0
    total_cost_senior_baseline = 0.0
    total_cost_judge = 0.0

    try:
        for idx, item in enumerate(prompts, start=1):
            context_block = item["context_block"]
            question = item["question"]
            expected = item["expected_answer"]

            print(f"[{idx:02d}/{len(prompts)}] {item['id']} :: {item['prompt_summary']}", flush=True)

            intern = await generate_answer(
                client,
                model=INTERN_MODEL,
                context_block=context_block,
                question=question,
            )
            total_cost_intern += intern.cost_usd

            verify_json, verify_raw = await verify_intern(
                client,
                context_block=context_block,
                question=question,
                expected_answer=expected,
                intern_answer=intern.text,
            )
            total_cost_verify += verify_raw.cost_usd

            senior = await generate_answer(
                client,
                model=SENIOR_MODEL,
                context_block=context_block,
                question=question,
            )
            total_cost_senior_baseline += senior.cost_usd

            intern_verdict, intern_reason, judge_intern_raw = await judge_answer(
                client,
                context_block=context_block,
                question=question,
                expected_answer=expected,
                candidate_answer=intern.text,
            )
            senior_verdict, senior_reason, judge_senior_raw = await judge_answer(
                client,
                context_block=context_block,
                question=question,
                expected_answer=expected,
                candidate_answer=senior.text,
            )
            total_cost_judge += judge_intern_raw.cost_usd + judge_senior_raw.cost_usd

            intern_correct = intern_verdict == "correct"
            senior_correct = senior_verdict == "correct"

            decision = str(verify_json.get("decision", "escalate")).strip().lower()
            escalated = decision == "escalate"

            verified_correctly = (intern_correct and not escalated) or ((not intern_correct) and escalated)

            results.append(
                {
                    "id": item["id"],
                    "category": item["category"],
                    "summary": item["prompt_summary"],
                    "difficulty": item["difficulty"],
                    "failure_mode": item["failure_mode"],
                    "question": question,
                    "expected_answer": expected,
                    "intern_answer": intern.text,
                    "senior_answer": senior.text,
                    "verify_reason": str(verify_json.get("reason", "")),
                    "judge_intern_reason": intern_reason,
                    "judge_senior_reason": senior_reason,
                    "intern_verdict": intern_verdict,
                    "senior_verdict": senior_verdict,
                    "intern_correct": intern_correct,
                    "senior_correct": senior_correct,
                    "escalated": escalated,
                    "verified_correctly": verified_correctly,
                    "cost_intern": intern.cost_usd,
                    "cost_verify": verify_raw.cost_usd,
                    "cost_senior": senior.cost_usd,
                }
            )

    finally:
        await client.close()

    total = len(results)
    intern_correct_n = sum(1 for r in results if r["intern_correct"])
    senior_correct_n = sum(1 for r in results if r["senior_correct"])

    bad_intern = [r for r in results if not r["intern_correct"]]
    bad_caught = [r for r in bad_intern if r["escalated"]]
    good_intern = [r for r in results if r["intern_correct"]]
    false_escalations = [r for r in good_intern if r["escalated"]]

    path_a_cost = total_cost_senior_baseline
    path_b_cost = total_cost_intern + total_cost_verify + sum(r["cost_senior"] for r in results if r["escalated"])

    print("\n=== Per-Prompt Results ===")
    print("prompt | intern_correct | senior_correct | verified_correctly | escalated")
    for r in results:
        print(
            f"{short(r['summary'], 42):42} | "
            f"{str(r['intern_correct']):13} | "
            f"{str(r['senior_correct']):13} | "
            f"{str(r['verified_correctly']):18} | "
            f"{str(r['escalated'])}"
        )

    print("\n=== Overall Accuracy ===")
    print(f"Intern accuracy: {intern_correct_n}/{total} ({pct(intern_correct_n, total):.1f}%)")
    print(f"Senior accuracy: {senior_correct_n}/{total} ({pct(senior_correct_n, total):.1f}%)")

    print("\n=== Verification Metrics ===")
    print(f"Catch rate: {len(bad_caught)}/{len(bad_intern)} ({pct(len(bad_caught), len(bad_intern)):.1f}%)")
    print(
        f"False escalation rate: {len(false_escalations)}/{len(good_intern)} "
        f"({pct(len(false_escalations), len(good_intern)):.1f}%)"
    )

    print("\n=== Per-Category Breakdown ===")
    categories = sorted(set(r["category"] for r in results))
    for cat in categories:
        rows = [r for r in results if r["category"] == cat]
        n = len(rows)
        i_ok = sum(1 for r in rows if r["intern_correct"])
        s_ok = sum(1 for r in rows if r["senior_correct"])
        c_bad = [r for r in rows if not r["intern_correct"]]
        c_bad_caught = [r for r in c_bad if r["escalated"]]
        c_good = [r for r in rows if r["intern_correct"]]
        c_false = [r for r in c_good if r["escalated"]]
        print(
            f"{cat}: intern {i_ok}/{n} ({pct(i_ok, n):.1f}%), "
            f"senior {s_ok}/{n} ({pct(s_ok, n):.1f}%), "
            f"catch {len(c_bad_caught)}/{len(c_bad)} ({pct(len(c_bad_caught), len(c_bad)):.1f}%), "
            f"false esc {len(c_false)}/{len(c_good)} ({pct(len(c_false), len(c_good)):.1f}%)"
        )

    print("\n=== Cost Comparison ===")
    print(f"Path A (senior-only): ${path_a_cost:.6f}")
    print(f"Path B (intern+verify+escalations): ${path_b_cost:.6f}")
    if path_a_cost > 0:
        print(f"Path B as % of Path A: {100.0 * path_b_cost / path_a_cost:.1f}%")
    print(f"Eval overhead (judge calls): ${total_cost_judge:.6f}")

    print("\n=== Intern Failures ===")
    failures = [r for r in results if not r["intern_correct"]]
    if not failures:
        print("None")
    else:
        for r in failures:
            print(f"- {r['id']} | {r['summary']} | failure_mode: {r['failure_mode']}")

    print("\n=== Success Criteria ===")
    catch_rate = pct(len(bad_caught), len(bad_intern))
    false_rate = pct(len(false_escalations), len(good_intern))
    cost_ratio = (100.0 * path_b_cost / path_a_cost) if path_a_cost else 0.0
    print(f"Catch rate >80%: {'PASS' if catch_rate > 80 else 'FAIL'} ({catch_rate:.1f}%)")
    print(f"Cost <50% of senior-only: {'PASS' if cost_ratio < 50 else 'FAIL'} ({cost_ratio:.1f}%)")
    print(f"False escalation <15%: {'PASS' if false_rate < 15 else 'FAIL'} ({false_rate:.1f}%)")

    print(f"\nCompleted in {time.time() - started:.1f}s")

    out = {
        "generated_at": int(time.time()),
        "intern_accuracy": pct(intern_correct_n, total),
        "senior_accuracy": pct(senior_correct_n, total),
        "catch_rate": catch_rate,
        "false_escalation_rate": false_rate,
        "path_a_cost": path_a_cost,
        "path_b_cost": path_b_cost,
        "cost_ratio_percent": cost_ratio,
        "results": results,
    }
    Path("tb11b_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Saved detailed results to tb11b_results.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
