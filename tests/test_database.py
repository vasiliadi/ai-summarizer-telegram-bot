import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import (
    register_user,
    select_user,
    set_prompt_strategy,
    set_summarizing_model,
    set_target_language,
    set_thinking_level,
    toggle_transcription,
    toggle_yt_transcription,
)
from models import Base, UsersOrm


@pytest.fixture
def sqlite_session_factory(tmp_path):
    """Provide an isolated SQLite session factory for integration-style tests."""
    sqlite_path = tmp_path / "test-db.sqlite"
    engine = create_engine(f"sqlite:///{sqlite_path}")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


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


def test_toggle_transcription_persists(monkeypatch, sqlite_session_factory):
    """Test toggling transcription persists to a real SQLite database."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    toggle_transcription(123)

    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.use_transcription is True


def test_set_target_language_persists(monkeypatch, sqlite_session_factory):
    """Test setting target language persists to a real SQLite database."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    result = set_target_language(123, "English")

    assert result is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.target_language == "English"


def test_set_target_language_rejects_unsupported(monkeypatch, sqlite_session_factory):
    """Test set_target_language returns False for unsupported languages."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    assert set_target_language(123, "Klingon") is False


def test_set_target_language_returns_false_for_missing_user(
    monkeypatch, sqlite_session_factory
):
    """Test set_target_language returns False when the user does not exist."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)

    assert set_target_language(123, "English") is False


def test_toggle_yt_transcription_persists(monkeypatch, sqlite_session_factory):
    """Test toggling YouTube transcription persists to a real SQLite database."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    toggle_yt_transcription(123)

    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.use_yt_transcription is True


def test_toggle_yt_transcription_missing_user_is_noop(
    monkeypatch, sqlite_session_factory
):
    """Test toggle_yt_transcription silently does nothing for unknown users."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)

    toggle_yt_transcription(999)  # must not raise


def test_set_summarizing_model_persists(monkeypatch, sqlite_session_factory):
    """Test setting summarizing model persists to a real SQLite database."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    result = set_summarizing_model(123, "gemini-3.5-flash")

    assert result is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.summarizing_model == "gemini-3.5-flash"


def test_set_summarizing_model_rejects_unknown(monkeypatch, sqlite_session_factory):
    """Test set_summarizing_model returns False for unsupported models."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    assert set_summarizing_model(123, "gpt-4") is False


def test_set_summarizing_model_missing_user(monkeypatch, sqlite_session_factory):
    """Test set_summarizing_model returns False when the user does not exist."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)

    assert set_summarizing_model(999, "gemini-3.5-flash") is False


def test_set_prompt_strategy_persists(monkeypatch, sqlite_session_factory):
    """Test setting prompt strategy persists to a real SQLite database."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    result = set_prompt_strategy(123, "basic_prompt_for_transcript")

    assert result is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.prompt_key_for_summary == "basic_prompt_for_transcript"


def test_set_prompt_strategy_rejects_unknown(monkeypatch, sqlite_session_factory):
    """Test set_prompt_strategy returns False for unsupported prompt keys."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    assert set_prompt_strategy(123, "bogus") is False


def test_set_prompt_strategy_missing_user(monkeypatch, sqlite_session_factory):
    """Test set_prompt_strategy returns False when the user does not exist."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)

    assert set_prompt_strategy(999, "key_points_for_transcript") is False


def test_set_thinking_level_persists(monkeypatch, sqlite_session_factory):
    """Test setting thinking level persists to a real SQLite database."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    result = set_thinking_level(123, "high")

    assert result is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.thinking_level == "HIGH"


def test_set_thinking_level_rejects_unknown_value(monkeypatch, sqlite_session_factory):
    """Test set_thinking_level returns False for unsupported values."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    assert set_thinking_level(123, "bogus") is False
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.thinking_level == "MINIMAL"


def test_set_thinking_level_missing_user(monkeypatch, sqlite_session_factory):
    """Test set_thinking_level returns False when the user does not exist."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)

    assert set_thinking_level(999, "HIGH") is False
