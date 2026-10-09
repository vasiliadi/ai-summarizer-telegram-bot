"""Tests for the eval harness's shared setup."""

import os

from helpers import load_eval_script


def test_load_tags_sentry_events_as_eval(monkeypatch):
    """Harness errors land in Sentry as `eval`, whatever `.env` sets."""
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "LOCAL")
    bootstrap = load_eval_script(monkeypatch, "_bootstrap")

    bootstrap.load()

    assert os.environ["SENTRY_ENVIRONMENT"] == "eval"
