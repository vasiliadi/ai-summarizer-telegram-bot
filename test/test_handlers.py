from telebot import types
from tenacity import RetryError

from exceptions import LimitExceededError
from main import handle_message, process_message_content


def test_unauthorized_user(message_factory, mocker):
    """Test that unauthorized users receive an access denied message."""
    msg = message_factory(content_type="text", text="Hello")
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=False))
    mock_send_message = mocker.patch("main.bot.send_message")

    handle_message(msg)

    mock_send_message.assert_called_once_with(msg.chat.id, "You are not approved.")


def test_handle_message_missing_user(message_factory, mocker):
    """Test handle_message rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="Hello")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")

    handle_message(msg)

    mock_reply.assert_called_once_with(msg, "User information is missing.")


def test_successful_document_flow(message_factory, mocker):
    """Test a valid user sending a document receives the generated summary."""
    msg = message_factory(content_type="document")
    mock_user = mocker.MagicMock(
        approved=True,
        summarizing_model="mock-model",
        prompt_key_for_summary="mock-prompt",
        target_language="English",
    )
    mock_file = mocker.MagicMock(spec=types.File)
    mocker.patch("main.select_user", return_value=mock_user)
    mocker.patch("handlers.get_file_with_retry", return_value=mock_file)
    mocker.patch(
        "handlers.summarize_with_document",
        return_value="Here is your awesome summary",
    )
    mock_send_answer = mocker.patch("handlers.send_answer")

    handle_message(msg)

    mock_send_answer.assert_called_once_with(msg, "Here is your awesome summary")


def test_process_message_content_dispatches_audio(message_factory, mocker):
    """Test audio messages route to handle_audio."""
    msg = message_factory(content_type="audio")
    user = mocker.MagicMock()
    mock_audio = mocker.patch("main.handle_audio")

    process_message_content(msg, user)

    mock_audio.assert_called_once_with(msg, user)


def test_process_message_content_dispatches_allowed_document(message_factory, mocker):
    """Test supported document MIME types route to handle_document."""
    msg = message_factory(content_type="document")
    user = mocker.MagicMock()
    mock_document = mocker.patch("main.handle_document")

    process_message_content(msg, user)

    mock_document.assert_called_once_with(msg, user)


def test_process_message_content_dispatches_application_rtf_document(
    message_factory,
    mocker,
):
    """Test application/rtf documents route to handle_document."""
    msg = message_factory(content_type="document")
    msg.document.mime_type = "application/rtf"
    user = mocker.MagicMock()
    mock_document = mocker.patch("main.handle_document")

    process_message_content(msg, user)

    mock_document.assert_called_once_with(msg, user)


def test_process_message_content_sends_textless_fallback(message_factory, mocker):
    """Test unsupported non-text messages produce a clear fallback response."""
    msg = message_factory(content_type="document")
    msg.document.mime_type = "application/zip"
    msg.text = None
    user = mocker.MagicMock()
    mock_send = mocker.patch("main.bot.send_message")

    process_message_content(msg, user)

    mock_send.assert_called_once_with(msg.chat.id, "No text to process.")


def test_handle_audio_file_too_large(message_factory, mocker):
    """Test that audio files over 20MB are rejected."""
    msg = message_factory(content_type="audio")
    msg.audio.file_size = 25_000_000
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_reply_to = mocker.patch("main.bot.reply_to")
    mock_summarize = mocker.patch("handlers.summarize")

    handle_message(msg)

    mock_reply_to.assert_called_once_with(msg, "File is too big.")
    mock_summarize.assert_not_called()


def test_handle_document_missing_file_info(message_factory, mocker):
    """Test that documents missing required file info are rejected."""
    msg = message_factory(content_type="document")
    msg.document.file_id = None
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_reply_to = mocker.patch("main.bot.reply_to")
    mock_summarize_with_document = mocker.patch("handlers.summarize_with_document")

    handle_message(msg)

    mock_reply_to.assert_called_once_with(msg, "No document found.")
    mock_summarize_with_document.assert_not_called()


def test_handle_url_unsupported_pattern(message_factory, mocker):
    """Test that non-URL text is rejected."""
    msg = message_factory(content_type="text", text="This is not a url.")
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_send_message = mocker.patch("main.bot.send_message")
    mock_summarize_webpage = mocker.patch("handlers.summarize_webpage")

    handle_message(msg)

    mock_send_message.assert_called_once_with(msg.chat.id, "No data to proceed.")
    mock_summarize_webpage.assert_not_called()


def test_handle_url_youtube_pattern(message_factory, mocker):
    """Test that YouTube URLs trigger summarize."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    msg = message_factory(content_type="text", text=url)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_summarize = mocker.patch("handlers.summarize")
    mocker.patch("handlers.send_answer")

    handle_message(msg)

    assert mock_summarize.call_args.kwargs["data"] == url


