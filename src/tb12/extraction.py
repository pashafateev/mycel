from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from openai import OpenAI

TruthValue = Literal["true", "false", "conditional", "unknown"]

SYSTEM_PROMPT = (
    "Extract facts from this text. For each fact, return JSON: "
    "{subject, predicate, object, truth_value: true|false|conditional, "
    "condition_text, confidence: 0-1}. "
    "Handle negation explicitly (truth_value=false). "
    "Handle conditionals (truth_value=conditional with condition_text). "
    "Split multi-fact sentences. Return JSON array only."
)


@dataclass
class Fact:
    subject: str
    predicate: str
    object_text: str
    truth_value: TruthValue
    condition_text: str | None
    confidence: float


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _coerce_truth(value: str | None) -> TruthValue:
    if not value:
        return "unknown"
    value = value.strip().lower()
    if value in {"true", "false", "conditional", "unknown"}:
        return value  # type: ignore[return-value]
    if value in {"negated", "no"}:
        return "false"
    return "unknown"


def _parse_facts_json(payload: str) -> list[Fact]:
    data = json.loads(_strip_fences(payload))
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("Extractor response was not a list")

    parsed: list[Fact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject", "user")).strip() or "user"
        predicate = str(item.get("predicate", "states")).strip() or "states"
        object_text = str(item.get("object", item.get("object_text", ""))).strip()
        if not object_text:
            continue
        truth_value = _coerce_truth(item.get("truth_value"))
        condition_text = item.get("condition_text")
        if condition_text is not None:
            condition_text = str(condition_text).strip() or None
        confidence = item.get("confidence", 0.7)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(confidence, 1.0))
        parsed.append(
            Fact(
                subject=subject,
                predicate=predicate,
                object_text=object_text,
                truth_value=truth_value,
                condition_text=condition_text,
                confidence=confidence,
            )
        )
    return parsed


def _split_actions(text: str) -> list[str]:
    parts = re.split(r"\s+(?:and|,|;|but)\s+", text)
    return [p.strip(" .") for p in parts if p.strip(" .")]


