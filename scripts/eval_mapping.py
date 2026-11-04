#!/usr/bin/env python3
"""Evaluate AI mapping quality against a gold set (Slice 1.19, ADR 048).

The harness lives in the backend (``app/services/eval_*.py``) and is run through the
administration commands, so it uses the same database, AI settings and budget as the platform:

    python -m app.cli eval-template --framework "My framework" --out gold-set-template.xlsx
    python -m app.cli eval-import filled-in.xlsx --name "Pilot gold set" --framework "My framework"
    python -m app.cli eval-run --gold-set "Pilot gold set" --version <version id> --email you@example.org
    python -m app.cli eval-report --gold-set "Pilot gold set" --min-coverage 2

This script is a convenience: it passes its arguments to ``python -m app.cli`` from the
``backend`` folder (so it works from a checkout with the virtual environment active). With Docker
use ``docker compose exec api python -m app.cli ...``. The same functions are on the page
Admin > Check the AI's mapping. See docs/admin/ai-evaluation.md.

Target for the real pilot: Cohen's kappa of at least 0.6 between the AI and human mappers.
"""

import subprocess
import sys
from pathlib import Path

COMMANDS = {"eval-template", "eval-import", "eval-run", "eval-report"}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)  # noqa: T201
        return 2
    backend = Path(__file__).resolve().parent.parent / "backend"
    return subprocess.call([sys.executable, "-m", "app.cli", *argv], cwd=backend)  # noqa: S603


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