def test_handle_url_youtube_pattern_without_www(message_factory, mocker):
    """Test that non-www YouTube URLs still trigger summarize."""
    url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
    msg = message_factory(content_type="text", text=url)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_summarize = mocker.patch("handlers.summarize")
    mocker.patch("handlers.send_answer")

    handle_message(msg)

    assert mock_summarize.call_args.kwargs["data"] == url


def test_handle_url_castro_pattern(message_factory, mocker):
    """Test that Castro URLs trigger summarize."""
    url = "https://castro.fm/episode/123"
    msg = message_factory(content_type="text", text=url)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_summarize = mocker.patch("handlers.summarize")
    mocker.patch("handlers.send_answer")

    handle_message(msg)

    assert mock_summarize.call_args.kwargs["data"] == url


def test_handle_url_other_http_pattern(message_factory, mocker):
    """Test that other URLs trigger summarize_webpage."""
    url = "https://example.com/article"
    msg = message_factory(content_type="text", text=url)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_summarize_webpage = mocker.patch("handlers.summarize_webpage")
    mocker.patch("handlers.send_answer")

    handle_message(msg)

    assert mock_summarize_webpage.call_args.kwargs["content"] == url


def test_handle_voice_happy_path(message_factory, mocker):
    """Test successful voice message processing."""
    msg = message_factory(content_type="voice")
    mocker.patch(
        "main.select_user",
        return_value=mocker.MagicMock(
            approved=True,
            use_transcription=False,
            summarizing_model="model",
            prompt_key_for_summary="prompt",
            target_language="English",
        ),
    )
    mock_file = mocker.MagicMock(spec=types.File)
    mocker.patch("handlers.get_file_with_retry", return_value=mock_file)
    mock_summarize = mocker.patch("handlers.summarize")
    mocker.patch("handlers.send_answer")

    handle_message(msg)

    assert mock_summarize.call_args.kwargs["data"] == mock_file


def test_handle_voice_too_big(message_factory, mocker):
    """Test voice message rejection when file exceeds limit (20MB)."""
    msg = message_factory(content_type="voice")
    msg.voice.file_size = 21 * 1024 * 1024
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_bot_handlers = mocker.patch("handlers.bot")

    handle_message(msg)

    mock_bot_handlers.reply_to.assert_called_once_with(msg, "File is too big.")


def test_handle_voice_missing_info(message_factory, mocker):
    """Test voice message rejection when voice attribute is missing."""
    msg = message_factory(content_type="text")
    msg.content_type = "voice"
    msg.voice = None
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mock_bot_handlers = mocker.patch("handlers.bot")

    handle_message(msg)

    mock_bot_handlers.reply_to.assert_called_once_with(msg, "No voice message found.")


def test_handle_video_happy_path_cleans_up_download(message_factory, mocker):
    """Test video processing cleans up the downloaded temporary file."""
    msg = message_factory(content_type="video")
    mocker.patch(
        "main.select_user",
        return_value=mocker.MagicMock(
            approved=True,
            use_transcription=False,
            summarizing_model="model",
            prompt_key_for_summary="prompt",
            target_language="English",
        ),
    )
    mock_file = mocker.MagicMock(spec=types.File)
    mocker.patch("handlers.get_file_with_retry", return_value=mock_file)
    mocker.patch("handlers.download_tg", return_value="downloaded.mp4")
    mocker.patch("handlers.generate_temporary_name", return_value="compressed.ogg")
    mocker.patch("handlers.compress_audio")
    mocker.patch("handlers.summarize", return_value="summary")
    mocker.patch("handlers.send_answer")
    mock_clean_up = mocker.patch("handlers.clean_up")

    handle_message(msg)

    mock_clean_up.assert_called_once_with(file="downloaded.mp4")


