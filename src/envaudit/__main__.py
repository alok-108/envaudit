"""Allow running via `python -m envaudit`."""

import sys

from envaudit.cli import main

if __name__ == "__main__":
    sys.exit(main())
