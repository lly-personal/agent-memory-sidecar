from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any


EVENT_RETENTION_DAYS = 7
MAX_EVENT_ENVELOPE_BYTES = 4 * 1024
MAX_ENVELOPE_SCALAR_BYTES = 256

_SAFE_ENVELOPE_FIELDS = (
    "hook_event_name",
    "source",
    "tool_name",
    "status",
    "success",
    "exit_code",
)
_SECRET_KEY_PATTERN = (
    r"(?:authorization|cookie|set-cookie|aws_secret_access_key|"
    r"api[_-]?key|token|secret|password|"
    r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*_(?:api_key|token|secret|password))"
)
_SENSITIVE_HEADER_PATTERN = re.compile(
    r'''(?im)^(?P<prefix>[ \t]*(?:[<>][ \t]*)?["']?'''
    r'''(?:authorization|cookie|set-cookie)["']?[ \t]*:[ \t]*)[^\r\n]*'''
)
_QUOTED_SECRET_PATTERN = re.compile(
    rf'''(?P<prefix>(?<![a-z0-9_])(?:\\?["'])?{_SECRET_KEY_PATTERN}'''
    r'''(?:\\?["'])?\s*[:=]\s*)(?P<quote>\\?["'])(?P<value>.*?)(?P=quote)''',
    flags=re.IGNORECASE | re.DOTALL,
)
_SECRET_PATTERNS = (
    re.compile(
        rf'''(?i)((?<![a-z0-9_]){_SECRET_KEY_PATTERN}\s*[:=]\s*)'''
        r'''(?!["'])[^\r\n,;&]+'''
    ),
)
def minimize_hook_event(
    *,
    payload: dict[str, Any],
    content: str,
) -> tuple[str, dict[str, Any]]:
    """Return a bounded event envelope without persisting full prompt/tool payloads."""

    encoded = content.encode("utf-8", errors="replace")
    digest = hashlib.sha256(encoded).hexdigest()
    envelope: dict[str, Any] = {
        key: _safe_scalar(payload.get(key))
        for key in _SAFE_ENVELOPE_FIELDS
        if payload.get(key) is not None
    }
    envelope.update(
        {
            "content_hash": f"sha256:{digest}",
            "content_bytes": len(encoded),
            "retention_days": EVENT_RETENTION_DAYS,
        }
    )
    if len(json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")) > MAX_EVENT_ENVELOPE_BYTES:
        for key in _SAFE_ENVELOPE_FIELDS:
            if isinstance(envelope.get(key), str):
                envelope[key] = "[TRUNCATED]"
    stored_content = (
        f"{envelope.get('hook_event_name') or 'CodexHook'} "
        f"{envelope['content_hash']} bytes={envelope['content_bytes']}"
    )
    return stored_content, envelope


def retention_cutoff(*, now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return (value - timedelta(days=EVENT_RETENTION_DAYS)).isoformat(timespec="seconds")


def _redact_secrets(content: str) -> str:
    redacted = _SENSITIVE_HEADER_PATTERN.sub(r"\g<prefix>[REDACTED]", content)
    redacted = _QUOTED_SECRET_PATTERN.sub(
        lambda match: (
            f"{match.group('prefix')}{match.group('quote')}"
            f"[REDACTED]{match.group('quote')}"
        ),
        redacted,
    )
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def _normalize_bounded_text(value: str) -> str:
    normalized = (
        value.replace("\\", "／")
        .replace('"', "'")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )
    return re.sub(r"[\x00-\x1f\x7f]", " ", normalized)


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        normalized = _normalize_bounded_text(_redact_secrets(value))
        raw = normalized.encode("utf-8", errors="replace")
        if len(raw) <= MAX_ENVELOPE_SCALAR_BYTES:
            return normalized
        return raw[:MAX_ENVELOPE_SCALAR_BYTES].decode("utf-8", errors="ignore")
    return f"[non-scalar:{type(value).__name__}]"
