import pytest
from limits import parse as parse_rate_limit
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from limits.util import WindowStats

from exceptions import LimitExceededError
from prompts import prompt_version
from services import GeminiHelper, Messenger, QuotaManager, Tracer


@pytest.mark.parametrize("entities", [[], [{"type": "bold"}]])
def test__reply_with_retry_forwards_entities(mocker, entities):
    """Test _reply_with_retry forwards entities (empty or not) to bot.reply_to."""
    mock_bot = mocker.MagicMock()
    mock_msg = mocker.MagicMock()

    Messenger(mock_bot)._reply_with_retry(mock_msg, "hello", entities=entities)

    mock_bot.reply_to.assert_called_once_with(mock_msg, "hello", entities=entities)


def test_get_file_with_retry_success(mocker):
    """Test get_file_with_retry retrieves file info."""
    mock_bot = mocker.MagicMock()
    mock_bot.get_file.return_value = "mock_file"

    result = Messenger(mock_bot).get_file_with_retry("id123")

    assert result == "mock_file"
    mock_bot.get_file.assert_called_once_with("id123")


def test_send_answer_single_chunk(mocker):
    """Test send_answer with a short message (single chunk)."""
    mock_convert = mocker.patch("services.convert", return_value=("text", []))
    # Mock split_entities to return one chunk
    mock_entity = mocker.MagicMock()
    mock_entity.to_dict.return_value = {"type": "bold"}
    mock_split = mocker.patch(
        "services.split_entities",
        return_value=[("text", [mock_entity])],
    )

    messenger = Messenger(mocker.MagicMock())
    mock_reply = mocker.patch.object(messenger, "_reply_with_retry")
    mock_msg = mocker.MagicMock()

    messenger.send_answer(mock_msg, "short answer")

    mock_convert.assert_called_once_with("short answer")
    mock_split.assert_called_once_with("text", [], max_utf16_len=4096)
    mock_reply.assert_called_once_with(mock_msg, "text", entities=[{"type": "bold"}])


def test_send_answer_multi_chunk(mocker):
    """Test send_answer with a long message (multiple chunks)."""
    mocker.patch("services.convert", return_value=("text", []))
    mocker.patch("services.split_entities", return_value=[("part1", []), ("part2", [])])
    mocker.patch("services.time.sleep")

    messenger = Messenger(mocker.MagicMock())
    mock_reply = mocker.patch.object(messenger, "_reply_with_retry")
    mock_msg = mocker.MagicMock()

    messenger.send_answer(mock_msg, "long answer")

    assert mock_reply.call_count == 2


def test_upload_and_wait_for_file_happy(mocker):
    """Test uploading file to Gemini when it's immediately ACTIVE."""
    mock_client = mocker.MagicMock()
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "ACTIVE"
    mock_file.uri = "uri"
    mock_file.mime_type = "audio/ogg"

    mock_client.files.upload.return_value = mock_file

    result = GeminiHelper(mock_client).upload_and_wait_for_file("path", "audio/ogg", 1)

    assert result == mock_file
    mock_client.files.upload.assert_called_once()


def test_upload_and_wait_for_file_polling(mocker):
    """Test uploading file to Gemini with polling (PROCESSING -> ACTIVE)."""
    mock_client = mocker.MagicMock()
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

    result = GeminiHelper(mock_client).upload_and_wait_for_file("path", "audio/ogg", 1)

    assert result == mock_file_active
    mock_sleep.assert_called_once_with(1)
    mock_client.files.get.assert_called_once_with(name="name")


def test_upload_and_wait_for_file_failed(mocker):
    """Test upload_and_wait_for_file raises ValueError on FAILED state."""
    mock_client = mocker.MagicMock()
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "FAILED"
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(ValueError, match="FAILED"):
        GeminiHelper(mock_client).upload_and_wait_for_file("path", "audio/ogg", 1)


def test_resolve_mime_type_uses_mimetypes_guess(mocker):
    """resolve_mime_type maps known extensions via the stdlib mimetypes database."""
    gemini_helper = GeminiHelper(mocker.MagicMock())
    assert gemini_helper.resolve_mime_type("document.pdf") == "application/pdf"
    assert gemini_helper.resolve_mime_type("data.csv") == "text/csv"
    assert gemini_helper.resolve_mime_type("text.rtf") == "application/rtf"
    assert gemini_helper.resolve_mime_type("audio.ogg") == "audio/ogg"
    assert gemini_helper.resolve_mime_type("audio.opus") == "audio/ogg"
    assert gemini_helper.resolve_mime_type("audio.mp3") == "audio/mpeg"
    assert gemini_helper.resolve_mime_type("video.mp4") == "video/mp4"


