from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

import httpx

TIERS: Tuple[str, ...] = ("intern", "junior", "senior", "executive")

SYSTEM_PROMPT = """You are a task routing classifier for Mycel's Organization model.
Classify the user prompt into exactly one tier:
- intern: fact extraction, summarization, formatting, parsing, classification
- junior: casual chat, lookups, simple tool use, reminders
- senior: knowledge linking, error recovery, code review, teaching
- executive: architecture design, complex multi-step reasoning, system design

Return JSON only with keys:
{"tier":"intern|junior|senior|executive","confidence":<0 to 1 float>}
No prose."""


@dataclass
class ClassificationResult:
    tier: str
    confidence: float
    method: str
    error: str | None = None


def classify_task(
    prompt: str,
    model: str = "google/gemini-2.5-flash-lite",
    timeout: float = 20.0,
) -> ClassificationResult:
    """Classify a prompt into intern/junior/senior/executive.

    Uses OpenRouter when OPENROUTER_API_KEY is available.
    Falls back to a keyword classifier when credentials are missing or request fails.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        tier, confidence = _keyword_classify(prompt)
        return ClassificationResult(
            tier=tier,
            confidence=confidence,
            method="keyword_fallback",
            error="OPENROUTER_API_KEY not set",
        )

    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://mycel.local/tb06",
            "X-Title": "mycel-tb06-routing-eval",
        }
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        tier, confidence = _parse_model_output(content)
        return ClassificationResult(tier=tier, confidence=confidence, method="openrouter")
    except Exception as exc:  # noqa: BLE001
        tier, confidence = _keyword_classify(prompt)
        return ClassificationResult(
            tier=tier,
            confidence=confidence,
            method="keyword_fallback",
            error=f"OpenRouter failure: {exc}",
        )


def _parse_model_output(content: str) -> Tuple[str, float]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = _extract_json(content)

    raw_tier = str(parsed.get("tier", "")).strip().lower()
    tier = raw_tier if raw_tier in TIERS else "junior"
    raw_confidence = parsed.get("confidence", 0.5)
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return tier, confidence


def _extract_json(content: str) -> Dict[str, object]:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _keyword_classify(prompt: str) -> Tuple[str, float]:
    text = prompt.lower()

    keyword_weights: Dict[str, List[Tuple[str, int]]] = {
        "intern": [
            ("summarize", 3),
            ("summary", 3),
            ("extract", 3),
            ("parse", 3),
            ("format", 3),
            ("classify", 3),
            ("rewrite", 2),
            ("list", 1),
            ("what day", 2),
            ("date", 2),
        ],
        "junior": [
            ("weather", 3),
            ("remind", 3),
            ("search", 3),
            ("find", 2),
            ("look up", 3),
            ("lookup", 3),
            ("near me", 3),
            ("book", 2),
            ("set a timer", 3),
            ("casual", 1),
        ],
        "senior": [
            ("review", 3),
            ("security", 3),
            ("debug", 3),
            ("replay", 2),
            ("tradeoff", 3),
            ("why is", 2),
            ("explain", 2),
            ("teach", 3),
            ("error", 3),
            ("incident", 2),
        ],
        "executive": [
            ("design", 3),
            ("architecture", 4),
            ("architect", 4),
            ("migration plan", 4),
            ("strategy", 3),
            ("roadmap", 3),
            ("multi-step", 3),
            ("system design", 4),
            ("build custom", 3),
            ("cost-effective", 2),
        ],
    }

    scores: Dict[str, int] = {tier: 0 for tier in TIERS}
    for tier, keywords in keyword_weights.items():
        for keyword, weight in keywords:
            if keyword in text:
                scores[tier] += weight

    # Bias up if explicit difficulty markers appear.
    if any(token in text for token in ("from scratch", "end-to-end", "org-wide", "company-wide")):
        scores["executive"] += 2

    best_tier = max(scores, key=scores.get)
    best_score = scores[best_tier]
    sorted_scores = sorted(scores.values(), reverse=True)
    margin = sorted_scores[0] - sorted_scores[1]

    if best_score == 0:
        return "junior", 0.35

    confidence = min(0.98, 0.45 + (best_score * 0.06) + (margin * 0.07))
    return best_tier, round(confidence, 2)
