"""Codebase scanner for environment variable references across languages."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re

SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        "coverage",
        "vendor",
    }
)

CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".yml",
        ".yaml",
    }
)

# Regex patterns per language family
_JS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bprocess\.env\.([A-Z_][A-Z0-9_]*)\b"),
    re.compile(r"""\bprocess\.env\[['"]([A-Z_][A-Z0-9_]*)['"]\]"""),
    re.compile(r"\bimport\.meta\.env\.([A-Z_][A-Z0-9_]*)\b"),
    re.compile(r"""\bDeno\.env\.get\(\s*['"]([A-Z_][A-Z0-9_]*)['"]\s*\)"""),
)

_GO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""\bos\.(?:Getenv|LookupEnv)\(\s*"([A-Z_][A-Z0-9_]*)"\s*\)"""),
)

_RUST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""\b(?:std::)?env::var\(\s*"([A-Z_][A-Z0-9_]*)"\s*\)"""),
    re.compile(r"""\b(?:option_)?env!\(\s*"([A-Z_][A-Z0-9_]*)"\s*\)"""),
)

_RUBY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""\bENV\[['"]([A-Z_][A-Z0-9_]*)['"]\]"""),
    re.compile(r"""\bENV\.fetch\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
)

_PHP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""\bgetenv\(\s*['"]([A-Z_][A-Z0-9_]*)['"]\s*\)"""),
    re.compile(r"""\$_ENV\[['"]([A-Z_][A-Z0-9_]*)['"]\]"""),
    re.compile(r"""\benv\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
)

_YAML_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::?[-?][^}]*)?\}")

_PY_FALLBACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""\bos\.environ\[['"]([A-Z_][A-Z0-9_]*)['"]\]"""),
    re.compile(r"""\bos\.(?:environ\.get|getenv)\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
)


@dataclass(frozen=True)
class VarReference:
    """A single occurrence of an environment variable in source code."""

    key: str
    file: Path
    line: int


def _scan_python_ast(text: str, file_path: Path) -> list[VarReference]:
    """Use Python's AST to accurately extract os.getenv / os.environ references."""
    refs: list[VarReference] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _scan_lines(text, file_path, _PY_FALLBACK_PATTERNS)

    for node in ast.walk(tree):
        # os.environ["FOO"]
        if isinstance(node, ast.Subscript):
            if _is_os_environ(node.value) and isinstance(node.slice, ast.Constant):
                if isinstance(node.slice.value, str) and node.slice.value.isidentifier():
                    refs.append(VarReference(node.slice.value, file_path, node.lineno))
        # os.getenv("FOO") or os.environ.get("FOO")
        elif isinstance(node, ast.Call):
            if _is_env_getter_call(node.func) and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    if arg0.value.isidentifier():
                        refs.append(VarReference(arg0.value, file_path, node.lineno))
    return refs


def _is_os_environ(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _is_env_getter_call(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        # os.getenv(...)
        if (
            node.attr == "getenv"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            return True
        # os.environ.get(...)
        if node.attr == "get" and _is_os_environ(node.value):
            return True
    return False


def _scan_lines(
    text: str, file_path: Path, patterns: tuple[re.Pattern[str], ...]
) -> list[VarReference]:
    refs: list[VarReference] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            for match in pattern.finditer(line):
                refs.append(VarReference(match.group(1), file_path, line_no))
    return refs


def scan_file(file_path: Path, root: Path) -> list[VarReference]:
    """Scan a single source file for environment variable references."""
    suffix = file_path.suffix.lower()
    if suffix not in CODE_EXTENSIONS:
        return []

    rel_path = file_path.relative_to(root)
    text = file_path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".py":
        return _scan_python_ast(text, rel_path)
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        return _scan_lines(text, rel_path, _JS_PATTERNS)
    if suffix == ".go":
        return _scan_lines(text, rel_path, _GO_PATTERNS)
    if suffix == ".rs":
        return _scan_lines(text, rel_path, _RUST_PATTERNS)
    if suffix == ".rb":
        return _scan_lines(text, rel_path, _RUBY_PATTERNS)
    if suffix == ".php":
        return _scan_lines(text, rel_path, _PHP_PATTERNS)
    if suffix in {".yml", ".yaml"}:
        return _scan_lines(text, rel_path, (_YAML_PATTERN,))
    return []


def scan_codebase(root: Path) -> dict[str, list[VarReference]]:
    """Walk root directory and return mapping of env var name -> list of references."""
    refs_by_key: dict[str, list[VarReference]] = {}
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        for ref in scan_file(path, root):
            refs_by_key.setdefault(ref.key, []).append(ref)
    return refs_by_key