def test_resolve_mime_type_defaults_for_unknown_extension(mocker):
    """resolve_mime_type falls back to octet-stream for extensions mimetypes cannot map.

    Uses .zzz rather than .bin: mimetypes resolves .bin to application/octet-stream
    itself, so it never reaches the default and leaves that branch uncovered.
    """
    gemini_helper = GeminiHelper(mocker.MagicMock())
    assert gemini_helper.resolve_mime_type("mystery.zzz") == "application/octet-stream"
    assert gemini_helper.resolve_mime_type("no_extension") == "application/octet-stream"


def test_upload_and_wait_for_file_name_none(mocker):
    """upload_and_wait_for_file raises AttributeError when upload returns no name."""
    mock_client = mocker.MagicMock()
    mock_file = mocker.MagicMock()
    mock_file.name = None
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(AttributeError):
        GeminiHelper(mock_client).upload_and_wait_for_file("path", "audio/ogg", 1)


def test_upload_and_wait_for_file_name_none_after_polling(mocker):
    """upload_and_wait_for_file raises AttributeError when the polled file has no name.

    The pre-loop check only sees the upload response; callers cast .name on the
    returned object, so the polled result must be validated too.
    """
    mock_client = mocker.MagicMock()
    mocker.patch("services.time.sleep")

    mock_file_proc = mocker.MagicMock()
    mock_file_proc.name = "name"
    mock_file_proc.state = "PROCESSING"

    mock_file_done = mocker.MagicMock()
    mock_file_done.name = None
    mock_file_done.state = "ACTIVE"
    mock_file_done.uri = "uri"
    mock_file_done.mime_type = "audio/ogg"

    mock_client.files.upload.return_value = mock_file_proc
    mock_client.files.get.return_value = mock_file_done

    with pytest.raises(AttributeError):
        GeminiHelper(mock_client).upload_and_wait_for_file("path", "audio/ogg", 1)


def test_upload_and_wait_for_file_missing_uri(mocker):
    """upload_and_wait_for_file raises AttributeError when uri or mime_type is None."""
    mock_client = mocker.MagicMock()
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "ACTIVE"
    mock_file.uri = None
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(AttributeError):
        GeminiHelper(mock_client).upload_and_wait_for_file("path", "audio/ogg", 1)


def test_delete_file_forwards_name_to_client(mocker):
    """Test delete_file passes the file name through to the client's files.delete."""
    mock_client = mocker.MagicMock()

    GeminiHelper(mock_client).delete_file("files/mock123")

    mock_client.files.delete.assert_called_once_with(name="files/mock123")


def test_get_remaining_quota(mocker):
    """get_remaining_quota returns remaining count from window stats."""
    mock_rate_limiter = mocker.MagicMock()
    mock_rate_limiter.get_window_stats.return_value = WindowStats(
        reset_time=9999999999.0,
        remaining=7,
    )
    quota_manager = QuotaManager(mock_rate_limiter, parse_rate_limit("5 per minute"))

    result = quota_manager.get_remaining_quota(user_id=123, daily_limit=10)

    assert result == 7


def test_check_quota_raises_immediately_when_daily_limit_zero(mocker):
    """check_quota raises LimitExceededError without touching Redis when limit is 0."""
    mock_rate_limiter = mocker.MagicMock()
    quota_manager = QuotaManager(mock_rate_limiter, parse_rate_limit("5 per minute"))

    with pytest.raises(LimitExceededError):
        quota_manager.check_quota(user_id=1, daily_limit=0)

    mock_rate_limiter.hit.assert_not_called()


def test_get_remaining_quota_returns_zero_when_daily_limit_zero(mocker):
    """get_remaining_quota returns 0 without touching Redis when limit is 0."""
    mock_rate_limiter = mocker.MagicMock()
    quota_manager = QuotaManager(mock_rate_limiter, parse_rate_limit("5 per minute"))

    result = quota_manager.get_remaining_quota(user_id=1, daily_limit=0)

    assert result == 0
    mock_rate_limiter.get_window_stats.assert_not_called()


def test_check_quota_uses_per_user_redis_key(mocker):
    """check_quota hits the Redis key scoped to the user (RPD:{user_id})."""
    mock_rate_limiter = mocker.MagicMock()
    mock_rate_limiter.hit.return_value = True
    quota_manager = QuotaManager(mock_rate_limiter, parse_rate_limit("5 per minute"))

    quota_manager.check_quota(user_id=456, daily_limit=5)

    assert mock_rate_limiter.hit.call_args_list[0].args[1] == "RPD:456"


