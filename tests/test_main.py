from types import SimpleNamespace

from main import BotApp, build_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(mocker):
    """Return (app, fakes) with every collaborator injected as a MagicMock."""
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


def _make_fake_container(mocker):
    """Return a duck-typed stand-in exposing only the members build_app reads."""
    return SimpleNamespace(
        bot=mocker.MagicMock(),
        user_repo=mocker.MagicMock(),
        quota_manager=mocker.MagicMock(),
        tracer=mocker.MagicMock(),
        handlers=mocker.MagicMock(),
    )


def test_build_app_wires_container_and_registers_handlers(mocker):
    """build_app wires BotApp to the container's members and registers handlers."""
    container = _make_fake_container(mocker)

    app = build_app(container)

    assert isinstance(app, BotApp)
    assert app._bot is container.bot
    assert app._user_repo is container.user_repo
    assert app._quota_manager is container.quota_manager
    assert app._tracer is container.tracer
    assert app._handlers is container.handlers
    # 8 registrations: start, info, myinfo, four /set_* commands, unified handler.
    assert container.bot.message_handler.call_count == 8


def test_register_registers_expected_handlers(mocker):
    """register() registers all eight handlers with their exact kwargs."""
    app, fakes = _make_app(mocker)

    app.register()

    assert fakes.bot.message_handler.call_count == 8
    calls = fakes.bot.message_handler.call_args_list
    assert calls[0].kwargs == {"commands": ["start"]}
    assert calls[1].kwargs == {"commands": ["info"]}
    assert calls[2].kwargs["commands"] == ["myinfo"]
    assert calls[3].kwargs["commands"] == ["set_target_language"]
    assert calls[4].kwargs["commands"] == ["set_summarizing_model"]
    assert calls[5].kwargs["commands"] == ["set_prompt_strategy"]
    assert calls[6].kwargs["commands"] == ["set_thinking_level"]
    assert calls[7].kwargs["content_types"] == [
        "text",
        "audio",
        "document",
        "video_note",
        "voice",
        "video",
    ]

    # The four auth-gated commands (myinfo, set_*) wire a func= predicate backed
    # by user_repo.check_auth.
    for call in calls[2:7]:
        func = call.kwargs["func"]
        message = mocker.MagicMock()
        fakes.user_repo.check_auth.return_value = True
        assert func(message) is True
        message.from_user = None
        assert func(message) is False


def test_run_starts_infinity_polling(mocker):
    """run() polls Telegram with the fixed 20s timeout."""
    app, fakes = _make_app(mocker)

    app.run()

    fakes.bot.infinity_polling.assert_called_once_with(timeout=20)


def test_shutdown_cleans_up_and_flushes_the_tracer(mocker):
    """shutdown() sweeps temp files and flushes the tracer.

    Whether tracing is configured at all is Tracer.shutdown's decision, covered
    by tests/test_services.py::test_tracer_shutdown_*.
    """
    app, fakes = _make_app(mocker)
    mock_clean_up = mocker.patch("main.clean_up")

    app.shutdown()

    mock_clean_up.assert_called_once_with(all_downloads=True)
    fakes.tracer.shutdown.assert_called_once_with()
