from types import SimpleNamespace

import pytest
from tenacity import RetryError

from exceptions import LimitExceededError, WebParseError
from helpers import make_app
from main import BotApp, build_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    app, fakes = make_app(mocker)

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

    # The five auth-gated commands (myinfo and the four set_*) all wire the same
    # func= predicate, backed by user_repo.check_auth.
    for call in calls[2:7]:
        assert call.kwargs["func"] == app._authorized


def test_authorized_gates_on_a_known_approved_sender(mocker):
    """_authorized passes only a present sender that check_auth approves."""
    app, fakes = make_app(mocker)
    message = mocker.MagicMock()

    fakes.user_repo.check_auth.return_value = True
    assert app._authorized(message) is True

    fakes.user_repo.check_auth.return_value = False
    assert app._authorized(message) is False

    message.from_user = None
    assert app._authorized(message) is False
    # The None guard short-circuits, so the repo is not consulted a third time.
    assert fakes.user_repo.check_auth.call_count == 2


def test_authorized_reads_an_unregistered_sender_as_unauthorized(mocker):
    """_authorized answers False rather than raising for an unknown user.

    TeleBot evaluates func= filters unguarded, so a ValueError out of
    check_auth would abort handler matching for the whole update — the sender
    would get silence instead of falling through to handle_message.
    """
    app, fakes = make_app(mocker)
    message = mocker.MagicMock()
    message.from_user.id = 4242
    fakes.user_repo.check_auth.side_effect = ValueError("User not found")

    assert app._authorized(message) is False
    # Pins the sender's own id as the one looked up, which every other
    # attribute of a MagicMock message would otherwise satisfy.
    fakes.user_repo.check_auth.assert_called_once_with(4242)


def test_run_starts_infinity_polling(mocker):
    """run() polls Telegram with the fixed 20s timeout."""
    app, fakes = make_app(mocker)

    app.run()

    fakes.bot.infinity_polling.assert_called_once_with(timeout=20)


def test_shutdown_cleans_up_and_flushes_the_tracer(mocker):
    """shutdown() sweeps temp files and flushes the tracer.

    Whether tracing is configured at all is Tracer.shutdown's decision, covered
    by tests/test_services.py::test_tracer_shutdown_*.
    """
    app, fakes = make_app(mocker)
    mock_clean_up = mocker.patch("main.clean_up")

    app.shutdown()

    mock_clean_up.assert_called_once_with(all_downloads=True)
    fakes.tracer.shutdown.assert_called_once_with()


def test_shutdown_flushes_the_tracer_when_the_sweep_fails(mocker):
    """A failing temp-file sweep still lets buffered spans flush.

    clean_up unlinks files directly, so a single OSError would otherwise cost
    everything the tracer has buffered.
    """
    app, fakes = make_app(mocker)
    mocker.patch("main.clean_up", side_effect=OSError("device busy"))

    with pytest.raises(OSError, match="device busy"):
        app.shutdown()

    fakes.tracer.shutdown.assert_called_once_with()


def test_unauthorized_user(message_factory, mocker):
    """Test that unauthorized users receive an access denied message."""
    msg = message_factory(content_type="text", text="Hello")
    app, fakes = make_app(mocker)
    fakes.user_repo.select_user.return_value = mocker.MagicMock(approved=False)

    app.handle_message(msg)

    fakes.bot.send_message.assert_called_once_with(msg.chat.id, "You are not approved.")


