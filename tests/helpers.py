"""Builders shared by more than one test module."""

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
