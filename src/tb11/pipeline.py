import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
INTERN_MODEL = os.getenv(
    "TB11_INTERN_MODEL", "google/gemini-2.5-flash-lite-preview-06-17"
)
SENIOR_MODEL = os.getenv("TB11_SENIOR_MODEL", "google/gemini-2.5-flash")
MODEL_FALLBACKS = {
    "google/gemini-2.5-flash-lite-preview-06-17": ["google/gemini-2.5-flash-lite"],
}

# Approximate defaults ($ per 1M tokens). Override with env vars if needed.
MODEL_PRICING_PER_M = {
    INTERN_MODEL: {
        "input": float(os.getenv("TB11_PRICE_INTERN_INPUT_PER_M", "0.10")),
        "output": float(os.getenv("TB11_PRICE_INTERN_OUTPUT_PER_M", "0.40")),
    },
    SENIOR_MODEL: {
        "input": float(os.getenv("TB11_PRICE_SENIOR_INPUT_PER_M", "0.30")),
        "output": float(os.getenv("TB11_PRICE_SENIOR_OUTPUT_PER_M", "2.50")),
    },
}

VERIFY_SYSTEM_PROMPT = (
    "You are a quality checker. Given the original prompt and a response, evaluate:\n"
    "1. Is the response correct? (yes/partially/no)\n"
    "2. Is it complete? (yes/no)\n"
    "3. Should it be escalated to a more capable model? (yes/no)\n"
    "4. Confidence score (0-1)\n"
    "5. Brief explanation\n\n"
    "Return STRICT JSON with keys: correctness, complete, should_escalate, confidence, explanation."
)


@dataclass
class ModelRun:
    model: str
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    cost_estimate_usd: float
    raw: Dict[str, Any]


@dataclass
class VerifyVerdict:
    correctness: str
    complete: str
    should_escalate: str
    confidence: float
    explanation: str


@dataclass
class VerifyRun:
    verdict: VerifyVerdict
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    cost_estimate_usd: float
    raw: Dict[str, Any]


def _cost_estimate(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = MODEL_PRICING_PER_M.get(model, {"input": 0.0, "output": 0.0})
    in_cost = (prompt_tokens / 1_000_000.0) * pricing["input"]
    out_cost = (completion_tokens / 1_000_000.0) * pricing["output"]
    return in_cost + out_cost


def _extract_usage(payload: Dict[str, Any]) -> Dict[str, int]:
    usage = payload.get("usage", {}) or {}
    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("promptTokens")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("completionTokens")
        or 0
    )
    total_tokens = usage.get("total_tokens") or usage.get("totalTokens") or (
        prompt_tokens + completion_tokens
    )
    return {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(total_tokens),
    }


def _extract_text(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts).strip()
    return str(content).strip()


def _chat(model: str, messages: List[Dict[str, str]], temperature: float = 0.2) -> ModelRun:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in environment")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("TB11_HTTP_REFERER", "https://local.tb11"),
        "X-Title": os.getenv("TB11_X_TITLE", "mycel-tb11-verification"),
    }

    models_to_try = [model] + MODEL_FALLBACKS.get(model, [])
    selected_model = model
    payload: Optional[Dict[str, Any]] = None
    latency_ms = 0.0

    retriable_statuses = {408, 429, 500, 502, 503, 504}
    with httpx.Client(timeout=60.0) as client:
        for candidate in models_to_try:
            for attempt in range(3):
                body = {
                    "model": candidate,
                    "messages": messages,
                    "temperature": temperature,
                }
                start = time.perf_counter()
                response = client.post(OPENROUTER_URL, headers=headers, json=body)
                latency_ms = (time.perf_counter() - start) * 1000.0

                if response.status_code < 400:
                    payload = response.json()
                    selected_model = candidate
                    break

                if (
                    "not a valid model id" in response.text.lower()
                    and candidate != models_to_try[-1]
                ):
                    break

                if response.status_code in retriable_statuses and attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue

                if response.status_code in retriable_statuses and candidate != models_to_try[-1]:
                    break

                raise RuntimeError(
                    f"OpenRouter error {response.status_code} for model {candidate}: {response.text}"
                )
            if payload is not None:
                break

    if payload is None:
        raise RuntimeError(f"No successful response for model candidates: {models_to_try}")

    usage = _extract_usage(payload)
    text = _extract_text(payload)
    cost = _cost_estimate(
        selected_model, usage["prompt_tokens"], usage["completion_tokens"]
    )

    return ModelRun(
        model=selected_model,
        text=text,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        latency_ms=latency_ms,
        cost_estimate_usd=cost,
        raw=payload,
    )


def _parse_verdict(text: str) -> VerifyVerdict:
    text = text.strip()

    parsed: Optional[Dict[str, Any]] = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))

    if not parsed:
        return VerifyVerdict(
            correctness="partially",
            complete="no",
            should_escalate="yes",
            confidence=0.0,
            explanation=f"Verifier returned unparseable output: {text[:300]}",
        )

    def _norm(v: Any, default: str) -> str:
        if v is None:
            return default
        return str(v).strip().lower()

    correctness = _norm(parsed.get("correctness"), "partially")
    if correctness not in {"yes", "partially", "no"}:
        correctness = "partially"

    complete = _norm(parsed.get("complete"), "no")
    if complete not in {"yes", "no"}:
        complete = "no"

    should_escalate = _norm(parsed.get("should_escalate"), "yes")
    if should_escalate not in {"yes", "no"}:
        should_escalate = "yes"

    confidence_raw = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    explanation = str(parsed.get("explanation", "")).strip()

    return VerifyVerdict(
        correctness=correctness,
        complete=complete,
        should_escalate=should_escalate,
        confidence=confidence,
        explanation=explanation,
    )


def intern_generate(prompt: str) -> ModelRun:
    messages = [{"role": "user", "content": prompt}]
    return _chat(INTERN_MODEL, messages, temperature=0.2)


def senior_generate(prompt: str) -> ModelRun:
    messages = [{"role": "user", "content": prompt}]
    return _chat(SENIOR_MODEL, messages, temperature=0.2)


def senior_verify(prompt: str, intern_response: str, expected_answer: str) -> VerifyRun:
    user_content = (
        f"Original prompt:\n{prompt}\n\n"
        f"Intern response:\n{intern_response}\n\n"
        f"Expected answer (gold standard):\n{expected_answer}\n"
    )
    messages = [
        {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    run = _chat(SENIOR_MODEL, messages, temperature=0.0)
    verdict = _parse_verdict(run.text)

    return VerifyRun(
        verdict=verdict,
        prompt_tokens=run.prompt_tokens,
        completion_tokens=run.completion_tokens,
        total_tokens=run.total_tokens,
        latency_ms=run.latency_ms,
        cost_estimate_usd=run.cost_estimate_usd,
        raw=run.raw,
    )
