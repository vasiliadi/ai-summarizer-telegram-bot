from types import SimpleNamespace

import pytest
from telebot import types
from tenacity import RetryError

from domain import PrefixedText
from exceptions import LimitExceededError, WebParseError
from handlers import MessageHandlers
from helpers import make_app
from utils import classify_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handlers(mocker):
    """Return (handlers, fakes) with every collaborator injected as a MagicMock."""
    fakes = SimpleNamespace(
        bot=mocker.MagicMock(),
        messenger=mocker.MagicMock(),
        summarizer=mocker.MagicMock(),
        web_parser=mocker.MagicMock(),
        quota_manager=mocker.MagicMock(),
        downloader=mocker.MagicMock(),
    )
    handlers = MessageHandlers(
        fakes.bot,
        fakes.messenger,
        fakes.summarizer,
        fakes.web_parser,
        fakes.quota_manager,
        fakes.downloader,
    )
    return handlers, fakes


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


def test_successful_document_flow(message_factory, mocker):
    """Test a valid user sending a document receives the generated summary."""
    msg = message_factory(content_type="document")
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock(
        approved=True,
        summarizing_model="mock-model",
        prompt_key_for_summary="mock-prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    fakes.messenger.get_file_with_retry.return_value = mock_file
    fakes.summarizer.summarize_with_document.return_value = (
        "Here is your awesome summary"
    )

    handlers.handle_document(msg, user)

    fakes.messenger.send_answer.assert_called_once_with(
        msg,
        "Here is your awesome summary",
    )


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


def test_handle_audio_file_too_large(message_factory, mocker):
    """Test that audio files over 20MB are rejected."""
    msg = message_factory(content_type="audio")
    msg.audio.file_size = 25_000_000
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_audio(msg, user)

    fakes.bot.reply_to.assert_called_once_with(msg, "File is too big.")
    fakes.summarizer.summarize.assert_not_called()


def test_handle_audio_happy_path(message_factory, mocker):
    """Test successful audio file processing."""
    msg = message_factory(content_type="audio")
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock(
        approved=True,
        summarizing_model="model",
        prompt_key_for_summary="prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    fakes.messenger.get_file_with_retry.return_value = mock_file

    handlers.handle_audio(msg, user)

    assert fakes.summarizer.summarize.call_args.kwargs["data"] == mock_file


def test_handle_document_missing_file_size(message_factory, mocker):
    """Test that a document with no file_size is rejected."""
    msg = message_factory(content_type="document")
    msg.document.file_size = None
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_document(msg, user)

    fakes.bot.reply_to.assert_called_once_with(msg, "No document found.")
    fakes.summarizer.summarize_with_document.assert_not_called()


def test_handle_url_unsupported_pattern(message_factory, mocker):
    """Test that non-URL text is rejected."""
    msg = message_factory(content_type="text", text="This is not a url.")
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_url(msg, user, "This is not a url.")

    fakes.bot.send_message.assert_called_once_with(msg.chat.id, "No data to proceed.")
    fakes.summarizer.summarize_text.assert_not_called()


def test_classify_url_uppercase_youtube_host():
    """Test classify_url normalises uppercase YouTube hostnames to 'youtube'."""
    assert classify_url("https://YOUTU.BE/dQw4w9WgXcQ") == "youtube"
    assert classify_url("https://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ") == "youtube"


def test_classify_url_strips_www_prefix():
    """Test classify_url routes www-prefixed media hosts to their media kind.

    Regression: routing used to be duplicated, and the second classifier matched
    three literal lowercase prefixes. A www-prefixed Castro or youtu.be link was
    classified as media here, then failed the second check and reached the
    Gemini file upload with the URL string as its file path.
    """
    assert classify_url("https://www.castro.fm/episode/123") == "castro"
    assert classify_url("https://www.youtu.be/dQw4w9WgXcQ") == "youtube"


def test_classify_url_castro_non_episode_path_is_web():
    """Test classify_url only treats Castro /episode/ paths as media."""
    assert classify_url("https://castro.fm/about") == "web"


def test_classify_url_malformed_no_host():
    """Test classify_url returns None for URLs with no parseable hostname."""
    assert classify_url("https://") is None


def test_classify_url_rejects_non_http_scheme():
    """Test classify_url returns None for non-http(s) schemes."""
    assert classify_url("ftp://example.com/file.txt") is None


def test_classify_url_returns_none_for_unparseable_authority():
    """Test classify_url returns None when urlsplit rejects the authority.

    urlsplit raises ValueError on bracket-malformed hosts. Left uncaught it
    escapes handle_url's kind check and reaches handle_message's catch-all, so
    the user sees "Unexpected: ValueError" instead of "No data to proceed.".
    """
    assert classify_url("https://[") is None
    assert classify_url("http://[::1") is None


def test_classify_url_http_youtube_is_web():
    """Test classify_url only treats https media hosts as media."""
    assert classify_url("http://youtube.com/watch?v=dQw4w9WgXcQ") == "web"


def test_handle_url_youtube_pattern(message_factory, mocker):
    """Test that YouTube URLs trigger summarize."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    msg = message_factory(content_type="text", text=url)
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_url(msg, user, url)

    assert fakes.summarizer.summarize.call_args.kwargs["data"] == url


def test_handle_url_castro_pattern(message_factory, mocker):
    """Test that Castro URLs trigger summarize."""
    url = "https://castro.fm/episode/123"
    msg = message_factory(content_type="text", text=url)
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_url(msg, user, url)

    assert fakes.summarizer.summarize.call_args.kwargs["data"] == url


def test_handle_url_other_http_pattern(message_factory, mocker):
    """Test that other URLs preflight quota, parse, then summarize with parsed text."""
    url = "https://example.com/article"
    msg = message_factory(content_type="text", text=url)
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()
    fakes.quota_manager.check_quota.return_value = True
    fakes.web_parser.parse.return_value = PrefixedText(
        text="Parsed page content.",
        prefix="🌐",
    )
    fakes.summarizer.summarize_text.return_value = "Summary text."

    handlers.handle_url(msg, user, url)

    fakes.web_parser.parse.assert_called_once_with(url)
    assert (
        fakes.summarizer.summarize_text.call_args.kwargs["text"]
        == "Parsed page content."
    )
    answer = fakes.messenger.send_answer.call_args.args[1]
    assert answer.startswith("🌐")
    assert "Summary text." in answer


def test_handle_url_web_preflight_blocks_before_parse_url(message_factory, mocker):
    """Test that quota preflight blocks Tavily IO for over-quota users."""
    url = "https://example.com/article"
    msg = message_factory(content_type="text", text=url)
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()
    fakes.quota_manager.check_quota.side_effect = LimitExceededError

    with pytest.raises(LimitExceededError):
        handlers.handle_url(msg, user, url)

    fakes.web_parser.parse.assert_not_called()
    fakes.summarizer.summarize_text.assert_not_called()


def test_handle_url_web_parse_error_skips_summarize(message_factory, mocker):
    """Test that WebParseError from parse_url short-circuits before summarize_text."""
    url = "https://example.com/article"
    msg = message_factory(content_type="text", text=url)
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()
    fakes.quota_manager.check_quota.return_value = True
    fakes.web_parser.parse.side_effect = WebParseError("boom")

    with pytest.raises(WebParseError):
        handlers.handle_url(msg, user, url)

    fakes.summarizer.summarize_text.assert_not_called()


def test_handle_voice_happy_path(message_factory, mocker):
    """Test successful voice message processing."""
    msg = message_factory(content_type="voice")
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock(
        approved=True,
        summarizing_model="model",
        prompt_key_for_summary="prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    fakes.messenger.get_file_with_retry.return_value = mock_file

    handlers.handle_voice(msg, user)

    assert fakes.summarizer.summarize.call_args.kwargs["data"] == mock_file


def test_handle_voice_too_big(message_factory, mocker):
    """Test voice message rejection when file exceeds limit (20MB)."""
    msg = message_factory(content_type="voice")
    msg.voice.file_size = 21 * 1024 * 1024
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_voice(msg, user)

    fakes.bot.reply_to.assert_called_once_with(msg, "File is too big.")


def test_handle_voice_missing_info(message_factory, mocker):
    """Test voice message rejection when voice attribute is missing."""
    msg = message_factory(content_type="text")
    msg.content_type = "voice"
    msg.voice = None
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_voice(msg, user)

    fakes.bot.reply_to.assert_called_once_with(msg, "No voice message found.")


def test_handle_video_happy_path_cleans_up_download(message_factory, mocker):
    """Test video processing cleans up the downloaded temporary file."""
    msg = message_factory(content_type="video")
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock(
        approved=True,
        summarizing_model="model",
        prompt_key_for_summary="prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    fakes.messenger.get_file_with_retry.return_value = mock_file
    fakes.downloader.download_tg.return_value = "downloaded.mp4"
    mocker.patch("handlers.generate_temporary_name", return_value="compressed.ogg")
    mocker.patch("handlers.compress_audio")
    fakes.summarizer.summarize.return_value = "summary"
    mock_clean_up = mocker.patch("handlers.clean_up")

    handlers.handle_video(msg, user)

    assert mock_clean_up.call_args_list == [
        mocker.call(file="downloaded.mp4"),
        mocker.call(file="compressed.ogg"),
    ]


def test_handle_video_note_happy_path_cleans_up_download(message_factory, mocker):
    """Test video note processing cleans up the downloaded temporary file."""
    msg = message_factory(content_type="video_note")
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock(
        approved=True,
        summarizing_model="model",
        prompt_key_for_summary="prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    fakes.messenger.get_file_with_retry.return_value = mock_file
    fakes.downloader.download_tg.return_value = "downloaded.mp4"
    mocker.patch("handlers.generate_temporary_name", return_value="compressed.ogg")
    mocker.patch("handlers.compress_audio")
    fakes.summarizer.summarize.return_value = "summary"
    mock_clean_up = mocker.patch("handlers.clean_up")

    handlers.handle_video_note(msg, user)

    assert mock_clean_up.call_args_list == [
        mocker.call(file="downloaded.mp4"),
        mocker.call(file="compressed.ogg"),
    ]


def test_handle_video_cleans_up_compressed_file_when_summarize_raises(
    message_factory,
    mocker,
):
    """Test the compressed temp file is removed even if summarize() raises early.

    summarize()'s preflight quota check can raise LimitExceededError before its
    own cleanup runs, so _handle_video_like must clean up the file it created.
    """
    msg = message_factory(content_type="video")
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock(
        approved=True,
        summarizing_model="model",
        prompt_key_for_summary="prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    fakes.messenger.get_file_with_retry.return_value = mock_file
    fakes.downloader.download_tg.return_value = "downloaded.mp4"
    mocker.patch("handlers.generate_temporary_name", return_value="compressed.ogg")
    mocker.patch("handlers.compress_audio")
    fakes.summarizer.summarize.side_effect = LimitExceededError("blocked")
    mock_clean_up = mocker.patch("handlers.clean_up")

    with pytest.raises(LimitExceededError):
        handlers.handle_video(msg, user)

    assert mock_clean_up.call_args_list == [
        mocker.call(file="downloaded.mp4"),
        mocker.call(file="compressed.ogg"),
    ]


def test_handle_video_note_file_too_large(message_factory, mocker):
    """Test video note rejection when file exceeds 20MB limit."""
    msg = message_factory(content_type="video_note")
    msg.video_note.file_size = 21 * 1024 * 1024
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_video_note(msg, user)

    fakes.bot.reply_to.assert_called_once_with(msg, "File is too big.")


def test_handle_video_file_too_large(message_factory, mocker):
    """Test video rejection when file exceeds 20MB limit."""
    msg = message_factory(content_type="video")
    msg.video.file_size = 21 * 1024 * 1024
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_video(msg, user)

    fakes.bot.reply_to.assert_called_once_with(msg, "File is too big.")


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
