from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrefixedText:
    """Text paired with the display prefix for the source that produced it."""

    text: str
    prefix: str


def format_prefixed_summary(prefix: str, summary: str) -> str:
    """Format a prefixed summary with a stable blank line separator."""
    return f"{prefix}\n\n{summary.strip()}"
