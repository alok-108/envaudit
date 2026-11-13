"""Secret leak detection for .env.example files."""

from __future__ import annotations

import math
import re

# Known secret token prefixes that should never appear in .env.example
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI API key", re.compile(r"^sk-(?:proj-)?[A-Za-z0-9_-]{20,}$")),
    ("Anthropic API key", re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,}$")),
    ("GitHub token", re.compile(r"^(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}$")),
    ("GitHub fine-grained token", re.compile(r"^github_pat_[A-Za-z0-9_]{20,}$")),
    ("AWS Access Key ID", re.compile(r"^AKIA[0-9A-Z]{16}$")),
    ("Google API key", re.compile(r"^AIza[0-9A-Za-z_-]{35}$")),
    ("Slack token", re.compile(r"^xox[baprs]-[0-9A-Za-z-]{10,}$")),
    ("Stripe live/test key", re.compile(r"^(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}$")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)

_PLACEHOLDER_HINTS = (
    "your_",
    "your-",
    "example",
    "placeholder",
    "changeme",
    "change_me",
    "replace_me",
    "dummy",
    "test",
    "sample",
    "todo",
    "xxx",
    "***",
    "<",
    ">",
    "${",
)

_SAFE_KEY_PREFIXES = ("NEXT_PUBLIC_", "VITE_", "PUBLIC_")


def _shannon_entropy(value: str) -> float:
    """Calculate Shannon entropy in bits per character."""
    if not value:
        return 0.0
    length = len(value)
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _is_placeholder(value: str) -> bool:
    """Return True if value looks like an intentional placeholder or URL/bool."""
    lower = value.lower()
    if any(hint in lower for hint in _PLACEHOLDER_HINTS):
        return True
    if lower in ("true", "false", "0", "1", "localhost", "development", "production"):
        return True
    if lower.startswith(("http://localhost", "https://localhost", "postgres://", "sqlite://")):
        return True
    return False


def detect_secret(key: str, value: str) -> str | None:
    """Return a reason string if value in .env.example looks like a real secret."""
    if not value or len(value) < 8:
        return None
    if _is_placeholder(value):
        return None

    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            return f"Matches {label} pattern"

    if key.startswith(_SAFE_KEY_PREFIXES):
        return None

    # High-entropy check for secret-named variables
    secret_key_hint = any(
        tok in key.upper()
        for tok in ("SECRET", "TOKEN", "KEY", "PASSWORD", "PASS", "AUTH", "CREDENTIAL")
    )
    if secret_key_hint and len(value) >= 20 and " " not in value:
        entropy = _shannon_entropy(value)
        if entropy >= 3.8:
            return f"High-entropy value ({entropy:.1f} bits/char) in sensitive key"

    return None
