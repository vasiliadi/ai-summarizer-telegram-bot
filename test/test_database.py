
import pytest
from sqlalchemy.exc import IntegrityError
from database import (
    register_user,
    toggle_transcription,
    toggle_yt_transcription,
    set_target_language,
    set_summarizing_model,
    set_prompt_strategy
)
from models import UsersOrm

def test_register_user_success(mock_db_session):
    """Test registering a new user successfully."""
    # Mock select to return None (user doesn't exist)
    mock_db_session.scalars.return_value.first.return_value = None

    result = register_user(123, "First", "Last", "user")

    assert result is True
    assert mock_db_session.add.called
    assert mock_db_session.commit.called


def test_register_user_duplicate(mock_db_session):
    """Test register_user returns False when user already exists (IntegrityError)."""
    mock_db_session.commit.side_effect = IntegrityError("msg", "params", "orig")

    result = register_user(123, "First", "Last", "user")

    assert result is False
    assert mock_db_session.rollback.called


def test_toggle_transcription(mock_db_session):
    """Test toggling the use_transcription flag."""
    mock_user = UsersOrm(user_id=123, use_transcription=False)
    # mock_db_session.scalars is used in select_user
    mock_db_session.get.return_value = mock_user

    toggle_transcription(123)

    assert mock_user.use_transcription is True
    assert mock_db_session.commit.called


def test_toggle_yt_transcription(mock_db_session):
    """Test toggling the use_yt_transcription flag."""
    mock_user = UsersOrm(user_id=123, use_yt_transcription=False)
    mock_db_session.get.return_value = mock_user

    toggle_yt_transcription(123)

    assert mock_user.use_yt_transcription is True
    assert mock_db_session.commit.called


def test_set_target_language_valid(mock_db_session):
    """Test setting a valid target language."""
    mock_user = UsersOrm(user_id=123, target_language="English")
    mock_db_session.get.return_value = mock_user

    # Language list is Title-cased in database.py: SUPPORTED_LANGUAGES
    result = set_target_language(123, "English")

    assert result is True
    assert mock_user.target_language == "English"
    assert mock_db_session.commit.called


def test_set_target_language_invalid(mock_db_session):
    """Test setting an invalid target language returns False."""
    result = set_target_language(123, "UnsupportedLang")
    assert result is False


def test_set_summarizing_model_valid(mock_db_session):
    """Test setting a valid summarizing model."""
    mock_user = UsersOrm(user_id=123, summarizing_model="gemini-2.5-flash")
    mock_db_session.get.return_value = mock_user

    result = set_summarizing_model(123, "gemini-3-flash-preview")

    assert result is True
    assert mock_user.summarizing_model == "gemini-3-flash-preview"
    assert mock_db_session.commit.called


def test_set_summarizing_model_invalid(mock_db_session):
    """Test setting an invalid summarizing model returns False."""
    result = set_summarizing_model(123, "unknown-model")
    assert result is False


def test_set_prompt_strategy_valid(mock_db_session):
    """Test setting a valid prompt strategy."""
    mock_user = UsersOrm(user_id=123, prompt_key_for_summary="basic")
    mock_db_session.get.return_value = mock_user

    result = set_prompt_strategy(123, "basic_prompt_for_transcript")

    assert result is True
    assert mock_user.prompt_key_for_summary == "basic_prompt_for_transcript"
    assert mock_db_session.commit.called

def test_set_prompt_strategy_invalid(mock_db_session):
    """Test setting an invalid prompt strategy returns False."""
    result = set_prompt_strategy(123, "unknown-strategy")
    assert result is False
