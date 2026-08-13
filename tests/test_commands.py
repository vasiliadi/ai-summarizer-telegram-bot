import pytest

from helpers import make_app
from models import UsersOrm


def test_handle_start_new_user(message_factory, mocker):
    """Test /start for a new user (registration)."""
    msg = message_factory(content_type="text", text="/start")
    app, fakes = make_app(mocker)
    fakes.user_repo.register_user.return_value = True

    app.handle_start(msg)

    fakes.user_repo.register_user.assert_called_once()
    fakes.bot.send_message.assert_called_once()
    assert "Hi there" in fakes.bot.send_message.call_args[0][1]


def test_handle_start_existing_user(message_factory, mocker):
    """Test /start for an existing user."""
    msg = message_factory(content_type="text", text="/start")
    app, fakes = make_app(mocker)
    fakes.user_repo.register_user.return_value = False

    app.handle_start(msg)

    assert "You are good to go!" in fakes.bot.send_message.call_args[0][1]


def test_handle_start_missing_user(message_factory, mocker):
    """Test /start rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="/start")
    msg.from_user = None
    app, fakes = make_app(mocker)

    app.handle_start(msg)

    fakes.bot.reply_to.assert_called_once_with(msg, "User information is missing.")
    fakes.user_repo.register_user.assert_not_called()


def test_handle_info(message_factory, mocker):
    """Test /info command."""
    msg = message_factory(content_type="text", text="/info")
    app, fakes = make_app(mocker)

    app.handle_info(msg)

    assert str(msg.from_user.id) in fakes.bot.send_message.call_args[0][1]


def test_handle_info_missing_user(message_factory, mocker):
    """Test /info rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="/info")
    msg.from_user = None
    app, fakes = make_app(mocker)

    app.handle_info(msg)

    fakes.bot.reply_to.assert_called_once_with(msg, "User information is missing.")


def test_handle_myinfo(message_factory, mocker):
    """Test /myinfo command."""
    msg = message_factory(content_type="text", text="/myinfo")
    app, fakes = make_app(mocker)
    mock_user = UsersOrm(
        user_id=123,
        approved=True,
        target_language="English",
        summarizing_model="gemini-3.7-flash",
        prompt_key_for_summary="basic_prompt_for_transcript",
        daily_limit=10,
        thinking_level="minimal",
    )
    fakes.user_repo.select_user.return_value = mock_user
    fakes.quota_manager.get_remaining_quota.return_value = 7

    app.handle_myinfo(msg)

    content = fakes.bot.send_message.call_args[0][1]
    assert "Approved: True" in content
    assert "Target language: English" in content
    assert "Daily limit: 10" in content
    assert "Remaining quota: 7" in content
    assert "Summarizing model: Gemini 3.7 Flash" in content
    assert "Thinking level: Minimal" in content
    assert "Prompt strategy: Detailed Summary" in content
    assert "YouTube transcript" not in content
    assert "Audio transcript" not in content


def test_handle_myinfo_missing_user(message_factory, mocker):
    """Test /myinfo rejects messages without Telegram user metadata."""
    msg = message_factory(content_type="text", text="/myinfo")
    msg.from_user = None
    app, fakes = make_app(mocker)

    app.handle_myinfo(msg)

    fakes.bot.reply_to.assert_called_once_with(msg, "User information is missing.")


@pytest.mark.parametrize(
    ("handler_name", "expected_text", "expected_next_step_name"),
    [
        (
            "handle_set_target_language",
            "Select target language",
            "proceed_set_target_language",
        ),
        (
            "handle_set_summarizing_model",
            "Select summarizing model",
            "proceed_set_summarizing_model",
        ),
        (
            "handle_set_prompt_strategy",
            "Select summarization strategy",
            "proceed_set_prompt_strategy",
        ),
        (
            "handle_set_thinking_level",
            "Select thinking level",
            "proceed_set_thinking_level",
        ),
    ],
)
def test_handle_set_setting_shows_keyboard(
    message_factory,
    mocker,
    handler_name,
    expected_text,
    expected_next_step_name,
):
    """Test each /set_* command shows its selection keyboard."""
    msg = message_factory(content_type="text")
    app, fakes = make_app(mocker)

    getattr(app, handler_name)(msg)

    assert expected_text in fakes.bot.send_message.call_args[0][1]
    fakes.bot.register_next_step_handler.assert_called_once_with(
        msg,
        getattr(app, expected_next_step_name),
    )


def test_proceed_set_target_language_success(message_factory, mocker):
    """Test successful language selection."""
    msg = message_factory(content_type="text", text="Russian")
    app, fakes = make_app(mocker)
    fakes.user_repo.set_target_language.return_value = True

    app.proceed_set_target_language(msg)

    assert (
        "The target language is set to Russian"
        in fakes.bot.send_message.call_args[0][1]
    )


def test_proceed_set_summarizing_model_success(message_factory, mocker):
    """Test successful model selection."""
    msg = message_factory(content_type="text", text="Gemini 3.7 Flash")
    app, fakes = make_app(mocker)
    fakes.user_repo.set_summarizing_model.return_value = True

    app.proceed_set_summarizing_model(msg)

    fakes.user_repo.set_summarizing_model.assert_called_once_with(
        msg.from_user.id,
        "gemini-3.7-flash",
    )
    assert (
        "The summarizing model is set to Gemini 3.7 Flash"
        in fakes.bot.send_message.call_args[0][1]
    )