def test_handle_video_note_happy_path_cleans_up_download(message_factory, mocker):
    """Test video note processing cleans up the downloaded temporary file."""
    msg = message_factory(content_type="video_note")
    mocker.patch(
        "main.select_user",
        return_value=mocker.MagicMock(
            approved=True,
            use_transcription=False,
            summarizing_model="model",
            prompt_key_for_summary="prompt",
            target_language="English",
        ),
    )
    mock_file = mocker.MagicMock(spec=types.File)
    mocker.patch("handlers.get_file_with_retry", return_value=mock_file)
    mocker.patch("handlers.download_tg", return_value="downloaded.mp4")
    mocker.patch("handlers.generate_temporary_name", return_value="compressed.ogg")
    mocker.patch("handlers.compress_audio")
    mocker.patch("handlers.summarize", return_value="summary")
    mocker.patch("handlers.send_answer")
    mock_clean_up = mocker.patch("handlers.clean_up")

    handle_message(msg)

    mock_clean_up.assert_called_once_with(file="downloaded.mp4")


def test_handle_video_cleans_up_compressed_file_when_compression_fails(
    message_factory,
    mocker,
):
    """Test video processing cleans up temp files when compression fails."""
    msg = message_factory(content_type="video")
    mocker.patch(
        "main.select_user",
        return_value=mocker.MagicMock(
            approved=True,
            use_transcription=False,
            summarizing_model="model",
            prompt_key_for_summary="prompt",
            target_language="English",
        ),
    )
    mock_file = mocker.MagicMock(spec=types.File)
    mocker.patch("handlers.get_file_with_retry", return_value=mock_file)
    mocker.patch("handlers.download_tg", return_value="downloaded.mp4")
    mocker.patch("handlers.generate_temporary_name", return_value="compressed.ogg")
    mocker.patch("handlers.compress_audio", side_effect=RuntimeError("compression failed"))
    mocker.patch("main.capture_exception")
    mocker.patch("main.bot.reply_to")
    mock_clean_up = mocker.patch("handlers.clean_up")

    handle_message(msg)

    mock_clean_up.assert_has_calls(
        [
            mocker.call(file="compressed.ogg"),
            mocker.call(file="downloaded.mp4"),
        ],
    )


def test_handle_message_limit_exceeded(message_factory, mocker):
    """Test handle_message when rate limit is exceeded."""
    msg = message_factory(content_type="text", text="http://youtube.com/watch?v=123")
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mocker.patch(
        "main.process_message_content",
        side_effect=LimitExceededError("Rate limit exceeded"),
    )
    mock_reply = mocker.patch("main.bot.reply_to")

    handle_message(msg)

    mock_reply.assert_called_once_with(
        msg,
        "Daily limit has been exceeded, try again tomorrow.",
    )


def test_handle_message_retry_error(message_factory, mocker):
    """Test handle_message when retries are exhausted."""
    msg = message_factory(content_type="text", text="http://youtube.com/watch?v=123")
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mocker.patch(
        "main.process_message_content",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mock_reply = mocker.patch("main.bot.reply_to")

    handle_message(msg)

    mock_reply.assert_called_once_with(
        msg,
        "An error occurred during execution. Please try again in 10 minutes.",
    )


def test_handle_message_unexpected_error(message_factory, mocker):
    """Test handle_message when an unexpected exception occurs."""
    msg = message_factory(content_type="text", text="http://youtube.com/watch?v=123")
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))
    mocker.patch("main.process_message_content", side_effect=Exception("BOOM"))
    mock_reply = mocker.patch("main.bot.reply_to")

    handle_message(msg)

    mock_reply.assert_called_once_with(msg, "Unexpected: Exception")
