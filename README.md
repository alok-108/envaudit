# envaudit

**Catch missing, unused, and leaked environment variables before production does.**

`envaudit` is a **zero-dependency** CLI that scans your actual source code (`Python`, `JS/TS`, `Go`, `Rust`, `Ruby`, `PHP`, `YAML`) and audits it against `.env` and `.env.example` in milliseconds.

```text
  envaudit v0.1.0  /path/to/your-app
  code: 6 vars | .env: 4 vars | .env.example: 3 vars

  ERROR  STRIPE_SECRET_KEY  Used in code but missing from .env (src/billing.py:14)
  ERROR  STRIPE_SECRET_KEY  Missing from .env.example (src/billing.py:14)
  ERROR  GITHUB_TOKEN       Possible secret in .env.example: Matches GitHub token pattern (.env.example:5)
  WARN   LEGACY_REDIS_URL   Defined in env file(s) but never referenced in code (.env:8)

  Summary: 3 error(s), 1 warning(s)
```

---

## Why `envaudit`?

Most `.env` linters only check syntax. `envaudit` compares **three sources of truth** at once:

| Check | What it catches | Severity |
| :--- | :--- | :--- |
| **Missing in `.env`** | Code reads `os.getenv("X")` or `process.env.X`, but `.env` doesn't have it | `ERROR` |
| **Missing in `.env.example`** | Variable exists in code or `.env`, but teammates won't know to set it | `ERROR` |
| **Leaked Secret in `.env.example`** | Real API keys (`sk-`, `ghp_`, `AKIA`, `xoxb-`, high-entropy secrets) committed to example files | `ERROR` |
| **Unused in Code** | Dead variables cluttering `.env` or `.env.example` | `WARN` |

- **Zero runtime dependencies** — pure Python 3.10+ standard library.
- **AST-accurate for Python** — parses `os.environ[...]`, `os.environ.get(...)`, and `os.getenv(...)` via `ast`.
- **Multi-language** — supports `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.go`, `.rs`, `.rb`, `.php`, `.yml`/`.yaml`.
- **Safe `--fix`** — appends missing keys to `.env.example` without ever overwriting existing values.
- **CI-ready** — `--ci`, `--strict`, and `--json` flags built in.

---

## Quick Start

### Install

```bash
pip install git+https://github.com/alok-108/envaudit.git
```

Or run directly from a cloned repo without installing anything:

```bash
git clone https://github.com/alok-108/envaudit.git
PYTHONPATH=envaudit/src python -m envaudit /path/to/your-project
```

### Usage

```bash
# Audit current directory
envaudit

# Audit a specific project
envaudit ./my-app

# Auto-add missing keys to .env.example (safe, append-only)
envaudit --fix

# Fail CI on errors (or --strict to also fail on unused vars)
envaudit --ci
envaudit --ci --strict

# Machine-readable JSON output
envaudit --json

# Ignore specific variables
envaudit --ignore NODE_ENV,DEBUG_MODE
```

---

## Configuration

### `.envauditignore`

Create a `.envauditignore` file in your project root (one variable name per line):

```text
# Runtime / deployment vars
NODE_ENV
PORT
VERCEL_URL
```

### `pyproject.toml`

Or configure ignores directly in `pyproject.toml`:

```toml
[tool.envaudit]
ignore = ["NODE_ENV", "PORT", "VERCEL_URL"]
```

---

## GitHub Actions CI

Drop this into `.github/workflows/envaudit.yml` to block PRs with missing `.env.example` keys or leaked secrets:

```yaml
name: Env Audit
on: [push, pull_request]

jobs:
  envaudit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install git+https://github.com/alok-108/envaudit.git
      - run: envaudit --ci
```

---

## Running Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

---

## License

[MIT](LICENSE)
