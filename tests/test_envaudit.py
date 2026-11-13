"""Unit and integration tests for envaudit."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from envaudit.auditor import fix_example_file, run_audit
from envaudit.cli import main
from envaudit.parser import parse_env_file
from envaudit.secrets import detect_secret


class TestParser(unittest.TestCase):
    def test_parse_env_file_handles_quotes_exports_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "# Database config\n"
                'export DATABASE_URL="postgres://localhost/app"\n'
                "API_KEY='secret123' # inline comment\n"
                "PLAIN=hello # trailing note\n"
                "EMPTY=\n",
                encoding="utf-8",
            )
            parsed = parse_env_file(env_path)
            self.assertEqual(parsed["DATABASE_URL"].value, "postgres://localhost/app")
            self.assertEqual(parsed["API_KEY"].value, "secret123")
            self.assertEqual(parsed["PLAIN"].value, "hello")
            self.assertEqual(parsed["EMPTY"].value, "")
            self.assertEqual(parsed["DATABASE_URL"].line, 2)


class TestSecrets(unittest.TestCase):
    def test_detects_known_secret_patterns_and_ignores_placeholders(self) -> None:
        self.assertIsNotNone(detect_secret("OPENAI_API_KEY", "sk-proj-abcdefghijklmnopqrstuvwxyz123456"))
        self.assertIsNotNone(detect_secret("GITHUB_PAT", "ghp_1234567890abcdefghij1234567890"))
        self.assertIsNone(detect_secret("OPENAI_API_KEY", "your_openai_key_here"))
        self.assertIsNone(detect_secret("NEXT_PUBLIC_API_URL", "https://api.example.com/v1"))


class TestAuditAndCli(unittest.TestCase):
    def test_full_audit_detects_missing_unused_and_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text(
                "import os\n"
                "db = os.environ['DATABASE_URL']\n"
                "stripe = os.getenv('STRIPE_SECRET_KEY')\n",
                encoding="utf-8",
            )
            (root / "web.ts").write_text(
                "const url = process.env.NEXT_PUBLIC_URL;\n"
                "const vite = import.meta.env.VITE_APP_NAME;\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "DATABASE_URL=postgres://localhost/db\n"
                "UNUSED_FLAG=true\n",
                encoding="utf-8",
            )
            (root / ".env.example").write_text(
                "DATABASE_URL=postgres://localhost/db\n"
                "GITHUB_TOKEN=ghp_1234567890abcdefghij1234567890\n",
                encoding="utf-8",
            )

            report = run_audit(root)
            codes = {(f.code, f.key) for f in report.findings}

            self.assertIn(("MISSING_IN_ENV", "STRIPE_SECRET_KEY"), codes)
            self.assertIn(("MISSING_IN_ENV", "NEXT_PUBLIC_URL"), codes)
            self.assertIn(("MISSING_IN_ENV", "VITE_APP_NAME"), codes)
            self.assertIn(("MISSING_IN_EXAMPLE", "STRIPE_SECRET_KEY"), codes)
            self.assertIn(("MISSING_IN_EXAMPLE", "UNUSED_FLAG"), codes)
            self.assertIn(("SECRET_IN_EXAMPLE", "GITHUB_TOKEN"), codes)
            self.assertIn(("UNUSED_IN_CODE", "UNUSED_FLAG"), codes)

            # --ci should return 1 because errors exist
            self.assertEqual(main([str(root), "--ci", "--no-color"]), 1)

            # Fix should add missing keys to .env.example
            added = fix_example_file(report)
            self.assertIn("STRIPE_SECRET_KEY", added)
            example_text = (root / ".env.example").read_text(encoding="utf-8")
            self.assertIn("STRIPE_SECRET_KEY=", example_text)

    def test_clean_repo_passes_ci(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text(
                "import os\nPORT = os.getenv('PORT', '8000')\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("PORT=8000\n", encoding="utf-8")
            (root / ".env.example").write_text("PORT=8000\n", encoding="utf-8")

            exit_code = main([str(root), "--ci", "--strict", "--no-color"])
            self.assertEqual(exit_code, 0)

    def test_json_output_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.js").write_text("console.log(process.env.API_URL);\n", encoding="utf-8")
            report = run_audit(root)
            payload = json.loads(json.dumps(report.to_dict()))
            self.assertEqual(payload["summary"]["code_vars"], 1)
            self.assertEqual(payload["findings"][0]["key"], "API_URL")


if __name__ == "__main__":
    unittest.main()
