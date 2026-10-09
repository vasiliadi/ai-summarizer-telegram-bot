"""Shared setup for the evaluation scripts: repo path, `.env`, and `src/` on the path."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def load() -> Path:
    """Load `.env`, put `src/` on the import path, and return the repo root.

    Also tags Sentry events `eval`; see evals.md → *Harness runs report to Sentry as
    `eval`*.
    """
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    # Overrides `.env`, and must run before anything imports `config`.
    os.environ["SENTRY_ENVIRONMENT"] = "eval"
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    return REPO


def langfuse_rest() -> tuple[str, tuple[str, str]]:
    """Return the Langfuse base URL and basic-auth pair for direct REST calls."""
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    return base, auth
