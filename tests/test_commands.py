from main import (
    handle_info,
    handle_limit,
    handle_myinfo,
    handle_set_prompt_strategy,
    handle_set_summarizing_model,
    handle_set_target_language,
    handle_start,
    handle_toggle_transcription,
    handle_toggle_yt_transcription,
    proceed_set_prompt_strategy,
    proceed_set_summarizing_model,
    proceed_set_target_language,
)
from models import UsersOrm


def test_handle_start_new_user(message_factory, mocker):
    """Test /start for a new user (registration)."""
    msg = message_factory(content_type="text", text="/start")
    mock_register = mocker.patch("main.register_user", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    handle_start(msg)

    mock_register.assert_called_once()
    mock_send.assert_called_once()
    assert "Hi there" in mock_send.call_args[0][1]


def test_handle_start_existing_user(message_factory, mocker):
    """Test /start for an existing user."""
    msg = message_factory(content_type="text", text="/start")
    mocker.patch("main.register_user", return_value=False)
    mock_send = mocker.patch("main.bot.send_message")

    handle_start(msg)

    assert "You are good to go!" in mock_send.call_args[0][1]


def test_handle_start_missing_user(message_factory, mocker):
    """Test /start rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="/start")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_register = mocker.patch("main.register_user")

    handle_start(msg)

    mock_reply.assert_called_once_with(msg, "User information is missing.")
    mock_register.assert_not_called()


def test_handle_info(message_factory, mocker):
    """Test /info command."""
    msg = message_factory(content_type="text", text="/info")
    mock_send = mocker.patch("main.bot.send_message")

    handle_info(msg)

    assert str(msg.from_user.id) in mock_send.call_args[0][1]


def test_handle_info_missing_user(message_factory, mocker):
    """Test /info rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="/info")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")

    handle_info(msg)

    mock_reply.assert_called_once_with(msg, "User information is missing.")


def test_handle_myinfo(message_factory, mocker):
    """Test /myinfo command."""
    msg = message_factory(content_type="text", text="/myinfo")
    mock_user = UsersOrm(
        user_id=123,
        approved=True,
        target_language="English",
        summarizing_model="gemini-2.5-flash",
        prompt_key_for_summary="basic",
        use_yt_transcription=False,
        use_transcription=False,
        daily_limit=10,
    )
    mocker.patch("main.select_user", return_value=mock_user)
    mocker.patch("main.get_remaining_quota", return_value=7)
    mock_send = mocker.patch("main.bot.send_message")

    handle_myinfo(msg)

    content = mock_send.call_args[0][1]
    assert "Approved: True" in content
    assert "Target language: English" in content
    assert "Daily limit: 10" in content
    assert "Remaining quota: 7" in content


def test_handle_myinfo_missing_user(message_factory, mocker):
    """Test /myinfo rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="/myinfo")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")

    handle_myinfo(msg)

    mock_reply.assert_called_once_with(msg, "User information is missing.")


def test_handle_limit(message_factory, mocker):
    """Test /limit command."""
    msg = message_factory(content_type="text", text="/limit")
    mock_user = mocker.MagicMock(user_id=123, daily_limit=20)
    mocker.patch("main.select_user", return_value=mock_user)
    mocker.patch("main.get_remaining_quota", return_value=15)
    mock_send = mocker.patch("main.bot.send_message")

    handle_limit(msg)

    assert "Remaining limit: 15" in mock_send.call_args[0][1]


def test_handle_limit_missing_user(message_factory, mocker):
    """Test /limit silently returns when Telegram user metadata is absent."""
    msg = message_factory(content_type="text", text="/limit")
    msg.from_user = None
    mock_select = mocker.patch("main.select_user")

    handle_limit(msg)

    mock_select.assert_not_called()


def test_handle_toggle_transcription(message_factory, mocker):
    """Test /toggle_transcription."""
    msg = message_factory(content_type="text")
    mock_user = UsersOrm(user_id=123, use_transcription=False)
    mocker.patch("main.select_user", return_value=mock_user)
    mock_toggle = mocker.patch("main.toggle_transcription")
    mock_send = mocker.patch("main.bot.send_message")

    handle_toggle_transcription(msg)

    mock_toggle.assert_called_once_with(msg.from_user.id)
    assert "Transcription enabled" in mock_send.call_args[0][1]


def test_handle_toggle_transcription_missing_user(message_factory, mocker):
    """Test /toggle_transcription rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_toggle = mocker.patch("main.toggle_transcription")

    handle_toggle_transcription(msg)

    mock_reply.assert_called_once_with(msg, "User information is missing.")
    mock_toggle.assert_not_called()


def test_handle_toggle_yt_transcription(message_factory, mocker):
    """Test /toggle_yt_transcription."""
    msg = message_factory(content_type="text")
    mock_user = UsersOrm(user_id=123, use_yt_transcription=False)
    mocker.patch("main.select_user", return_value=mock_user)
    mock_toggle = mocker.patch("main.toggle_yt_transcription")
    mock_send = mocker.patch("main.bot.send_message")

    handle_toggle_yt_transcription(msg)

    mock_toggle.assert_called_once_with(msg.from_user.id)
    assert "YT transcription enabled" in mock_send.call_args[0][1]


