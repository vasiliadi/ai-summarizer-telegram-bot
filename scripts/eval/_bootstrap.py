"""Shared setup for the STG-138 evaluation scripts.

Every script here runs standalone from the repo root and needs the same three
things: the repo path, `.env` loaded, and `src/` importable so the harness can
reuse the bot's own prompts and model client rather than restating them.

Deriving the root from `__file__` rather than hardcoding it is what lets these
scripts survive being moved or checked out elsewhere — the previous versions
lived in a session-scoped temp directory with an absolute path baked in.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def load() -> Path:
    """Load `.env`, put `src/` on the import path, and return the repo root."""
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    return REPO


def langfuse_rest() -> tuple[str, tuple[str, str]]:
    """Return the Langfuse base URL and basic-auth pair for direct REST calls.

    The SDK covers datasets and experiments; scores, evaluators and evaluation
    rules are reached over REST because the pieces this project needs live on
    the unstable API or on routes the SDK does not wrap.
    """
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    return base, auth
