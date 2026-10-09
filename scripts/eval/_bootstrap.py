"""Shared setup for the evaluation scripts: repo path, `.env`, and `src/` on the path."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def load() -> Path:
    """Load `.env`, put `src/` on the import path, and return the repo root.

    Also tags Sentry events `eval` and lengthens the Langfuse timeout; see evals.md →
    *Harness runs report to Sentry as `eval`* and *A run can lose items on the way to
    Langfuse*.
    """
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    # Overrides `.env`, and must run before anything imports `config`.
    os.environ["SENTRY_ENVIRONMENT"] = "eval"
    # Also the span exporter's budget: at the SDK's 5 s a sweep dropped a span batch.
    # A larger value from `.env` or the shell is kept.
    timeout = max(30, int(os.environ.get("LANGFUSE_TIMEOUT") or 0))
    os.environ["LANGFUSE_TIMEOUT"] = str(timeout)
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    return REPO


def langfuse_rest() -> tuple[str, tuple[str, str]]:
    """Return the Langfuse base URL and basic-auth pair for direct REST calls."""
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    return base, auth
