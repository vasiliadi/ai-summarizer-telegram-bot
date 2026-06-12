from main import (
    handle_info,
    handle_myinfo,
    handle_set_prompt_strategy,
    handle_set_summarizing_model,
    handle_set_target_language,
    handle_set_thinking_level,
    handle_start,
    proceed_set_prompt_strategy,
    proceed_set_summarizing_model,
    proceed_set_target_language,
    proceed_set_thinking_level,
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
        summarizing_model="gemini-3.5-flash",
        prompt_key_for_summary="basic_prompt_for_transcript",
        daily_limit=10,
        thinking_level="MINIMAL",
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
    assert "Summarizing model: Gemini 3.5 Flash" in content
    assert "Thinking level: Minimal" in content
    assert "Prompt strategy: Detailed Summary" in content
    assert "YouTube transcript" not in content
    assert "Audio transcript" not in content


def test_handle_myinfo_missing_user(message_factory, mocker):
    """Test /myinfo rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="/myinfo")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")

    handle_myinfo(msg)

    mock_reply.assert_called_once_with(msg, "User information is missing.")


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
    msg = message_factory(content_type="text", text="Gemini 3.5 Flash")
    mock_set_model = mocker.patch("main.set_summarizing_model", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_summarizing_model(msg)

    mock_set_model.assert_called_once_with(msg.from_user.id, "gemini-3.5-flash")
    assert "The summarizing model is set to Gemini 3.5 Flash" in mock_send.call_args[0][1]


def test_proceed_set_summarizing_model_missing_input(message_factory, mocker):
    """Test model selection fails fast when user or text is missing."""
    msg = message_factory(content_type="text", text="gemini-3.5-flash")
    msg.from_user = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_set_model = mocker.patch("main.set_summarizing_model")

    proceed_set_summarizing_model(msg)

    mock_reply.assert_called_once_with(msg, "User information or model is missing.")
    mock_set_model.assert_not_called()


def test_proceed_set_summarizing_model_db_failure(message_factory, mocker):
    """Test DB failure returns a clear user-facing message."""
    msg = message_factory(content_type="text", text="Gemini 3.5 Flash")
    mocker.patch("main.set_summarizing_model", return_value=False)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_summarizing_model(msg)

    mock_send.assert_called_once_with(msg.chat.id, "Failed to update summarizing model.")


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


def test_handle_set_thinking_level(message_factory, mocker):
    """Test /set_thinking_level shows keyboard."""
    msg = message_factory(content_type="text")
    mock_send = mocker.patch("main.bot.send_message")
    mock_register = mocker.patch("main.bot.register_next_step_handler")

    handle_set_thinking_level(msg)

    assert "Select thinking level" in mock_send.call_args[0][1]
    assert mock_register.called


def test_proceed_set_thinking_level_success(message_factory, mocker):
    """Test successful thinking level selection."""
    msg = message_factory(content_type="text", text="High")
    mock_set = mocker.patch("main.set_thinking_level", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_thinking_level(msg)

    mock_set.assert_called_once_with(msg.from_user.id, "HIGH")
    assert "The thinking level is set to High" in mock_send.call_args[0][1]


def test_proceed_set_thinking_level_missing_input(message_factory, mocker):
    """Test thinking level selection fails fast when user or text is missing."""
    msg = message_factory(content_type="text", text="High")
    msg.text = None
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_set = mocker.patch("main.set_thinking_level")

    proceed_set_thinking_level(msg)

    mock_reply.assert_called_once_with(msg, "User information or level is missing.")
    mock_set.assert_not_called()


def test_proceed_set_thinking_level_invalid_choice(message_factory, mocker):
    """Test invalid label short-circuits before calling set_thinking_level."""
    msg = message_factory(content_type="text", text="Ludicrous")
    mock_set = mocker.patch("main.set_thinking_level")
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_thinking_level(msg)

    mock_send.assert_called_once_with(msg.chat.id, "Unknown level")
    mock_set.assert_not_called()


def test_proceed_set_thinking_level_db_failure(message_factory, mocker):
    """Test DB failure returns a clear user-facing message."""
    msg = message_factory(content_type="text", text="High")
    mocker.patch("main.set_thinking_level", return_value=False)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_thinking_level(msg)

    mock_send.assert_called_once_with(
        msg.chat.id,
        "Failed to update thinking level.",
    )
