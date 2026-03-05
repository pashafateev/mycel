from __future__ import annotations

import html
import re
from urllib.parse import urlparse, urlunparse

import httpx

MAX_FETCH_CHARS = 2000
MAX_FETCH_BYTES = 200_000
FETCH_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_JS_REQUIRED_PHRASES = (
    "javascript required",
    "requires javascript",
    "javascript is required",
    "please enable javascript",
    "you need to enable javascript",
    "enable javascript to continue",
)


def is_valid_fetch_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _sanitize_url_for_display(value: str) -> str:
    parsed = urlparse(value.strip())
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


def _clean_text(raw: str) -> str:
    without_scripts = _SCRIPT_STYLE_RE.sub(" ", raw)
    no_tags = _TAG_RE.sub(" ", without_scripts)
    unescaped = html.unescape(no_tags)
    lines = [line.strip() for line in unescaped.splitlines()]
    non_empty = [line for line in lines if line]
    normalized = "\n".join(non_empty)
    return re.sub(r"[ \t]+", " ", normalized).strip()


def _looks_like_css_payload(cleaned: str, content_type: str) -> bool:
    if "text/css" in content_type:
        return True

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) < 5:
        return False

    css_like_lines = sum(1 for line in lines if "{" in line and "}" in line and ":" in line and ";" in line)
    return css_like_lines >= max(5, int(len(lines) * 0.6))


def _is_js_required_or_app_shell(raw: str, cleaned: str, content_type: str) -> bool:
    raw_lower = raw.lower()
    if any(phrase in raw_lower for phrase in _JS_REQUIRED_PHRASES):
        return True

    has_root_shell = any(
        marker in raw_lower
        for marker in (
            'id="root"',
            "id='root'",
            'id="app"',
            "id='app'",
            'id="__next"',
            "id='__next'",
        )
    )
    if has_root_shell and raw_lower.count("<script") >= 2 and len(cleaned) < 200:
        return True

    if _looks_like_css_payload(cleaned, content_type):
        return True

    return False


def fetch_url_summary(value: str) -> str:
    url = value.strip()
    if not is_valid_fetch_url(url):
        raise ValueError("Usage: /m_fetch <http(s)://url>")

    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            body = response.content[:MAX_FETCH_BYTES].decode(response.encoding or "utf-8", errors="replace")
            content_type = response.headers.get("content-type", "").lower()
    except httpx.HTTPError as exc:
        raise RuntimeError("Unable to fetch URL right now.") from exc

    cleaned = _clean_text(body)
    display_url = _sanitize_url_for_display(url)

    if _is_js_required_or_app_shell(body, cleaned, content_type):
        return (
            f"source: {display_url}\n\n"
            "This page appears to require JavaScript or returned an app shell/CSS payload. "
            "Try a print/export/raw-content URL instead."
        )

    if not cleaned:
        cleaned = "(no readable content)"

    snippet = cleaned[:MAX_FETCH_CHARS]
    if len(cleaned) > MAX_FETCH_CHARS:
        snippet += "\n\n...(truncated)"

    return f"source: {display_url}\n\n{snippet}"