def test_check_quota_raises_when_daily_redis_counter_exhausted(mocker):
    """check_quota raises LimitExceededError when the daily counter is exhausted."""
    mock_rate_limiter = mocker.MagicMock()
    mock_rate_limiter.hit.return_value = False
    quota_manager = QuotaManager(mock_rate_limiter, parse_rate_limit("5 per minute"))

    with pytest.raises(LimitExceededError):
        quota_manager.check_quota(user_id=789, daily_limit=3)


def test_check_quota_precheck_rejects_an_exhausted_daily_window():
    """The quantity=0 pre-check rejects once the real daily window is spent.

    Driven by a real FixedWindowRateLimiter rather than a mock: the bug this
    guards against lived in the limiter's semantics, where hit(cost=0)
    increments by nothing and so reports a spent window as still open.
    """
    quota_manager = QuotaManager(
        FixedWindowRateLimiter(MemoryStorage()),
        parse_rate_limit("100 per minute"),
    )

    quota_manager.check_quota(user_id=42, daily_limit=2, quantity=0)
    quota_manager.check_quota(user_id=42, daily_limit=2, quantity=1)
    quota_manager.check_quota(user_id=42, daily_limit=2, quantity=1)

    assert quota_manager.get_remaining_quota(user_id=42, daily_limit=2) == 0
    with pytest.raises(LimitExceededError):
        quota_manager.check_quota(user_id=42, daily_limit=2, quantity=0)


def test_check_quota_precheck_consumes_nothing():
    """The quantity=0 pre-check leaves the daily budget untouched."""
    quota_manager = QuotaManager(
        FixedWindowRateLimiter(MemoryStorage()),
        parse_rate_limit("100 per minute"),
    )

    for _ in range(5):
        quota_manager.check_quota(user_id=7, daily_limit=3, quantity=0)

    assert quota_manager.get_remaining_quota(user_id=7, daily_limit=3) == 3


def test_check_quota_sleeps_when_per_minute_limited(mocker):
    """check_quota sleeps until the window resets and retries the per-minute hit."""
    fixed_now = 1_000_000.0
    mocker.patch("services.time.time", return_value=fixed_now)
    mock_sleep = mocker.patch("services.time.sleep")

    mock_rate_limiter = mocker.MagicMock()
    mock_rate_limiter.hit.side_effect = [
        True,
        False,
        True,
    ]  # daily passes, per-minute blocked, retry ok
    mock_rate_limiter.get_window_stats.return_value = WindowStats(
        reset_time=fixed_now + 7.5,
        remaining=0,
    )
    quota_manager = QuotaManager(mock_rate_limiter, parse_rate_limit("5 per minute"))

    quota_manager.check_quota(user_id=321, daily_limit=5)

    mock_sleep.assert_called_once_with(7.5)


def test_tracer_shutdown_flushes_the_client(mocker):
    """Tracer.shutdown flushes buffered spans when Langfuse is configured."""
    mock_client = mocker.MagicMock()

    Tracer(mock_client).shutdown()

    mock_client.shutdown.assert_called_once_with()


def test_tracer_shutdown_is_a_noop_when_langfuse_disabled():
    """Tracer.shutdown does nothing when tracing is not configured."""
    Tracer(None).shutdown()


def test_observe_message_noop_when_langfuse_disabled(mocker):
    """observe_message is a no-op context manager when Langfuse is not configured."""
    mock_propagate = mocker.patch("services.propagate_attributes")

    with Tracer(None).observe_message(
        user_id=42,
        content_type="voice",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        thinking_level="HIGH",
    ):
        pass

    mock_propagate.assert_not_called()


def test_observe_message_names_and_tags_trace_when_langfuse_enabled(mocker):
    """observe_message names and attributes the trace, without opening a span."""
    mock_client = mocker.MagicMock()
    mock_propagate = mocker.patch("services.propagate_attributes")

    with Tracer(mock_client).observe_message(
        user_id=42,
        content_type="voice",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        thinking_level="HIGH",
    ):
        pass

    mock_client.start_as_current_observation.assert_not_called()
    mock_propagate.assert_called_once_with(
        trace_name="handle_message",
        user_id="42",
        tags=["voice"],
        metadata={
            "prompt_key": "basic_prompt_for_transcript",
            # Derived, not hardcoded: a hardcoded digest would turn every
            # prompt edit into a failing assertion with nothing to teach.
            "prompt_version": prompt_version("basic_prompt_for_transcript"),
            "target_language": "English",
            "thinking_level": "HIGH",
        },
    )
