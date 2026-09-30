"""Builders shared by more than one test module."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from main import BotApp


def make_app(mocker):
    """Return (app, fakes) with every BotApp collaborator injected as a MagicMock."""
    fakes = SimpleNamespace(
        bot=mocker.MagicMock(),
        user_repo=mocker.MagicMock(),
        quota_manager=mocker.MagicMock(),
        tracer=mocker.MagicMock(),
        handlers=mocker.MagicMock(),
    )
    app = BotApp(
        fakes.bot,
        fakes.user_repo,
        fakes.quota_manager,
        fakes.tracer,
        fakes.handlers,
    )
    return app, fakes


EVAL_DIR = Path(__file__).resolve().parents[1] / "scripts" / "eval"


def load_eval_script(monkeypatch, name):
    """Import `scripts/eval/<name>.py` as a fresh module without running its CLI.

    The scripts import each other by bare name (`import judge`), so their
    directory goes on the path for the test's duration.
    """
    monkeypatch.syspath_prepend(str(EVAL_DIR))
    spec = importlib.util.spec_from_file_location(
        f"eval_{name}_test",
        EVAL_DIR / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