def test_proceed_set_prompt_strategy_success(message_factory, mocker):
    """Test successful strategy selection."""
    msg = message_factory(content_type="text", text="Detailed Summary")
    app, fakes = make_app(mocker)
    fakes.user_repo.set_prompt_strategy.return_value = True

    app.proceed_set_prompt_strategy(msg)

    fakes.user_repo.set_prompt_strategy.assert_called_once_with(
        msg.from_user.id,
        "basic_prompt_for_transcript",
    )
    assert (
        "The prompt strategy is set to Detailed Summary"
        in fakes.bot.send_message.call_args[0][1]
    )


def test_proceed_set_thinking_level_success(message_factory, mocker):
    """Test successful thinking level selection."""
    msg = message_factory(content_type="text", text="High")
    app, fakes = make_app(mocker)
    fakes.user_repo.set_thinking_level.return_value = True

    app.proceed_set_thinking_level(msg)

    fakes.user_repo.set_thinking_level.assert_called_once_with(msg.from_user.id, "high")
    assert "The thinking level is set to High" in fakes.bot.send_message.call_args[0][1]


@pytest.mark.parametrize(
    ("proceed_name", "setter_name", "null_attr", "error_msg"),
    [
        (
            "proceed_set_target_language",
            "set_target_language",
            "text",
            "User information or language is missing.",
        ),
        (
            "proceed_set_summarizing_model",
            "set_summarizing_model",
            "from_user",
            "User information or model is missing.",
        ),
        (
            "proceed_set_prompt_strategy",
            "set_prompt_strategy",
            "text",
            "User information or strategy is missing.",
        ),
        (
            "proceed_set_thinking_level",
            "set_thinking_level",
            "text",
            "User information or level is missing.",
        ),
    ],
)
def test_proceed_set_setting_missing_input(
    message_factory,
    mocker,
    proceed_name,
    setter_name,
    null_attr,
    error_msg,
):
    """Test each setting selection fails fast when user or text is missing."""
    msg = message_factory(content_type="text", text="Anything")
    setattr(msg, null_attr, None)
    app, fakes = make_app(mocker)

    getattr(app, proceed_name)(msg)

    fakes.bot.reply_to.assert_called_once_with(msg, error_msg)
    getattr(fakes.user_repo, setter_name).assert_not_called()


@pytest.mark.parametrize(
    ("proceed_name", "setter_name", "bad_text", "error_msg"),
    [
        (
            "proceed_set_summarizing_model",
            "set_summarizing_model",
            "Gemini 4 Pro",
            "Unknown model",
        ),
        (
            "proceed_set_prompt_strategy",
            "set_prompt_strategy",
            "enterprise",
            "Unknown strategy",
        ),
        (
            "proceed_set_thinking_level",
            "set_thinking_level",
            "Ludicrous",
            "Unknown level",
        ),
    ],
)
def test_proceed_set_setting_invalid_choice(
    message_factory,
    mocker,
    proceed_name,
    setter_name,
    bad_text,
    error_msg,
):
    """Test an invalid label short-circuits before calling the setter."""
    msg = message_factory(content_type="text", text=bad_text)
    app, fakes = make_app(mocker)

    getattr(app, proceed_name)(msg)

    fakes.bot.send_message.assert_called_once_with(msg.chat.id, error_msg)
    getattr(fakes.user_repo, setter_name).assert_not_called()


def test_proceed_set_target_language_invalid_choice(message_factory, mocker):
    """Test an unknown language is rejected via the setter returning False."""
    msg = message_factory(content_type="text", text="Klingon")
    app, fakes = make_app(mocker)
    fakes.user_repo.set_target_language.return_value = False

    app.proceed_set_target_language(msg)

    fakes.bot.send_message.assert_called_once_with(msg.chat.id, "Unknown language")


@pytest.mark.parametrize(
    ("proceed_name", "setter_name", "valid_text", "error_msg"),
    [
        (
            "proceed_set_summarizing_model",
            "set_summarizing_model",
            "Gemini 3.7 Flash",
            "Failed to update summarizing model.",
        ),
        (
            "proceed_set_prompt_strategy",
            "set_prompt_strategy",
            "Detailed Summary",
            "Failed to update prompt strategy.",
        ),
        (
            "proceed_set_thinking_level",
            "set_thinking_level",
            "High",
            "Failed to update thinking level.",
        ),
    ],
)
def test_proceed_set_setting_db_failure(
    message_factory,
    mocker,
    proceed_name,
    setter_name,
    valid_text,
    error_msg,
):
    """Test a DB failure returns a clear user-facing message, not success."""
    msg = message_factory(content_type="text", text=valid_text)
    app, fakes = make_app(mocker)
    getattr(fakes.user_repo, setter_name).return_value = False

    getattr(app, proceed_name)(msg)

    fakes.bot.send_message.assert_called_once_with(msg.chat.id, error_msg)
