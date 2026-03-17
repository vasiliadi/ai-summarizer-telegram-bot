import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import (
    register_user,
    select_user,
    set_prompt_strategy,
    set_target_language,
    toggle_transcription,
)
from models import Base, UsersOrm


def test_register_user_success(mock_db_session):
    """Test registering a new user successfully."""
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


def test_select_user_missing(mock_db_session):
    """Test select_user raises a clear error for unknown users."""
    mock_db_session.get.return_value = None

    with pytest.raises(ValueError, match="User not found"):
        select_user(999)


def test_toggle_transcription_persists(monkeypatch, tmp_path):
    """Test toggling transcription persists to a real SQLite database."""
    session_factory = _sqlite_session_factory(tmp_path)
    monkeypatch.setattr("database.Session", session_factory)
    register_user(123, "First", "Last", "user")

    toggle_transcription(123)

    with session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.use_transcription is True


def test_set_target_language_returns_false_for_missing_user(monkeypatch, tmp_path):
    """Test set_target_language returns False when the user does not exist."""
    session_factory = _sqlite_session_factory(tmp_path)
    monkeypatch.setattr("database.Session", session_factory)

    assert set_target_language(123, "English") is False


def test_set_prompt_strategy_persists(monkeypatch, tmp_path):
    """Test setting prompt strategy persists to a real SQLite database."""
    session_factory = _sqlite_session_factory(tmp_path)
    monkeypatch.setattr("database.Session", session_factory)
    register_user(123, "First", "Last", "user")

    result = set_prompt_strategy(123, "basic_prompt_for_transcript")

    assert result is True
    with session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.prompt_key_for_summary == "basic_prompt_for_transcript"


def _sqlite_session_factory(tmp_path):
    """Create an isolated SQLite session factory for integration-style tests."""
    sqlite_path = tmp_path / "test-db.sqlite"
    engine = create_engine(f"sqlite:///{sqlite_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)
