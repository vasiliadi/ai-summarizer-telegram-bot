import httpx
import pytest
from limits import parse as parse_rate_limit
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from limits.util import WindowStats
from openai import APIStatusError, OpenAI

from exceptions import LimitExceededError
from prompts import prompt_version
from services import Messenger, OpenRouterFiles, QuotaManager, Tracer


def _make_openrouter_files(handler):
    """Return an OpenRouterFiles on a real `openai` client answered by `handler`."""
    client = OpenAI(
        api_key="mock_openrouter_key",
        base_url="https://openrouter.ai/api/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return OpenRouterFiles(client)


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


def test_upload_posts_the_file_and_returns_its_id(tmp_path):
    """Test upload sends the file as multipart and returns its `or_file_…` id."""
    document = tmp_path / "report"
    document.write_bytes(b"%PDF-1.7 mock")
    requests = []

    def handler(request):
        requests.append((request, request.read()))
        return httpx.Response(
            200,
            json={
                "id": "or_file_mock123",
                "object": "file",
                "bytes": 13,
                "created_at": 1790951515,
                "filename": "report",
                "purpose": "user_data",
                "status": "processed",
            },
        )

    file_id = _make_openrouter_files(handler).upload(
        file=str(document),
        mime_type="application/pdf",
    )

    assert file_id == "or_file_mock123"
    ((request, body),) = requests
    assert request.method == "POST"
    assert request.url == "https://openrouter.ai/api/v1/files"
    assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="purpose"\r\n\r\nuser_data' in body
    assert b'name="file"; filename="report"' in body
    assert b"Content-Type: application/pdf" in body
    assert b"%PDF-1.7 mock" in body


def test_upload_raises_the_sdk_error_on_a_refused_file(tmp_path):
    """Test a refused upload surfaces as the `openai` error the summarizer retries."""
    document = tmp_path / "report"
    document.write_bytes(b"mock")

    refused = httpx.Response(413, json={"error": {"message": "File too large"}})

    with pytest.raises(APIStatusError):
        _make_openrouter_files(lambda _: refused).upload(
            file=str(document),
            mime_type="application/pdf",
        )


def test_delete_removes_the_file_by_id():
    """Test delete calls DELETE on the uploaded file's own path."""
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": "or_file_mock123", "object": "file", "deleted": True},
        )

    _make_openrouter_files(handler).delete("or_file_mock123")

    (request,) = requests
    assert request.method == "DELETE"
    assert request.url == "https://openrouter.ai/api/v1/files/or_file_mock123"


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
        thinking_level="high",
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
        thinking_level="high",
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
            "thinking_level": "high",
        },
    )
