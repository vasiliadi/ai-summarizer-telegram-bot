
import pytest
from main import (
    handle_start,
    handle_info,
    handle_myinfo,
    handle_limit,
    handle_toggle_transcription,
    handle_toggle_yt_transcription,
    handle_set_target_language,
    proceed_set_target_language,
    handle_set_summarizing_model,
    proceed_set_summarizing_model,
    handle_set_prompt_strategy,
    proceed_set_prompt_strategy
)
from models import UsersOrm

def test_handle_start_new_user(message_factory, mocker):
    """Test /start for a new user (registration)."""
    msg = message_factory(content_type="text", text="/start")
    # register_user(user_id, first_name, last_name, username)
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

def test_handle_info(message_factory, mocker):
    """Test /info command."""
    msg = message_factory(content_type="text", text="/info")
    mock_send = mocker.patch("main.bot.send_message")
    
    handle_info(msg)
    
    assert str(msg.from_user.id) in mock_send.call_args[0][1]

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
        use_transcription=False
    )
    mocker.patch("main.select_user", return_value=mock_user)
    mock_send = mocker.patch("main.bot.send_message")
    
    handle_myinfo(msg)
    
    content = mock_send.call_args[0][1]
    assert "Approved: True" in content
    assert "Target language: English" in content

def test_handle_limit(message_factory, mocker):
    """Test /limit command."""
    msg = message_factory(content_type="text", text="/limit")
    mock_limit = mocker.patch("main.per_day_limit.check")
    mock_limit.return_value.remaining = 15
    mock_send = mocker.patch("main.bot.send_message")
    
    handle_limit(msg)
    
    assert "Remaining limit: 15" in mock_send.call_args[0][1]

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
    msg = message_factory(content_type="text", text="gemini-2.5-flash")
    mocker.patch("main.set_summarizing_model", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")
    
    proceed_set_summarizing_model(msg)
    
    assert "The summarizing model is set to gemini-2.5-flash" in mock_send.call_args[0][1]

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
    msg = message_factory(content_type="text", text="basic")
    mocker.patch("main.set_prompt_strategy", return_value=True)
    mock_send = mocker.patch("main.bot.send_message")
    
    proceed_set_prompt_strategy(msg)
    
    assert "The prompt strategy is set to basic" in mock_send.call_args[0][1]
