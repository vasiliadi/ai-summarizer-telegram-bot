from types import SimpleNamespace

import pytest
from telebot import types

from domain import PrefixedText
from exceptions import LimitExceededError, WebParseError
from handlers import MessageHandlers

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


# Every media handler funnels its size check through the one _fetch_media guard,
# so the four content types share a single test rather than one apiece.
@pytest.mark.parametrize(
    ("content_type", "handler_name"),
    [
        ("audio", "handle_audio"),
        ("voice", "handle_voice"),
        ("video", "handle_video"),
        ("video_note", "handle_video_note"),
    ],
)
def test_handle_media_rejects_file_over_the_telegram_cap(
    message_factory,
    mocker,
    content_type,
    handler_name,
):
    """Test each media handler rejects a file above Telegram's 20MB getFile cap."""
    msg = message_factory(content_type=content_type)
    getattr(msg, content_type).file_size = 21 * 1024 * 1024
    handlers, fakes = _make_handlers(mocker)

    getattr(handlers, handler_name)(msg, mocker.MagicMock())

    fakes.bot.reply_to.assert_called_once_with(msg, "File is too big.")
    # The cap exists because Telegram's getFile refuses files above it, so the
    # guard has to short-circuit before the fetch, not just before summarizing.
    fakes.messenger.get_file_with_retry.assert_not_called()
    fakes.summarizer.summarize.assert_not_called()


@pytest.mark.parametrize(
    ("content_type", "handler_name"),
    [("audio", "handle_audio"), ("voice", "handle_voice")],
)
def test_handle_media_summarizes_the_fetched_file(
    message_factory,
    mocker,
    content_type,
    handler_name,
):
    """Test audio and voice hand the fetched Telegram file straight to summarize."""
    msg = message_factory(content_type=content_type)
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock(
        approved=True,
        summarizing_model="model",
        prompt_key_for_summary="prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    fakes.messenger.get_file_with_retry.return_value = mock_file

    getattr(handlers, handler_name)(msg, user)

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


def test_handle_voice_missing_info(message_factory, mocker):
    """Test voice message rejection when voice attribute is missing."""
    msg = message_factory(content_type="text")
    msg.content_type = "voice"
    msg.voice = None
    handlers, fakes = _make_handlers(mocker)
    user = mocker.MagicMock()

    handlers.handle_voice(msg, user)

    fakes.bot.reply_to.assert_called_once_with(msg, "No voice message found.")


@pytest.mark.parametrize(
    ("content_type", "handler_name"),
    [("video", "handle_video"), ("video_note", "handle_video_note")],
)
def test_handle_video_like_cleans_up_both_temp_files(
    message_factory,
    mocker,
    content_type,
    handler_name,
):
    """Test video and video note both clean up the download and the compressed copy."""
    msg = message_factory(content_type=content_type)
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

    getattr(handlers, handler_name)(msg, user)

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
