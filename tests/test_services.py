import pytest
from google.genai import types
from limits.util import WindowStats

import services as services_module
from exceptions import LimitExceededError
from services import (
    check_quota,
    get_file_with_retry,
    get_gemini_config,
    get_remaining_quota,
    resolve_mime_type,
    send_answer,
    upload_and_wait_for_file,
)


def test__reply_with_retry_happy_path(mocker):
    """Test _reply_with_retry sends message successfully."""
    mock_bot = mocker.patch("services.bot")
    mock_msg = mocker.MagicMock()

    services_module.messenger._reply_with_retry(mock_msg, "hello")

    mock_bot.reply_to.assert_called_once_with(mock_msg, "hello")


def test__reply_with_retry_with_entities(mocker):
    """Test _reply_with_retry sends message with entities."""
    mock_bot = mocker.patch("services.bot")
    mock_msg = mocker.MagicMock()
    entities = [{"type": "bold"}]

    services_module.messenger._reply_with_retry(mock_msg, "hello", entities=entities)

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

    mock_reply = mocker.patch.object(services_module.messenger, "_reply_with_retry")
    mock_msg = mocker.MagicMock()

    send_answer(mock_msg, "short answer")

    mock_convert.assert_called_once_with("short answer")
    mock_split.assert_called_once_with("text", [], max_utf16_len=4096)
    mock_reply.assert_called_once_with(mock_msg, "text", entities=[{"type": "bold"}])


def test_send_answer_multi_chunk(mocker):
    """Test send_answer with a long message (multiple chunks)."""
    mocker.patch("services.convert", return_value=("text", []))
    mocker.patch("services.split_entities", return_value=[("part1", []), ("part2", [])])
    mock_reply = mocker.patch.object(services_module.messenger, "_reply_with_retry")
    mocker.patch("services.time.sleep")

    mock_msg = mocker.MagicMock()
    send_answer(mock_msg, "long answer")

    assert mock_reply.call_count == 2


def test_get_gemini_config_content():
    """Test get_gemini_config includes the correct language in instruction."""
    config = get_gemini_config("French", thinking_level="HIGH")
    assert "French" in config.system_instruction


def test_get_gemini_config_thinking_enabled():
    """Test that thinking config is set based on the passed thinking level."""
    config = get_gemini_config("English", thinking_level="MEDIUM")
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM


def test_get_gemini_config_invalid_thinking_level():
    """Lock current behavior on unknown thinking levels.

    ``google.genai.types.ThinkingLevel`` accepts unknown values, emits a
    ``UserWarning``, and returns a dynamically-created enum member rather than
    raising. ``get_gemini_config`` inherits that lenient behavior — it does not
    validate or fall back. This test pins both halves of the contract so any
    future change (added validation, silent fallback, or raise) is caught.
    """
    with pytest.warns(UserWarning, match="INVALID is not a valid ThinkingLevel"):
        config = get_gemini_config("English", thinking_level="INVALID")
    assert config.thinking_config is not None


def test_upload_and_wait_for_file_happy(mocker):
    """Test uploading file to Gemini when it's immediately ACTIVE."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "ACTIVE"
    mock_file.uri = "uri"
    mock_file.mime_type = "audio/ogg"

    mock_client.files.upload.return_value = mock_file

    result = upload_and_wait_for_file("path", "audio/ogg", 1)

    assert result == mock_file
    mock_client.files.upload.assert_called_once()


def test_upload_and_wait_for_file_polling(mocker):
    """Test uploading file to Gemini with polling (PROCESSING -> ACTIVE)."""
    mock_client = mocker.patch("services.gemini_client")
    mock_sleep = mocker.patch("services.time.sleep")

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

    result = upload_and_wait_for_file("path", "audio/ogg", 1)

    assert result == mock_file_active
    mock_sleep.assert_called_once_with(1)
    mock_client.files.get.assert_called_once_with(name="name")


def test_upload_and_wait_for_file_failed(mocker):
    """Test upload_and_wait_for_file raises ValueError on FAILED state."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "FAILED"
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(ValueError, match="FAILED"):
        upload_and_wait_for_file("path", "audio/ogg", 1)