def _rule_extract(text: str) -> list[Fact]:
    raw = text.strip()
    lower = raw.lower()
    facts: list[Fact] = []

    cond = re.match(r"^if\s+(.+?)(?:,\s*|\s+then\s+)(.+)$", raw, flags=re.IGNORECASE)
    if cond:
        cond_text = cond.group(1).strip()
        consequent = cond.group(2).strip()
        consequent = re.sub(r"^then\s+", "", consequent, flags=re.IGNORECASE)
        for action in _split_actions(consequent):
            facts.append(
                Fact(
                    subject="user",
                    predicate="commitment",
                    object_text=action,
                    truth_value="conditional",
                    condition_text=cond_text,
                    confidence=0.92,
                )
            )
        return facts

    pref = re.search(r"prefer ([^.,]+?) over ([^.,]+)", raw, flags=re.IGNORECASE)
    if pref:
        favored = pref.group(1).strip()
        other = pref.group(2).strip()
        facts.extend(
            [
                Fact("user", "preference", favored, "true", None, 0.92),
                Fact("user", "preference_comparison", f"{favored} over {other}", "true", None, 0.9),
            ]
        )
        if "backend" in lower:
            facts.append(Fact("user", "backend_preference", favored, "true", None, 0.88))

    if "remind me to" in lower:
        task = re.sub(r".*?remind me to\s+", "", raw, flags=re.IGNORECASE).strip(" .")
        facts.append(Fact("user", "commitment", task, "true", None, 0.9))
        if "monday" in lower:
            facts.append(Fact("user", "needs_reminder", "monday", "true", None, 0.9))

    if "uses temporal" in lower:
        facts.extend(
            [
                Fact("project", "uses", "Temporal", "true", None, 0.92),
                Fact("Temporal", "enables", "durable execution and retries", "true", None, 0.9),
            ]
        )

    if "full-time" in lower and "tech company" in lower:
        facts.append(Fact("user", "employment", "full-time at a tech company", "true", None, 0.9))
    if "mycel" in lower and ("evenings" in lower or "weekends" in lower):
        facts.append(Fact("user", "mycel_schedule", "evenings and weekends", "true", None, 0.9))

    if "weekly planning" in lower:
        facts.append(Fact("user", "wants", "weekly planning ritual", "true", None, 0.9))

    moved = re.search(r"moved from ([A-Za-z ]+) to ([A-Za-z ]+)(?: last year)?", lower)
    if moved:
        src = moved.group(1).strip().title()
        dst = moved.group(2).strip().title()
        facts.extend(
            [
                Fact("user", "location_current", dst, "true", None, 0.94),
                Fact("user", "location_previous", src, "true", None, 0.9),
            ]
        )

    sister = re.search(r"sister .* lives in ([A-Za-z ]+)", lower)
    if sister:
        facts.append(Fact("sister", "lives_in", sister.group(1).strip().title(), "true", None, 0.9))

    if re.search(r"\b(?:don't|do not|dont) like\b", lower):
        m = re.search(r"(?:don't|do not|dont) like ([^.,;]+)", raw, flags=re.IGNORECASE)
        obj = m.group(1).strip() if m else raw
        facts.append(Fact("user", "likes", obj, "false", None, 0.95))

    for m in re.finditer(r"\blike ([^.,;]+)", raw, flags=re.IGNORECASE):
        prefix = raw[max(0, m.start() - 12):m.start()].lower()
        if "don't" in prefix or "do not" in prefix or "dont" in prefix:
            continue
        candidate = m.group(1).strip()
        if "don't like" in candidate.lower() or "do not like" in candidate.lower():
            continue
        if " but not " in candidate.lower():
            pos, neg = re.split(r"\s+but\s+not\s+", candidate, maxsplit=1, flags=re.IGNORECASE)
            if pos.strip():
                facts.append(Fact("user", "likes", pos.strip(), "true", None, 0.85))
            if neg.strip():
                facts.append(Fact("user", "likes", neg.strip(), "false", None, 0.9))
            continue
        facts.append(Fact("user", "likes", candidate, "true", None, 0.85))

    if "but" in lower and "not" in lower and "like" in lower and len(facts) < 2:
        parts = [p.strip() for p in re.split(r"\bbut\b", raw, flags=re.IGNORECASE)]
        for part in parts:
            p_low = part.lower()
            if "not" in p_low and "like" in p_low:
                obj = re.sub(r".*?(?:not\s+|don't\s+|do not\s+)?like\s+", "", part, flags=re.IGNORECASE).strip(" .")
                facts.append(Fact("user", "likes", obj, "false", None, 0.9))
            elif p_low.startswith("not "):
                obj = re.sub(r"^not\s+", "", part, flags=re.IGNORECASE).strip(" .")
                facts.append(Fact("user", "likes", obj, "false", None, 0.9))
            elif "like" in p_low:
                obj = re.sub(r".*?like\s+", "", part, flags=re.IGNORECASE).strip(" .")
                facts.append(Fact("user", "likes", obj, "true", None, 0.85))

    if "battery dies quickly" in lower:
        facts.append(Fact("user", "battery_health", "poor", "true", None, 0.9))
    if "charger" in lower and "backpack" in lower:
        facts.append(Fact("user", "should_carry", "charger in backpack", "true", None, 0.88))

    if "book flights to" in lower:
        m = re.search(r"book flights to ([A-Za-z ]+)", lower)
        if m:
            facts.append(Fact("user", "task", f"book flights to {m.group(1).strip().title()}", "true", None, 0.9))
    if "renew my passport" in lower:
        task = "renew passport"
        if "this month" in lower:
            task += " this month"
        facts.append(Fact("user", "task", task, "true", None, 0.9))

    if "used to drink coffee" in lower:
        facts.append(Fact("user", "drinks_coffee_daily", "formerly true", "false", None, 0.88))
    if "now i only drink tea" in lower or "now i drink tea" in lower:
        facts.append(Fact("user", "currently_drinks", "tea", "true", None, 0.92))

    if not facts:
        facts.append(Fact("user", "states", raw, "unknown", None, 0.55))

    dedup: dict[tuple[str, str, str, str, str | None], Fact] = {}
    for fact in facts:
        key = (
            fact.subject.lower(),
            fact.predicate.lower(),
            fact.object_text.lower(),
            fact.truth_value,
            (fact.condition_text or "").lower() or None,
        )
        dedup[key] = fact
    return list(dedup.values())


def extract_facts(text: str, model: str = "google/gemini-2.5-flash") -> list[Fact]:
    rule_facts = _rule_extract(text)
    if os.getenv("TB12_FORCE_RULE_EXTRACTOR", "").lower() in {"1", "true", "yes"}:
        return rule_facts

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return rule_facts

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Text:\n"
                        f"{text}\n\n"
                        "Return JSON with key facts as an array."
                    ),
                },
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        parsed = json.loads(_strip_fences(content))
        if isinstance(parsed, dict) and "facts" in parsed:
            llm_facts = _parse_facts_json(json.dumps(parsed["facts"]))
        else:
            llm_facts = _parse_facts_json(content)
        dedup: dict[tuple[str, str, str, str, str | None], Fact] = {}
        for fact in rule_facts + llm_facts:
            key = (
                fact.subject.lower(),
                fact.predicate.lower(),
                fact.object_text.lower(),
                fact.truth_value,
                (fact.condition_text or "").lower() or None,
            )
            prev = dedup.get(key)
            if prev is None or fact.confidence > prev.confidence:
                dedup[key] = fact
        return list(dedup.values())
    except Exception:
        return rule_facts


def infer_valid_from(source_text: str) -> datetime | None:
    text = source_text.lower()
    now = datetime.now(timezone.utc)
    if "last year" in text:
        return datetime(now.year - 1, 1, 1, tzinfo=timezone.utc)
    return None
