"""Core audit logic comparing codebase references, .env, and .env.example."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from envaudit.parser import EnvEntry, parse_env_file
from envaudit.scanner import VarReference, scan_codebase
from envaudit.secrets import detect_secret

DEFAULT_IGNORED_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "PWD",
        "SHELL",
        "TERM",
        "LANG",
        "TZ",
        "HOSTNAME",
        "NO_COLOR",
        "CI",
        "GITHUB_ACTIONS",
        "GITHUB_SHA",
        "GITHUB_REF",
        "GITHUB_WORKSPACE",
        "RUNNER_OS",
    }
)


@dataclass(frozen=True)
class Finding:
    """Single audit finding."""

    code: str  # MISSING_IN_ENV | MISSING_IN_EXAMPLE | UNUSED_IN_CODE | SECRET_IN_EXAMPLE
    severity: str  # error | warning
    key: str
    message: str
    locations: list[str] = field(default_factory=list)


@dataclass
class AuditReport:
    """Complete result of an envaudit run."""

    root: Path
    has_env: bool
    has_example: bool
    code_keys: dict[str, list[VarReference]]
    env_entries: dict[str, EnvEntry]
    example_entries: dict[str, EnvEntry]
    findings: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    def to_dict(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "has_env": self.has_env,
            "has_example": self.has_example,
            "summary": {
                "code_vars": len(self.code_keys),
                "env_vars": len(self.env_entries),
                "example_vars": len(self.example_entries),
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "findings": [
                {
                    "code": f.code,
                    "severity": f.severity,
                    "key": f.key,
                    "message": f.message,
                    "locations": f.locations,
                }
                for f in self.findings
            ],
        }


def load_ignored_keys(root: Path, extra_ignore: set[str] | None = None) -> set[str]:
    """Load ignored env var names from defaults, .envauditignore, pyproject.toml, and CLI."""
    ignored = set(DEFAULT_IGNORED_KEYS)

    ignore_file = root / ".envauditignore"
    if ignore_file.is_file():
        for raw_line in ignore_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                ignored.add(line)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib  # Python 3.11+
        except ModuleNotFoundError:  # pragma: no cover
            tomllib = None  # type: ignore[assignment]
        if tomllib is not None:
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
                tool_cfg = data.get("tool", {}).get("envaudit", {})
                for item in tool_cfg.get("ignore", []):
                    if isinstance(item, str):
                        ignored.add(item.strip())
            except Exception:
                pass

    if extra_ignore:
        ignored.update(extra_ignore)
    return ignored


def _format_locations(refs: list[VarReference], limit: int = 3) -> list[str]:
    locs = [f"{r.file.as_posix()}:{r.line}" for r in refs[:limit]]
    if len(refs) > limit:
        locs.append(f"+{len(refs) - limit} more")
    return locs


def run_audit(
    root: Path,
    env_file: str = ".env",
    example_file: str = ".env.example",
    extra_ignore: set[str] | None = None,
) -> AuditReport:
    """Run all audit checks on the given project root."""
    root = root.resolve()
    env_path = root / env_file
    example_path = root / example_file

    has_env = env_path.is_file()
    has_example = example_path.is_file()

    env_entries = parse_env_file(env_path)
    example_entries = parse_env_file(example_path)
    code_keys = scan_codebase(root)
    ignored = load_ignored_keys(root, extra_ignore)

    findings: list[Finding] = []

    # 1. Code references missing from .env (only if .env exists)
    if has_env:
        for key in sorted(code_keys):
            if key in ignored:
                continue
            if key not in env_entries:
                findings.append(
                    Finding(
                        code="MISSING_IN_ENV",
                        severity="error",
                        key=key,
                        message=f"Used in code but missing from {env_file}",
                        locations=_format_locations(code_keys[key]),
                    )
                )

    # 2. Code or .env keys missing from .env.example
    expected_in_example = set(code_keys) | set(env_entries)
    for key in sorted(expected_in_example):
        if key in ignored:
            continue
        if key not in example_entries:
            locs = _format_locations(code_keys[key]) if key in code_keys else [f"{env_file}:{env_entries[key].line}"]
            findings.append(
                Finding(
                    code="MISSING_IN_EXAMPLE",
                    severity="error",
                    key=key,
                    message=f"Missing from {example_file}",
                    locations=locs,
                )
            )

    # 3. Secrets accidentally committed in .env.example
    for key, entry in sorted(example_entries.items()):
        reason = detect_secret(key, entry.value)
        if reason:
            findings.append(
                Finding(
                    code="SECRET_IN_EXAMPLE",
                    severity="error",
                    key=key,
                    message=f"Possible secret in {example_file}: {reason}",
                    locations=[f"{example_file}:{entry.line}"],
                )
            )

    # 4. Unused variables in .env or .env.example (not referenced in code)
    defined_keys = set(env_entries) | set(example_entries)
    for key in sorted(defined_keys):
        if key in ignored:
            continue
        if key not in code_keys:
            locs: list[str] = []
            if key in env_entries:
                locs.append(f"{env_file}:{env_entries[key].line}")
            if key in example_entries:
                locs.append(f"{example_file}:{example_entries[key].line}")
            findings.append(
                Finding(
                    code="UNUSED_IN_CODE",
                    severity="warning",
                    key=key,
                    message="Defined in env file(s) but never referenced in code",
                    locations=locs,
                )
            )

    return AuditReport(
        root=root,
        has_env=has_env,
        has_example=has_example,
        code_keys=code_keys,
        env_entries=env_entries,
        example_entries=example_entries,
        findings=findings,
    )


def fix_example_file(report: AuditReport, example_file: str = ".env.example") -> list[str]:
    """Append missing keys to .env.example safely without modifying existing keys."""
    missing = [f.key for f in report.findings if f.code == "MISSING_IN_EXAMPLE"]
    if not missing:
        return []

    example_path = report.root / example_file
    existing_text = ""
    if example_path.is_file():
        existing_text = example_path.read_text(encoding="utf-8", errors="replace")

    lines_to_add = [f"{key}=" for key in missing]
    prefix = ""
    if existing_text and not existing_text.endswith("\n"):
        prefix = "\n"
    if existing_text:
        prefix += "\n# Added by envaudit\n"
    else:
        prefix = "# Generated by envaudit\n"

    new_text = existing_text + prefix + "\n".join(lines_to_add) + "\n"
    example_path.write_text(new_text, encoding="utf-8")
    return missing