def test_resolve_mime_type_fallback_when_mimetypes_returns_none(mocker):
    """resolve_mime_type falls back to extension matching when mimetypes returns None."""
    mocker.patch("services.mimetypes.guess_type", return_value=(None, None))

    assert resolve_mime_type("audio.ogg") == "audio/ogg"
    assert resolve_mime_type("audio.opus") == "audio/ogg"
    assert resolve_mime_type("audio.mp3") == "audio/mpeg"
    assert resolve_mime_type("audio.wav") == "audio/wav"
    assert resolve_mime_type("video.mp4") == "video/mp4"
    assert resolve_mime_type("unknown.bin") == "application/octet-stream"


def test_upload_and_wait_for_file_name_none(mocker):
    """upload_and_wait_for_file raises AttributeError when upload returns no name."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = None
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(AttributeError):
        upload_and_wait_for_file("path", "audio/ogg", 1)


def test_upload_and_wait_for_file_missing_uri(mocker):
    """upload_and_wait_for_file raises AttributeError when uri or mime_type is None."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "ACTIVE"
    mock_file.uri = None
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(AttributeError):
        upload_and_wait_for_file("path", "audio/ogg", 1)


def test_get_remaining_quota(mocker):
    """get_remaining_quota returns remaining count from window stats."""
    mocker.patch(
        "services.rate_limiter.get_window_stats",
        return_value=WindowStats(reset_time=9999999999.0, remaining=7),
    )

    result = get_remaining_quota(user_id=123, daily_limit=10)

    assert result == 7


def test_check_quota_raises_immediately_when_daily_limit_zero(mocker):
    """check_quota raises LimitExceededError without touching Redis when limit is 0."""
    mock_hit = mocker.patch("services.rate_limiter.hit")

    with pytest.raises(LimitExceededError):
        check_quota(user_id=1, daily_limit=0)

    mock_hit.assert_not_called()


def test_get_remaining_quota_returns_zero_when_daily_limit_zero(mocker):
    """get_remaining_quota returns 0 without touching Redis when limit is 0."""
    mock_stats = mocker.patch("services.rate_limiter.get_window_stats")

    result = get_remaining_quota(user_id=1, daily_limit=0)

    assert result == 0
    mock_stats.assert_not_called()


def test_check_quota_uses_per_user_redis_key(mocker):
    """check_quota hits the Redis key scoped to the user (RPD:{user_id})."""
    mock_hit = mocker.patch("services.rate_limiter.hit", return_value=True)

    result = check_quota(user_id=456, daily_limit=5)

    assert result is True
    assert mock_hit.call_args_list[0].args[1] == "RPD:456"


def test_check_quota_raises_when_daily_redis_counter_exhausted(mocker):
    """check_quota raises LimitExceededError when the daily counter is exhausted."""
    mocker.patch("services.rate_limiter.hit", return_value=False)

    with pytest.raises(LimitExceededError):
        check_quota(user_id=789, daily_limit=3)


def test_check_quota_sleeps_when_per_minute_limited(mocker):
    """check_quota sleeps until the window resets and retries the per-minute hit."""
    fixed_now = 1_000_000.0
    mocker.patch("services.time.time", return_value=fixed_now)
    mocker.patch(
        "services.rate_limiter.hit",
        side_effect=[True, False, True],  # daily passes, per-minute blocked, retry ok
    )
    mocker.patch(
        "services.rate_limiter.get_window_stats",
        return_value=WindowStats(reset_time=fixed_now + 7.5, remaining=0),
    )
    mock_sleep = mocker.patch("services.time.sleep")

    result = check_quota(user_id=321, daily_limit=5)

    assert result is True
    mock_sleep.assert_called_once_with(7.5)
