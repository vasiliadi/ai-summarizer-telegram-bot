import pytest

from config import MODELS_WITH_THINKING_SUPPORT
from exceptions import LimitExceededError
from services import (
    check_quota,
    get_file_with_retry,
    get_gemini_config,
    get_remaining_quota,
    reply_with_retry,
    resolve_mime_type,
    send_answer,
    upload_and_wait_for_audio_file,
)


def test_reply_with_retry_happy_path(mocker):
    """Test reply_with_retry sends message successfully."""
    mock_bot = mocker.patch("services.bot")
    mock_msg = mocker.MagicMock()

    reply_with_retry(mock_msg, "hello")

    mock_bot.reply_to.assert_called_once_with(mock_msg, "hello")


def test_reply_with_retry_with_entities(mocker):
    """Test reply_with_retry sends message with entities."""
    mock_bot = mocker.patch("services.bot")
    mock_msg = mocker.MagicMock()
    entities = [{"type": "bold"}]

    reply_with_retry(mock_msg, "hello", entities=entities)

    mock_bot.reply_to.assert_called_once_with(mock_msg, "hello", entities=entities)


def test_get_file_with_retry_success(mocker):
    """Test get_file_with_retry retrieves file info."""
    mock_bot = mocker.patch("services.bot")
    mock_bot.get_file.return_value = "mock_file"

    result = get_file_with_retry("id123")

    assert result == "mock_file"
    mock_bot.get_file.assert_called_once_with("id123")


def test_send_answer_single_chunk(mocker):
    """Test send_answer with a short message (single chunk)."""
    mock_convert = mocker.patch("services.convert", return_value=("text", []))
    # Mock split_entities to return one chunk
    mock_entity = mocker.MagicMock()
    mock_entity.to_dict.return_value = {"type": "bold"}
    mock_split = mocker.patch(
        "services.split_entities", return_value=[("text", [mock_entity])]
    )

    mock_reply = mocker.patch("services.reply_with_retry")
    mock_msg = mocker.MagicMock()

    send_answer(mock_msg, "short answer")

    mock_convert.assert_called_once_with("short answer")
    mock_split.assert_called_once_with("text", [], max_utf16_len=4096)
    mock_reply.assert_called_once_with(mock_msg, "text", entities=[{"type": "bold"}])


def test_send_answer_multi_chunk(mocker):
    """Test send_answer with a long message (multiple chunks)."""
    mocker.patch("services.convert", return_value=("text", []))
    mocker.patch("services.split_entities", return_value=[("part1", []), ("part2", [])])
    mock_reply = mocker.patch("services.reply_with_retry")
    mocker.patch("services.time.sleep")

    mock_msg = mocker.MagicMock()
    send_answer(mock_msg, "long answer")

    assert mock_reply.call_count == 2


def test_get_gemini_config_content():
    """Test get_gemini_config includes the correct language in instruction."""
    config = get_gemini_config("French")
    assert "French" in config.system_instruction


def test_get_gemini_config_with_extra_system_instruction():
    """Test get_gemini_config appends extra system instruction when provided."""
    config = get_gemini_config(
        "English",
        extra_system_instruction="Use UrlContext before answering.",
    )
    assert "English" in config.system_instruction
    assert "Use UrlContext before answering." in config.system_instruction


def test_get_gemini_config_thinking_enabled_for_supported_model():
    """Test that thinking config is set for models that support it."""
    model = MODELS_WITH_THINKING_SUPPORT[0]
    config = get_gemini_config("English", model=model)
    assert config.thinking_config is not None


def test_get_gemini_config_thinking_disabled_for_unsupported_model():
    """Test that thinking config is None for models that do not support it."""
    config = get_gemini_config("English", model="gemini-2.5-flash")
    assert config.thinking_config is None


def test_get_gemini_config_thinking_disabled_when_no_model_given():
    """Test that thinking config is None when model is omitted."""
    config = get_gemini_config("English")
    assert config.thinking_config is None


