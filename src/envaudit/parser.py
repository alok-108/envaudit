"""Parser for .env and .env.example files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

_ENV_LINE_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)


@dataclass(frozen=True)
class EnvEntry:
    """Represents a single key-value entry in an env file."""

    key: str
    value: str
    line: int


def _strip_quotes_and_comment(raw_value: str) -> str:
    """Normalize a raw env value, stripping surrounding quotes or inline comments."""
    val = raw_value.strip()
    if not val:
        return ""

    if val[0] in ('"', "'"):
        quote = val[0]
        end_idx = val.find(quote, 1)
        if end_idx != -1:
            return val[1:end_idx]
        return val[1:]

    # Unquoted value: strip trailing inline comment preceded by whitespace
    comment_idx = val.find(" #")
    if comment_idx != -1:
        val = val[:comment_idx].rstrip()
    return val


def parse_env_file(path: Path) -> dict[str, EnvEntry]:
    """Parse a .env or .env.example file into a mapping of key -> EnvEntry."""
    if not path.is_file():
        return {}

    entries: dict[str, EnvEntry] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_LINE_RE.match(raw_line)
        if not match:
            continue
        key = match.group(1)
        value = _strip_quotes_and_comment(match.group(2))
        entries[key] = EnvEntry(key=key, value=value, line=line_no)
    return entries
