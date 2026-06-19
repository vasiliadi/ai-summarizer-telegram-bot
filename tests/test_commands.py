import pytest

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


@pytest.mark.parametrize(
    ("handler", "expected_text"),
    [
        (handle_set_target_language, "Select target language"),
        (handle_set_summarizing_model, "Select summarizing model"),
        (handle_set_prompt_strategy, "Select summarization strategy"),
        (handle_set_thinking_level, "Select thinking level"),
    ],
)
def test_handle_set_setting_shows_keyboard(
    message_factory, mocker, handler, expected_text
):
    """Test each /set_* command shows its selection keyboard."""
    msg = message_factory(content_type="text")
    mock_send = mocker.patch("main.bot.send_message")
    mock_register = mocker.patch("main.bot.register_next_step_handler")

    handler(msg)

    assert expected_text in mock_send.call_args[0][1]
    assert mock_register.called


def test_proceed_set_target_language_success(message_factory, mocker):
    """Test successful language selection."""
    msg = message_factory(content_type="text", text="Russian")
    mocker.patch("main.set_target_language", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_target_language(msg)

    assert "The target language is set to Russian" in mock_send.call_args[0][1]


def test_proceed_set_summarizing_model_success(message_factory, mocker):
    """Test successful model selection."""
    msg = message_factory(content_type="text", text="Gemini 3.5 Flash")
    mock_set_model = mocker.patch("main.set_summarizing_model", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_summarizing_model(msg)

    mock_set_model.assert_called_once_with(msg.from_user.id, "gemini-3.5-flash")
    assert "The summarizing model is set to Gemini 3.5 Flash" in mock_send.call_args[0][1]


def test_proceed_set_prompt_strategy_success(message_factory, mocker):
    """Test successful strategy selection."""
    msg = message_factory(content_type="text", text="Detailed Summary")
    mock_set_strategy = mocker.patch("main.set_prompt_strategy", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_prompt_strategy(msg)

    mock_set_strategy.assert_called_once_with(msg.from_user.id, "basic_prompt_for_transcript")
    assert "The prompt strategy is set to Detailed Summary" in mock_send.call_args[0][1]


def test_proceed_set_thinking_level_success(message_factory, mocker):
    """Test successful thinking level selection."""
    msg = message_factory(content_type="text", text="High")
    mock_set = mocker.patch("main.set_thinking_level", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_thinking_level(msg)

    mock_set.assert_called_once_with(msg.from_user.id, "HIGH")
    assert "The thinking level is set to High" in mock_send.call_args[0][1]


@pytest.mark.parametrize(
    ("proceed", "setter_path", "null_attr", "error_msg"),
    [
        (proceed_set_target_language, "main.set_target_language", "text", "User information or language is missing."),
        (proceed_set_summarizing_model, "main.set_summarizing_model", "from_user", "User information or model is missing."),
        (proceed_set_prompt_strategy, "main.set_prompt_strategy", "text", "User information or strategy is missing."),
        (proceed_set_thinking_level, "main.set_thinking_level", "text", "User information or level is missing."),
    ],
)
def test_proceed_set_setting_missing_input(
    message_factory, mocker, proceed, setter_path, null_attr, error_msg
):
    """Test each setting selection fails fast when user or text is missing."""
    msg = message_factory(content_type="text", text="Anything")
    setattr(msg, null_attr, None)
    mock_reply = mocker.patch("main.bot.reply_to")
    mock_setter = mocker.patch(setter_path)

    proceed(msg)

    mock_reply.assert_called_once_with(msg, error_msg)
    mock_setter.assert_not_called()


@pytest.mark.parametrize(
    ("proceed", "setter_path", "bad_text", "error_msg"),
    [
        (proceed_set_summarizing_model, "main.set_summarizing_model", "Gemini 4 Pro", "Unknown model"),
        (proceed_set_prompt_strategy, "main.set_prompt_strategy", "enterprise", "Unknown strategy"),
        (proceed_set_thinking_level, "main.set_thinking_level", "Ludicrous", "Unknown level"),
    ],
)
def test_proceed_set_setting_invalid_choice(
    message_factory, mocker, proceed, setter_path, bad_text, error_msg
):
    """Test an invalid label short-circuits before calling the setter."""
    msg = message_factory(content_type="text", text=bad_text)
    mock_setter = mocker.patch(setter_path)
    mock_send = mocker.patch("main.bot.send_message")

    proceed(msg)

    mock_send.assert_called_once_with(msg.chat.id, error_msg)
    mock_setter.assert_not_called()


def test_proceed_set_target_language_invalid_choice(message_factory, mocker):
    """Test an unknown language is rejected via the setter returning False."""
    msg = message_factory(content_type="text", text="Klingon")
    mocker.patch("main.set_target_language", return_value=False)
    mock_send = mocker.patch("main.bot.send_message")

    proceed_set_target_language(msg)

    mock_send.assert_called_once_with(msg.chat.id, "Unknown language")


@pytest.mark.parametrize(
    ("proceed", "setter_path", "valid_text", "error_msg"),
    [
        (proceed_set_summarizing_model, "main.set_summarizing_model", "Gemini 3.5 Flash", "Failed to update summarizing model."),
        (proceed_set_prompt_strategy, "main.set_prompt_strategy", "Detailed Summary", "Failed to update prompt strategy."),
        (proceed_set_thinking_level, "main.set_thinking_level", "High", "Failed to update thinking level."),
    ],
)
def test_proceed_set_setting_db_failure(
    message_factory, mocker, proceed, setter_path, valid_text, error_msg
):
    """Test a DB failure returns a clear user-facing message, not success."""
    msg = message_factory(content_type="text", text=valid_text)
    mocker.patch(setter_path, return_value=False)
    mock_send = mocker.patch("main.bot.send_message")

    proceed(msg)

    mock_send.assert_called_once_with(msg.chat.id, error_msg)
