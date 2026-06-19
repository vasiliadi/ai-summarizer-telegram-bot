import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import (
    check_auth,
    register_user,
    select_user,
    set_prompt_strategy,
    set_summarizing_model,
    set_target_language,
    set_thinking_level,
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


def test_check_auth_approved_user(mock_db_session):
    """Test that an approved user returns True."""
    mock_db_session.get.return_value = UsersOrm(user_id=123, approved=True)

    assert check_auth(123) is True
    mock_db_session.get.assert_called_once_with(UsersOrm, 123)


def test_check_auth_unapproved_user(mock_db_session):
    """Test that an unapproved user returns False."""
    mock_db_session.get.return_value = UsersOrm(user_id=123, approved=False)

    assert check_auth(123) is False
    mock_db_session.get.assert_called_once_with(UsersOrm, 123)


def test_check_auth_unknown_user(mock_db_session):
    """Test that an unknown user ID raises ValueError."""
    mock_db_session.get.return_value = None

    with pytest.raises(ValueError, match="User not found"):
        check_auth(999)
    mock_db_session.get.assert_called_once_with(UsersOrm, 999)


@pytest.mark.parametrize(
    ("setter", "value", "orm_attr", "stored_value"),
    [
        (set_target_language, "English", "target_language", "English"),
        (set_summarizing_model, "gemini-3.5-flash", "summarizing_model", "gemini-3.5-flash"),
        (set_prompt_strategy, "basic_prompt_for_transcript", "prompt_key_for_summary", "basic_prompt_for_transcript"),
        (set_thinking_level, "high", "thinking_level", "HIGH"),
    ],
)
def test_set_setting_persists(
    monkeypatch, sqlite_session_factory, setter, value, orm_attr, stored_value
):
    """Test each setting setter persists to a real SQLite database."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    result = setter(123, value)

    assert result is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert getattr(user, orm_attr) == stored_value


@pytest.mark.parametrize(
    ("setter", "bad_value"),
    [
        (set_target_language, "Klingon"),
        (set_summarizing_model, "gpt-4"),
        (set_prompt_strategy, "bogus"),
    ],
)
def test_set_setting_rejects_unsupported(
    monkeypatch, sqlite_session_factory, setter, bad_value
):
    """Test each setting setter returns False for unsupported values."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    assert setter(123, bad_value) is False


def test_set_thinking_level_rejects_unknown_value(monkeypatch, sqlite_session_factory):
    """Test set_thinking_level returns False and leaves the default unchanged."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)
    register_user(123, "First", "Last", "user")

    assert set_thinking_level(123, "bogus") is False
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.thinking_level == "MINIMAL"


@pytest.mark.parametrize(
    ("setter", "value"),
    [
        (set_target_language, "English"),
        (set_summarizing_model, "gemini-3.5-flash"),
        (set_prompt_strategy, "key_points_for_transcript"),
        (set_thinking_level, "HIGH"),
    ],
)
def test_set_setting_missing_user(monkeypatch, sqlite_session_factory, setter, value):
    """Test each setting setter returns False when the user does not exist."""
    monkeypatch.setattr("database.Session", sqlite_session_factory)

    assert setter(999, value) is False