def test_upload_and_wait_for_audio_file_happy(mocker):
    """Test uploading file to Gemini when it's immediately ACTIVE."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "ACTIVE"
    mock_file.uri = "uri"
    mock_file.mime_type = "audio/ogg"

    mock_client.files.upload.return_value = mock_file

    result = upload_and_wait_for_audio_file("path", "audio/ogg", 1)

    assert result == mock_file
    mock_client.files.upload.assert_called_once()


def test_upload_and_wait_for_audio_file_polling(mocker):
    """Test uploading file to Gemini with polling (PROCESSING -> ACTIVE)."""
    mock_client = mocker.patch("services.gemini_client")
    mocker.patch("services.time.sleep")

    mock_file_proc = mocker.MagicMock()
    mock_file_proc.name = "name"
    mock_file_proc.state = "PROCESSING"

    mock_file_active = mocker.MagicMock()
    mock_file_active.name = "name"
    mock_file_active.state = "ACTIVE"
    mock_file_active.uri = "uri"
    mock_file_active.mime_type = "audio/ogg"

    mock_client.files.upload.return_value = mock_file_proc
    mock_client.files.get.return_value = mock_file_active

    result = upload_and_wait_for_audio_file("path", "audio/ogg", 1)

    assert result == mock_file_active
    mock_client.files.get.assert_called_once_with(name="name")


def test_upload_and_wait_for_audio_file_failed(mocker):
    """Test upload_and_wait_for_audio_file raises ValueError on FAILED state."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "FAILED"
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(ValueError, match="FAILED"):
        upload_and_wait_for_audio_file("path", "audio/ogg", 1)


def test_resolve_mime_type_fallback_when_mimetypes_returns_none(mocker):
    """resolve_mime_type falls back to extension matching when mimetypes returns None."""
    mocker.patch("services.mimetypes.guess_type", return_value=(None, None))

    assert resolve_mime_type("audio.ogg") == "audio/ogg"
    assert resolve_mime_type("audio.opus") == "audio/ogg"
    assert resolve_mime_type("audio.mp3") == "audio/mpeg"
    assert resolve_mime_type("audio.wav") == "audio/wav"
    assert resolve_mime_type("video.mp4") == "video/mp4"
    assert resolve_mime_type("unknown.bin") == "application/octet-stream"


def test_upload_and_wait_for_audio_file_name_none(mocker):
    """upload_and_wait_for_audio_file raises AttributeError when upload returns no name."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = None
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(AttributeError):
        upload_and_wait_for_audio_file("path", "audio/ogg", 1)


def test_upload_and_wait_for_audio_file_missing_uri(mocker):
    """upload_and_wait_for_audio_file raises AttributeError when uri or mime_type is None."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "ACTIVE"
    mock_file.uri = None
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(AttributeError):
        upload_and_wait_for_audio_file("path", "audio/ogg", 1)


def test_get_remaining_quota(mocker):
    """get_remaining_quota probes Redis with quantity=0 and returns remaining count."""
    mock_throttle_cls = mocker.patch("services.throttle.Throttle")
    mock_throttle_instance = mock_throttle_cls.return_value
    mock_throttle_instance.check.return_value = mocker.MagicMock(remaining=7)

    result = get_remaining_quota(user_id=123, daily_limit=10)

    assert result == 7
    mock_throttle_instance.check.assert_called_once_with("RPD:123", quantity=0)


def test_check_quota_uses_per_user_redis_key(mocker):
    """check_quota checks the Redis key scoped to the user (RPD:{user_id})."""
    mock_throttle_cls = mocker.patch("services.throttle.Throttle")
    mock_throttle_instance = mock_throttle_cls.return_value
    mock_throttle_instance.check.return_value = mocker.MagicMock(limited=False)
    mocker.patch(
        "services.per_minute_limit.check",
        return_value=mocker.MagicMock(limited=False),
    )

    result = check_quota(user_id=456, daily_limit=5)

    assert result is True
    mock_throttle_instance.check.assert_called_once_with("RPD:456", quantity=1)


def test_check_quota_raises_when_daily_redis_counter_exhausted(mocker):
    """check_quota raises LimitExceededError when Redis counter is at the cap."""
    mock_throttle_cls = mocker.patch("services.throttle.Throttle")
    mock_throttle_instance = mock_throttle_cls.return_value
    mock_throttle_instance.check.return_value = mocker.MagicMock(limited=True)

    with pytest.raises(LimitExceededError):
        check_quota(user_id=789, daily_limit=3)