def test_handle_toggle_yt_transcription_missing_user(message_factory, mocker):
    """Test /toggle_yt_transcription rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_toggle = mocker.patch("main.toggle_yt_transcription")

    handle_toggle_yt_transcription(msg)

    mock_reply.assert_called_once_with(msg, "User information is missing.")
    mock_toggle.assert_not_called()


def test_handle_set_target_language(message_factory, mocker):
    """Test /set_target_language shows keyboard."""
    msg = message_factory(content_type="text")
    mock_send = mocker.patch("main.bot.send_message")
    mock_register = mocker.patch("main.bot.register_next_step_handler")

    handle_set_target_language(msg)

    assert "Select target language" in mock_send.call_args[0][1]
    assert mock_register.called


def test_proceed_set_target_language_success(message_factory, mocker):
    """Test successful language selection."""
    msg = message_factory(content_type="text", text="Russian")
    mocker.patch("main.set_target_language", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_target_language(msg)

    assert "The target language is set to Russian" in mock_send.call_args[0][1]


def test_proceed_set_target_language_missing_input(message_factory, mocker):
    """Test target language selection fails fast when user or text is missing."""
    msg = message_factory(content_type="text", text="Russian")
    msg.text = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_set_language = mocker.patch("main.set_target_language")

    proceed_set_target_language(msg)

    mock_reply.assert_called_once_with(msg, "User information or language is missing.")
    mock_set_language.assert_not_called()


def test_proceed_set_target_language_invalid_choice(message_factory, mocker):
    """Test invalid target language returns a clear user-facing message."""
    msg = message_factory(content_type="text", text="Klingon")
    mocker.patch("main.set_target_language", return_value=False)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_target_language(msg)

    mock_send.assert_called_once_with(msg.chat.id, "Unknown language")


def test_handle_set_summarizing_model(message_factory, mocker):
    """Test /set_summarizing_model shows keyboard."""
    msg = message_factory(content_type="text")
    mock_send = mocker.patch("main.bot.send_message")
    mock_register = mocker.patch("main.bot.register_next_step_handler")

    handle_set_summarizing_model(msg)

    assert "Select summarizing model" in mock_send.call_args[0][1]
    assert mock_register.called


def test_proceed_set_summarizing_model_success(message_factory, mocker):
    """Test successful model selection."""
    msg = message_factory(content_type="text", text="Gemini 2.5 Flash")
    mocker.patch("main.set_summarizing_model", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_summarizing_model(msg)

    assert "The summarizing model is set to Gemini 2.5 Flash" in mock_send.call_args[0][1]


def test_proceed_set_summarizing_model_missing_input(message_factory, mocker):
    """Test model selection fails fast when user or text is missing."""
    msg = message_factory(content_type="text", text="gemini-2.5-flash")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_set_model = mocker.patch("main.set_summarizing_model")

    proceed_set_summarizing_model(msg)

    mock_reply.assert_called_once_with(msg, "User information or model is missing.")
    mock_set_model.assert_not_called()


def test_proceed_set_summarizing_model_invalid_choice(message_factory, mocker):
    """Test invalid label short-circuits before calling set_summarizing_model."""
    msg = message_factory(content_type="text", text="Gemini 4 Pro")
    mock_set_model = mocker.patch("main.set_summarizing_model")
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_summarizing_model(msg)

    mock_send.assert_called_once_with(msg.chat.id, "Unknown model")
    mock_set_model.assert_not_called()


def test_handle_set_prompt_strategy(message_factory, mocker):
    """Test /set_prompt_strategy shows keyboard."""
    msg = message_factory(content_type="text")
    mock_send = mocker.patch("main.bot.send_message")
    mock_register = mocker.patch("main.bot.register_next_step_handler")

    handle_set_prompt_strategy(msg)

    assert "Select summarization strategy" in mock_send.call_args[0][1]
    assert mock_register.called


def test_proceed_set_prompt_strategy_success(message_factory, mocker):
    """Test successful strategy selection."""
    msg = message_factory(content_type="text", text="Detailed Summary")
    mock_set_strategy = mocker.patch("main.set_prompt_strategy", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_prompt_strategy(msg)

    mock_set_strategy.assert_called_once_with(msg.from_user.id, "basic_prompt_for_transcript")
    assert "The prompt strategy is set to Detailed Summary" in mock_send.call_args[0][1]


def test_proceed_set_prompt_strategy_persistence_failure(message_factory, mocker):
    """Test that a DB failure from set_prompt_strategy sends an error, not success."""
    msg = message_factory(content_type="text", text="Detailed Summary")
    mocker.patch("main.set_prompt_strategy", return_value=False)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_prompt_strategy(msg)

    mock_send.assert_called_once_with(msg.chat.id, "Failed to update prompt strategy.")


def test_proceed_set_prompt_strategy_missing_input(message_factory, mocker):
    """Test prompt selection fails fast when user or text is missing."""
    msg = message_factory(content_type="text", text="basic")
    msg.text = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_set_strategy = mocker.patch("main.set_prompt_strategy")

    proceed_set_prompt_strategy(msg)

    mock_reply.assert_called_once_with(msg, "User information or strategy is missing.")
    mock_set_strategy.assert_not_called()


def test_proceed_set_prompt_strategy_invalid_choice(message_factory, mocker):
    """Test invalid prompt strategy returns a clear user-facing message."""
    msg = message_factory(content_type="text", text="enterprise")
    mock_set_strategy = mocker.patch("main.set_prompt_strategy")
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_prompt_strategy(msg)

    mock_send.assert_called_once_with(msg.chat.id, "Unknown strategy")
    mock_set_strategy.assert_not_called()
