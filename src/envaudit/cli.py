"""Command-line interface for envaudit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from envaudit import __version__
from envaudit.auditor import AuditReport, fix_example_file, run_audit


class _Style:
    def __init__(self, use_color: bool) -> None:
        self.use_color = use_color

    def _wrap(self, code: str, text: str) -> str:
        if not self.use_color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)


def _supports_color(no_color_flag: bool) -> bool:
    if no_color_flag or os.environ.get("NO_COLOR") is not None:
        return False
    return sys.stdout.isatty()


def _print_report(report: AuditReport, style: _Style, added_keys: list[str]) -> None:
    print()
    print(f"  {style.bold('envaudit')} {style.dim(f'v{__version__}')}  {style.cyan(str(report.root))}")
    print(
        "  "
        + style.dim(
            f"code: {len(report.code_keys)} vars | "
            f".env: {len(report.env_entries)} vars | "
            f".env.example: {len(report.example_entries)} vars"
        )
    )
    print()

    if not report.findings:
        print(f"  {style.green('PASS')} All environment variables are in sync and clean.")
        print()
        return

    for finding in report.findings:
        if finding.severity == "error":
            badge = style.red("ERROR")
        else:
            badge = style.yellow("WARN ")

        locs = f" {style.dim('(' + ', '.join(finding.locations) + ')')}" if finding.locations else ""
        print(f"  {badge}  {style.bold(finding.key)}  {finding.message}{locs}")

    if added_keys:
        print()
        print(
            f"  {style.green('FIXED')} Added {len(added_keys)} missing key(s) to .env.example: "
            + ", ".join(added_keys)
        )

    print()
    err_count = len(report.errors)
    warn_count = len(report.warnings)
    summary = f"  Summary: {err_count} error(s), {warn_count} warning(s)"
    print(style.red(summary) if err_count else style.yellow(summary))
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="envaudit",
        description="Audit .env, .env.example, and your codebase for missing, unused, or leaked environment variables.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to .env file relative to project root (default: .env)",
    )
    parser.add_argument(
        "--example",
        default=".env.example",
        help="Path to .env.example file relative to project root (default: .env.example)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically append missing keys to .env.example",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Exit with code 1 if any errors are found",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="With --ci, also fail on warnings (e.g. unused env vars)",
    )
    parser.add_argument(
        "--ignore",
        default="",
        help="Comma-separated list of env var names to ignore",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report as JSON",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print(f"envaudit: directory not found: {root}", file=sys.stderr)
        return 2

    extra_ignore = {k.strip() for k in args.ignore.split(",") if k.strip()}
    report = run_audit(
        root=root,
        env_file=args.env,
        example_file=args.example,
        extra_ignore=extra_ignore,
    )

    added_keys: list[str] = []
    if args.fix:
        added_keys = fix_example_file(report, example_file=args.example)
        if added_keys:
            report = run_audit(
                root=root,
                env_file=args.env,
                example_file=args.example,
                extra_ignore=extra_ignore,
            )

    if args.json_output:
        payload = report.to_dict()
        if added_keys:
            payload["fixed_keys"] = added_keys
        print(json.dumps(payload, indent=2))
    else:
        style = _Style(_supports_color(args.no_color))
        _print_report(report, style, added_keys)

    if args.ci:
        if report.errors:
            return 1
        if args.strict and report.warnings:
            return 1
    return 0
