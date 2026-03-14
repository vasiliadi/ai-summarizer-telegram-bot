
import config
from exceptions import LimitExceededError
from main import handle_message


def test_unauthorized_user(message_factory, mocker):
    """Test that unauthorized users receive an Access Denied message."""
    msg = message_factory(content_type="text", text="Hello")

    # Mock DB functions
    # main.py does: user = select_user(id); if not user.approved: bot.send_message
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=False))
    mocker.patch("main.check_auth", return_value=False)

    # Mock bot to capture send_message since main.py calls `bot.send_message`
    # instead of reply_to for unapproved users.
    mock_send_message = mocker.patch("main.bot.send_message")

    handle_message(msg)

    mock_send_message.assert_called_once_with(
        msg.chat.id,
        "You are not approved.",
    )


def test_rate_limited_user(message_factory, mocker):
    """Test that rate limited users receive a quota error message."""
    msg = message_factory(content_type="text", text="Hello")

    # Mock auth to succeed
    mocker.patch("main.check_auth", return_value=True)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(target_language="English", summarizing_model="test", prompt_key_for_summary="test"))

    # Mock the summarize_webpage, which is what handle_url calls for standard URLs
    # But wait, our message is standard text: "Hello", which will map to "Other URLs pattern" if it starts with http,
    # or "No data to proceed." if it doesn't.
    # We want to test general Limits, let's just make summarize_webpage raise the error.
    # Actually wait, `message.text.strip().split...` happens in `process_message_content`. Let's mock `process_message_content`.
    mocker.patch("main.process_message_content", side_effect=LimitExceededError("The daily limit for requests has been exceeded"))

    mock_reply_to = mocker.patch("main.bot.reply_to")

    handle_message(msg)

    # The limit exceeded error message
    mock_reply_to.assert_any_call(msg, "Daily limit has been exceeded, try again tomorrow.")


def test_successful_flow(message_factory, mocker):
    """Test a valid user sending a file gets processing and the correct summary."""
    msg = message_factory(content_type="document")

    # Mock auth and DB
    mocker.patch("main.check_auth", return_value=True)
    mock_user = mocker.MagicMock(
        use_transcription=False,
        use_yt_transcription=False,
        summarizing_model="mock-model",
        prompt_key_for_summary="mock-prompt",
        target_language="English",
    )
    mocker.patch("main.select_user", return_value=mock_user)

    # Mock bot interactions
    mocker.patch.object(config.bot, "reply_to")
    mock_send_answer = mocker.patch("handlers.send_answer")

    # Mock get_file
    mocker.patch("handlers.get_file_with_retry", return_value=mocker.MagicMock())

    # Mock summarize_with_document call
    mocker.patch("handlers.summarize_with_document", return_value="Here is your awesome summary")

    handle_message(msg)

    # The bot doesn't actually reply 'Processing...' in handle_message or handle_document natively based on the current implementation.
    # It just sends the answer once done. Wait, let me verify the file.
    # Ah, `handle_document` calls `get_file_with_retry`, then `summarize_with_document`, then `send_answer`.
    # Let's assert `send_answer` is called correctly.
    mock_send_answer.assert_called_once_with(msg, "Here is your awesome summary")


def test_handle_audio_file_too_large(message_factory, mocker):
    """Test that audio files over 20MB are rejected."""
    msg = message_factory(content_type="audio")
    msg.audio.file_size = 25000000  # 25MB

    mocker.patch("main.check_auth", return_value=True)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))

    mock_reply_to = mocker.patch("main.bot.reply_to")
    mock_summarize = mocker.patch("handlers.summarize")

    handle_message(msg)

    mock_reply_to.assert_called_once_with(msg, "File is too big.")
    mock_summarize.assert_not_called()


def test_handle_document_missing_file_info(message_factory, mocker):
    """Test that documents missing required file_info are rejected."""
    msg = message_factory(content_type="document")
    msg.document.file_id = None

    mocker.patch("main.check_auth", return_value=True)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))

    mock_reply_to = mocker.patch("main.bot.reply_to")
    mock_summarize_with_document = mocker.patch("handlers.summarize_with_document")

    handle_message(msg)

    mock_reply_to.assert_called_once_with(msg, "No document found.")
    mock_summarize_with_document.assert_not_called()


def test_handle_url_unsupported_pattern(message_factory, mocker):
    """Test that non-URL text is rejected."""
    msg = message_factory(content_type="text", text="This is not a url.")

    mocker.patch("main.check_auth", return_value=True)
    mocker.patch("main.select_user", return_value=mocker.MagicMock(approved=True))

    mock_send_message = mocker.patch("main.bot.send_message")
    mock_summarize_webpage = mocker.patch("handlers.summarize_webpage")

    handle_message(msg)

    # Check that main.bot.send_message is called with the chat ID from process_message_content -> handle_url
    mock_send_message.assert_called_once_with(msg.chat.id, "No data to proceed.")
    mock_summarize_webpage.assert_not_called()