def test_handle_message_missing_user(message_factory, mocker):
    """Test handle_message rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="Hello")
    msg.from_user = None
    app, fakes = make_app(mocker)

    app.handle_message(msg)

    fakes.bot.reply_to.assert_called_once_with(msg, "User information is missing.")


def test_process_message_content_dispatches_audio(message_factory, mocker):
    """Test audio messages route to handle_audio."""
    msg = message_factory(content_type="audio")
    app, fakes = make_app(mocker)
    user = mocker.MagicMock()

    app.process_message_content(msg, user)

    fakes.handlers.handle_audio.assert_called_once_with(msg, user)


def test_process_message_content_dispatches_allowed_document(message_factory, mocker):
    """Test supported document MIME types route to handle_document."""
    msg = message_factory(content_type="document")
    app, fakes = make_app(mocker)
    user = mocker.MagicMock()

    app.process_message_content(msg, user)

    fakes.handlers.handle_document.assert_called_once_with(msg, user)


def test_process_message_content_dispatches_video_note(message_factory, mocker):
    """Test video note messages route to handle_video_note."""
    msg = message_factory(content_type="video_note")
    app, fakes = make_app(mocker)
    user = mocker.MagicMock()

    app.process_message_content(msg, user)

    fakes.handlers.handle_video_note.assert_called_once_with(msg, user)


def test_process_message_content_dispatches_voice(message_factory, mocker):
    """Test voice messages route to handle_voice."""
    msg = message_factory(content_type="voice")
    app, fakes = make_app(mocker)
    user = mocker.MagicMock()

    app.process_message_content(msg, user)

    fakes.handlers.handle_voice.assert_called_once_with(msg, user)


def test_process_message_content_dispatches_video(message_factory, mocker):
    """Test video messages route to handle_video."""
    msg = message_factory(content_type="video")
    app, fakes = make_app(mocker)
    user = mocker.MagicMock()

    app.process_message_content(msg, user)

    fakes.handlers.handle_video.assert_called_once_with(msg, user)


def test_process_message_content_dispatches_url(message_factory, mocker):
    """Test text messages extract the first token and route to handle_url."""
    msg = message_factory(
        content_type="text",
        text="https://example.com/article extra words",
    )
    app, fakes = make_app(mocker)
    user = mocker.MagicMock()

    app.process_message_content(msg, user)

    fakes.handlers.handle_url.assert_called_once_with(
        msg,
        user,
        "https://example.com/article",
    )


def test_process_message_content_sends_textless_fallback(message_factory, mocker):
    """Test unsupported non-text messages produce a clear fallback response."""
    msg = message_factory(content_type="document")
    msg.document.mime_type = "application/zip"
    msg.text = None
    app, fakes = make_app(mocker)
    user = mocker.MagicMock()

    app.process_message_content(msg, user)

    fakes.bot.send_message.assert_called_once_with(msg.chat.id, "No text to process.")


def test_handle_message_limit_exceeded(message_factory, mocker):
    """Test handle_message when rate limit is exceeded."""
    msg = message_factory(content_type="text", text="http://youtube.com/watch?v=123")
    app, fakes = make_app(mocker)
    fakes.user_repo.select_user.return_value = mocker.MagicMock(approved=True)
    mocker.patch.object(
        app,
        "process_message_content",
        side_effect=LimitExceededError("Rate limit exceeded"),
    )

    app.handle_message(msg)

    fakes.bot.reply_to.assert_called_once_with(
        msg,
        "Daily limit has been exceeded, try again tomorrow.",
    )


def test_handle_message_retry_error(message_factory, mocker):
    """Test handle_message when retries are exhausted."""
    msg = message_factory(content_type="text", text="http://youtube.com/watch?v=123")
    app, fakes = make_app(mocker)
    fakes.user_repo.select_user.return_value = mocker.MagicMock(approved=True)
    mocker.patch.object(
        app,
        "process_message_content",
        side_effect=RetryError(mocker.MagicMock()),
    )

    app.handle_message(msg)

    fakes.bot.reply_to.assert_called_once_with(
        msg,
        "An error occurred during execution. Please try again in 10 minutes.",
    )


def test_handle_message_web_parse_error(message_factory, mocker):
    """Test handle_message when a webpage URL cannot be parsed."""
    msg = message_factory(content_type="text", text="http://example.com/dead")
    app, fakes = make_app(mocker)
    fakes.user_repo.select_user.return_value = mocker.MagicMock(approved=True)
    mocker.patch.object(
        app,
        "process_message_content",
        side_effect=WebParseError("Tavily could not extract content"),
    )

    app.handle_message(msg)

    fakes.bot.reply_to.assert_called_once_with(
        msg,
        "Check provided URL, looks like the page is not available.",
    )


def test_handle_message_unexpected_error(message_factory, mocker):
    """Test handle_message when an unexpected exception occurs."""
    msg = message_factory(content_type="text", text="http://youtube.com/watch?v=123")
    app, fakes = make_app(mocker)
    fakes.user_repo.select_user.return_value = mocker.MagicMock(approved=True)
    mocker.patch.object(
        app,
        "process_message_content",
        side_effect=Exception("BOOM"),
    )

    app.handle_message(msg)

    fakes.bot.reply_to.assert_called_once_with(msg, "Unexpected: Exception")
