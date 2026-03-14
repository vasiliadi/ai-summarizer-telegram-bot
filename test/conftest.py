import sys
from pathlib import Path

import fakeredis
import pytest
from telebot import TeleBot, types

# Ensure `src` is in the PYTHONPATH so we can import modules like config, database, etc.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import os

# We must mock environment variables BEFORE any src.config imports happen,
# otherwise SQLAlchemy and Sentry will try to initialize with real credentials.
os.environ["ENV"] = "TEST"
os.environ["SENTRY_DSN"] = "http://public@localhost:9/1"
os.environ["DSN"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["TG_API_TOKEN"] = "12345:mock_token"
os.environ["GEMINI_API_KEY"] = "mock_gemini_key"
os.environ["REPLICATE_API_TOKEN"] = "mock_replicate_token"

import sentry_sdk

# Disable Sentry in tests to avoid connection errors
sentry_sdk.init = lambda *args, **kwargs: None


@pytest.fixture
def mock_bot(mocker):
    """Fixture to provide a mocked TeleBot instance."""
    return mocker.MagicMock(spec=TeleBot)


@pytest.fixture
def mock_db_session(mocker):
    """Fixture to mock the database session."""
    session_mock = mocker.MagicMock()
    # Mocking the Session factory from our database module
    # The actual database functions do:
    # with Session() as session:
    # So Session() must return a context manager that yields session_mock
    context_manager_mock = mocker.MagicMock()
    context_manager_mock.__enter__.return_value = session_mock

    mocker.patch("database.Session", return_value=context_manager_mock)
    # Also mock engine if accessed
    mocker.patch("database.engine", mocker.MagicMock())
    return session_mock
    # Also mock engine if accessed
    mocker.patch("database.engine", mocker.MagicMock())
    return session_mock


@pytest.fixture
def redis_client(mocker):
    """Fixture to provide a fakeredis instance and mock the actual redis client."""
    fake_redis = fakeredis.FakeRedis()
    # It mocks the redis client initialization in rush/config where appropriate
    mocker.patch("rush.stores.redis.redis.StrictRedis.from_url", return_value=fake_redis)
    return fake_redis


@pytest.fixture
def message_factory():
    """Fixture to generate a mock telebot Message with variable content."""
    def _create_message(
        content_type="text",
        text="Hello world",
        user_id=12345678,
        username="testuser",
        first_name="Test",
        last_name="User",
    ):
        user = types.User(
            id=user_id,
            is_bot=False,
            first_name=first_name,
            last_name=last_name,
            username=username,
        )
        chat = types.Chat(id=user_id, type="private")

        # Message requires json_string and options in the constructor but they can be empty
        msg = types.Message(
            message_id=1,
            from_user=user,
            date=1234567890,
            chat=chat,
            content_type=content_type,
            options=[],
            json_string="",
        )

        if content_type == "text":
            msg.text = text
        elif content_type == "document":
            msg.document = types.Document(
                file_id="mock_doc_id",
                file_unique_id="mock_doc_uid",
                file_name="test.pdf",
                mime_type="application/pdf",
                file_size=1024,
            )
        elif content_type == "audio":
            msg.audio = types.Audio(
                file_id="mock_audio_id",
                file_unique_id="mock_audio_uid",
                duration=10,
                file_name="test.ogg",
                mime_type="audio/ogg",
                file_size=1024,
            )
        elif content_type == "video":
            msg.video = types.Video(
                file_id="mock_video_id",
                file_unique_id="mock_video_uid",
                duration=10,
                width=640,
                height=480,
                file_name="test.mp4",
                mime_type="video/mp4",
                file_size=1024,
            )

        return msg

    return _create_message
