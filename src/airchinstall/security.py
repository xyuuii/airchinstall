from __future__ import annotations

import re

ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
SECRET_PATTERNS = (
    re.compile(
        r"(?im)\b(?:[A-Z0-9_]*(?:API[_ -]?KEY|TOKEN|PASSWORD|PASSPHRASE)|"
        r"WIFI(?:[_ -]?(?:PASSWORD|PSK))?)\s*[:=]\s*(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|\S+)"
    ),
    re.compile(r"(?im)Authorization:\s*Bearer\s+\S+"),
    re.compile(
        r"(?i)--(?:api[-_]?key|token|password|passphrase|psk|key-file)(?:=|\s+)"
        r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|\S+)"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def safe_excerpt(text: str, limit: int = 4000) -> str:
    cleaned = redact_text(ANSI_ESCAPE.sub("", text))
    return cleaned[-limit:]


def sanitize_data(value):
    if isinstance(value, str):
        return safe_excerpt(value)
    if isinstance(value, dict):
        return {sanitize_data(key): sanitize_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_data(item) for item in value)
    return value
