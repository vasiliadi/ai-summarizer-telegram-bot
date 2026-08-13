import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import (
    ALLOWED_THINKING_LEVELS,
    DEFAULT_MODEL_ID_FOR_SUMMARY,
    DEFAULT_PROMPT_KEY,
    DEFAULT_THINKING_LEVEL,
)
from database import UserRepository
from models import Base, UsersOrm


@pytest.fixture
def sqlite_session_factory(tmp_path):
    """Provide an isolated SQLite session factory for integration-style tests."""
    sqlite_path = tmp_path / "test-db.sqlite"
    engine = create_engine(f"sqlite:///{sqlite_path}")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def user_repo(sqlite_session_factory):
    """Provide a UserRepository backed by the isolated SQLite session factory."""
    return UserRepository(sqlite_session_factory)


def test_register_user_success(user_repo, sqlite_session_factory):
    """Test registering a new user successfully."""
    result = user_repo.register_user(123, "First", "Last", "user")

    assert result is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None


def test_register_user_stores_defaults(user_repo, sqlite_session_factory):
    """Test register_user stores the configured defaults when nothing is overridden."""
    assert user_repo.register_user(123, "First", "Last", "user") is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.summarizing_model == DEFAULT_MODEL_ID_FOR_SUMMARY
        assert user.prompt_key_for_summary == DEFAULT_PROMPT_KEY
        assert user.thinking_level == DEFAULT_THINKING_LEVEL


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("summarizing_model", DEFAULT_MODEL_ID_FOR_SUMMARY),
        ("prompt_key_for_summary", DEFAULT_PROMPT_KEY),
        ("thinking_level", DEFAULT_THINKING_LEVEL),
    ],
)
def test_orm_server_defaults_match_config(column, expected):
    """Test the column server defaults stay in sync with the config constants."""
    assert UsersOrm.__table__.c[column].server_default.arg == expected


def test_register_user_duplicate(mocker, user_repo, sqlite_session_factory):
    """Test register_user returns False when user already exists (IntegrityError).

    Registering the same user_id twice raises a real IntegrityError from SQLite's
    primary-key constraint. The rollback is spied on the Session class, not an
    instance: the repository opens its own session, so there is none to spy on first.
    """
    assert user_repo.register_user(123, "First", "Last", "user") is True
    rollback_spy = mocker.spy(sqlite_session_factory.class_, "rollback")

    result = user_repo.register_user(123, "First", "Last", "user")

    assert result is False
    assert rollback_spy.called


def test_select_user_missing(user_repo):
    """Test select_user raises a clear error for unknown users."""
    with pytest.raises(ValueError, match="User not found"):
        user_repo.select_user(999)


def test_check_auth_approved_user(user_repo):
    """Test that an approved user returns True."""
    user_repo.register_user(123, "First", "Last", "user", approved=True)

    assert user_repo.check_auth(123) is True


def test_check_auth_unapproved_user(user_repo):
    """Test that an unapproved user returns False."""
    user_repo.register_user(123, "First", "Last", "user", approved=False)

    assert user_repo.check_auth(123) is False


def test_check_auth_unknown_user(user_repo):
    """Test that an unknown user ID raises ValueError."""
    with pytest.raises(ValueError, match="User not found"):
        user_repo.check_auth(999)


@pytest.mark.parametrize(
    ("setter", "value", "orm_attr", "stored_value"),
    [
        ("set_target_language", "English", "target_language", "English"),
        (
            "set_summarizing_model",
            "gemini-3.7-flash",
            "summarizing_model",
            "gemini-3.7-flash",
        ),
        (
            "set_prompt_strategy",
            "basic_prompt_for_transcript",
            "prompt_key_for_summary",
            "basic_prompt_for_transcript",
        ),
        ("set_thinking_level", "high", "thinking_level", "high"),
    ],
)
def test_set_setting_persists(
    user_repo,
    sqlite_session_factory,
    setter,
    value,
    orm_attr,
    stored_value,
):
    """Test each setting setter persists to a real SQLite database."""
    user_repo.register_user(123, "First", "Last", "user")

    result = getattr(user_repo, setter)(123, value)

    assert result is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert getattr(user, orm_attr) == stored_value


@pytest.mark.parametrize(
    ("setter", "bad_value"),
    [
        ("set_target_language", "Klingon"),
        ("set_summarizing_model", "gpt-4"),
        ("set_prompt_strategy", "bogus"),
    ],
)
def test_set_setting_rejects_unsupported(user_repo, setter, bad_value):
    """Test each setting setter returns False for unsupported values."""
    user_repo.register_user(123, "First", "Last", "user")

    assert getattr(user_repo, setter)(123, bad_value) is False


@pytest.mark.parametrize(
    ("setter", "value", "orm_attr", "stored_value"),
    [
        ("set_target_language", "english", "target_language", "English"),
        (
            "set_summarizing_model",
            "GEMINI-3.7-FLASH",
            "summarizing_model",
            "gemini-3.7-flash",
        ),
        (
            "set_prompt_strategy",
            "Key_Points_For_Transcript",
            "prompt_key_for_summary",
            "key_points_for_transcript",
        ),
        ("set_thinking_level", "HIGH", "thinking_level", "high"),
    ],
)
def test_set_setting_stores_normalized_value(
    user_repo,
    sqlite_session_factory,
    setter,
    value,
    orm_attr,
    stored_value,
):
    """Test setters persist the canonical form, not the caller's casing.

    Validation already normalizes before checking the allow-list, so storing the
    raw input would let a non-canonical value through: PROMPTS[...] would raise
    KeyError and a mis-cased model id would be rejected by the Gemini API.
    """
    user_repo.register_user(123, "First", "Last", "user")

    assert getattr(user_repo, setter)(123, value) is True
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert getattr(user, orm_attr) == stored_value


def test_set_thinking_level_rejects_unknown_value(user_repo, sqlite_session_factory):
    """Test set_thinking_level returns False and leaves the stored level unchanged."""
    user_repo.register_user(123, "First", "Last", "user")
    # Move off the default first, so a rejected value cannot be mistaken for it.
    other_level = next(
        level for level in ALLOWED_THINKING_LEVELS if level != DEFAULT_THINKING_LEVEL
    )
    assert user_repo.set_thinking_level(123, other_level) is True

    assert user_repo.set_thinking_level(123, "bogus") is False
    with sqlite_session_factory() as session:
        user = session.get(UsersOrm, 123)
        assert user is not None
        assert user.thinking_level == other_level


@pytest.mark.parametrize(
    ("setter", "value"),
    [
        ("set_target_language", "English"),
        ("set_summarizing_model", "gemini-3.7-flash"),
        ("set_prompt_strategy", "key_points_for_transcript"),
        ("set_thinking_level", "high"),
    ],
)
def test_set_setting_missing_user(user_repo, setter, value):
    """Test each setting setter returns False when the user does not exist."""
    assert getattr(user_repo, setter)(999, value) is False
