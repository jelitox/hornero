"""Shared redaction layer (SPEC-003 §9, extending SPEC-002 R9).

Every surface hornero writes or emits (wiki pages, reports, traces, run
logs, digests) passes through :func:`redact`. Two mechanisms compose:

- known secret **shapes** (same pattern set the push secret-scan uses);
- **exact values** currently present in process env vars whose names match
  ``*_KEY|*_TOKEN|*_SECRET|*_PASSWORD`` — the strongest signal available:
  if it is a live credential in this environment, it never reaches disk.

Generators never read ``.env*`` files; a secret-bearing file is documented
as "configuration exists at X", never by content.
"""

import os
import re

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("secret key (sk-...)", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("URL with userinfo", re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
]

_ENV_NAME = re.compile(r".*(_KEY|_TOKEN|_SECRET|_PASSWORD)$", re.IGNORECASE)
_MIN_ENV_VALUE_LEN = 8  # never redact trivially short values ("1", "true")


def scan_secrets(text: str) -> list[str]:
    """Names of the secret shapes present in ``text`` (refusal gate)."""
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


def _env_secrets() -> list[tuple[str, str]]:
    return [
        (name, value)
        for name, value in os.environ.items()
        if _ENV_NAME.match(name) and len(value) >= _MIN_ENV_VALUE_LEN
    ]


def redact(text: str) -> str:
    """Replace live env secret values and known secret shapes with
    ``[REDACTED:<label>]`` markers. Idempotent; safe on any text."""
    for name, value in _env_secrets():
        if value in text:
            text = text.replace(value, f"[REDACTED:{name}]")
    for label, pattern in SECRET_PATTERNS:
        text = pattern.sub(f"[REDACTED:{label}]", text)
    return text
