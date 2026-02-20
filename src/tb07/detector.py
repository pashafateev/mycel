from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4.1-nano"

SYSTEM_PROMPT = """You classify assistant utterances for follow-up workflow triggering.

Return JSON with this exact schema:
{
  "is_commitment": boolean,
  "confidence": number,
  "extracted_text": string
}

Rules:
- is_commitment=true only when the assistant clearly commits to a future action.
- Soft language, opinions, or possibilities should be false.
- confidence must be in [0,1].
- extracted_text should be the exact commitment span if true, else empty string.
Output JSON only.
"""

EXPLICIT_PATTERNS = [
    re.compile(r"\bi(?:\s+am)?\s*(?:will|'ll|ll|going to)\s+", re.IGNORECASE),
    re.compile(r"\blet me\s+", re.IGNORECASE),
    re.compile(r"\bi can\s+", re.IGNORECASE),
]

COMMITMENT_ACTION_WORDS = {
    "check",
    "follow up",
    "follow-up",
    "remind",
    "review",
    "send",
    "update",
    "get back",
    "circle back",
    "revisit",
    "handle",
    "take care",
    "look into",
    "confirm",
    "ping",
}

TIME_MARKERS = {
    "tomorrow",
    "tonight",
    "this weekend",
    "next week",
    "later",
    "after",
    "by",
    "at",
    "on",
}

SOFT_MARKERS = {
    "should",
    "probably",
    "might",
    "maybe",
    "worth",
    "i'd like",
    "id like",
    "could",
    "i think",
    "i guess",
}


@dataclass
class PromiseDetection:
    is_commitment: bool
    confidence: float
    extracted_text: str
    source: str


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_json(content: str) -> Dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()

    if content and content[0] != "{":
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)

    return json.loads(content)


def _contains_commitment_action(normalized: str) -> bool:
    if any(token in normalized for token in COMMITMENT_ACTION_WORDS):
        return True
    return bool(re.search(r"\b(?:at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", normalized))


def _keyword_fallback(utterance: str) -> PromiseDetection:
    normalized = _clean_text(utterance.lower())

    has_explicit_form = any(pattern.search(normalized) for pattern in EXPLICIT_PATTERNS)
    has_action = _contains_commitment_action(normalized)
    has_time = any(marker in normalized for marker in TIME_MARKERS)
    has_soft = any(marker in normalized for marker in SOFT_MARKERS)

    if has_explicit_form and (has_action or has_time) and not has_soft:
        return PromiseDetection(
            is_commitment=True,
            confidence=0.86,
            extracted_text=_clean_text(utterance),
            source="keyword_fallback",
        )

    if has_soft:
        return PromiseDetection(
            is_commitment=False,
            confidence=0.68,
            extracted_text="",
            source="keyword_fallback",
        )

    return PromiseDetection(
        is_commitment=False,
        confidence=0.9,
        extracted_text="",
        source="keyword_fallback",
    )


def detect_promises(utterance: str, model: str = DEFAULT_MODEL, timeout_s: float = 20.0) -> PromiseDetection:
    """Classify whether an utterance is a commitment that should trigger FollowUp.

    If OPENROUTER_API_KEY is unavailable or model call fails, falls back to keyword detection.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return _keyword_fallback(utterance)

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": utterance},
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)

        is_commitment = bool(parsed.get("is_commitment", False))
        confidence = float(parsed.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        extracted_text = str(parsed.get("extracted_text", ""))

        return PromiseDetection(
            is_commitment=is_commitment,
            confidence=confidence,
            extracted_text=_clean_text(extracted_text),
            source="openrouter",
        )
    except Exception:
        return _keyword_fallback(utterance)
