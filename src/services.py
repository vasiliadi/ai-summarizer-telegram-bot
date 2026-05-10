import logging
import math
import mimetypes
import time
from textwrap import dedent
from typing import TYPE_CHECKING, Any, cast

from google.genai import types
from requests.exceptions import ReadTimeout
from rush import quota, throttle
from rush.exceptions import DataChangedInStoreError, MismatchedDataError
from rush.limiters import periodic
from telebot.apihelper import ApiTelegramException
from telegramify_markdown import convert, split_entities
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import (
    DAILY_LIMIT_KEY,
    GEMINI_CONFIG,
    MINUTE_LIMIT_KEY,
    MODELS_WITH_THINKING_SUPPORT,
    bot,
    gemini_client,
    per_minute_limit,
    rate_limiter_store,
)
from exceptions import LimitExceededError
from prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from telebot.types import File, Message
    from tenacity import (
        _utils as tenacity_utils,
    )

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


def choose_yt_audio_format(info: dict[str, Any]) -> str:
    """Return the most suitable audio format id for a YouTube video.

    Prefer audio-only formats when yt-dlp exposes them. Fall back to the
    combined format selector when the extractor does not provide a concrete
    audio-only id.

    """
    formats = info.get("formats") or []
    audio_only_formats = [
        fmt
        for fmt in formats
        if fmt.get("acodec") not in (None, "none") and fmt.get("vcodec") == "none"
    ]
    if not audio_only_formats:
        return "bestaudio/worst[acodec!=none]"

    def sort_key(fmt: dict[str, Any]) -> tuple[float, float]:
        abr = fmt.get("abr")
        tbr = fmt.get("tbr")
        return (
            float(abr) if abr is not None else math.inf,
            float(tbr) if tbr is not None else math.inf,
        )

    return str(min(audio_only_formats, key=sort_key)["format_id"])


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type((ApiTelegramException, ReadTimeout)),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=True,
)
def reply_with_retry(
    message: Message,
    text: str,
    entities: list[dict[str, object]] | None = None,
) -> None:
    """Send a reply to a Telegram message with retry logic.

    This function attempts to reply to a Telegram message using the bot's
    reply_to method. If an ApiTelegramException occurs, it retries up to 3
    times with a 1-second wait between attempts.

    Args:
        message (Message): The Telegram message to reply to.
        text (str): The text content of the reply.
        entities (list[dict[str, object]] | None): Optional list of message
            entities for formatting.

    Returns:
        None

    """
    if entities is None:
        bot.reply_to(message, text)
    else:
        bot.reply_to(message, text, entities=entities)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(ReadTimeout),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=True,
)
def get_file_with_retry(file_id: str) -> File:
    """Get file information from Telegram, with retries on timeout.

    Args:
        file_id (str): The Telegram file ID to retrieve.

    Returns:
        File: The downloaded file information.

    """
    return bot.get_file(file_id)


def send_answer(message: Message, answer: str) -> None:
    """Send a response message to the user.

    This function handles sending messages through the Telegram bot, including:
    - Converting Markdown to Telegram entities
    - Splitting long messages into chunks if they exceed Telegram's UTF-16 limit
    - Retrying Telegram API failures up to 3 times with a 1-second wait

    Args:
        message (Message): The original Telegram message to reply to
        answer (str): The text content to send as a response

    Returns:
        None

    Note:
        - Messages longer than 4096 UTF-16 code units are automatically split
        - There is a 1-second delay between sending chunks of split messages

    """
    text, entities = convert(answer)
    chunks_iter = iter(split_entities(text, entities, max_utf16_len=4096))
    current = next(chunks_iter, None)
    while current is not None:
        chunk_text, chunk_entities = current
        if chunk_text.strip():
            serialized_entities = [entity.to_dict() for entity in chunk_entities]
            reply_with_retry(message, chunk_text, entities=serialized_entities)
        next_chunk = next(chunks_iter, None)
        if next_chunk is not None:
            time.sleep(1)
        current = next_chunk


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(
        (DataChangedInStoreError, MismatchedDataError),
    ),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def check_quota(user_id: int, daily_limit: int, quantity: int = 1) -> bool:
    """Check if the request is within rate limits and handle any delays.

    This function checks both daily (per-user) and per-minute (global) rate limits.
    If the daily limit is exceeded, it raises an exception. If the per-minute limit
    is exceeded, it waits until the limit resets.

    Args:
        user_id (int): Telegram user ID whose daily cap to enforce.
        daily_limit (int): The user's configured daily request cap.
        quantity (int, optional): Number of quota units to check. Defaults to 1.

    Returns:
        bool: True if the request is allowed to proceed.

    Raises:
        LimitExceededError: If the daily request limit has been exceeded.
        RetryError: If store data errors persist after all retry attempts.

    Note:
        - The function will automatically sleep if the per-minute limit is reached
        - Daily limits cannot be bypassed and will raise an exception

    """
    if daily_limit <= 0:
        msg = "The daily limit for requests has been exceeded"
        raise LimitExceededError(msg)
    per_day_limit = throttle.Throttle(
        limiter=periodic.PeriodicLimiter(
            store=rate_limiter_store,
        ),
        rate=quota.Quota.per_day(
            count=daily_limit,
        ),
    )
    rpd = per_day_limit.check(f"{DAILY_LIMIT_KEY}:{user_id}", quantity=quantity)
    if rpd.limited:
        msg = "The daily limit for requests has been exceeded"
        raise LimitExceededError(msg)
    rpm = per_minute_limit.check(MINUTE_LIMIT_KEY, quantity=quantity)
    if rpm.limited:
        time_to_reset = max(0, rpm.reset_after.total_seconds())
        time.sleep(time_to_reset)
    return True


def get_remaining_quota(user_id: int, daily_limit: int) -> int:
    """Return remaining daily requests for a user without consuming quota.

    Args:
        user_id (int): Telegram user ID.
        daily_limit (int): The user's configured daily request cap.

    Returns:
        int: Number of requests still available today.

    """
    if daily_limit <= 0:
        return 0
    per_day_limit = throttle.Throttle(
        limiter=periodic.PeriodicLimiter(
            store=rate_limiter_store,
        ),
        rate=quota.Quota.per_day(
            count=daily_limit,
        ),
    )
    result = per_day_limit.check(f"{DAILY_LIMIT_KEY}:{user_id}", quantity=0)
    return max(0, result.remaining)


def get_gemini_config(
    target_language: str,
    model: str = "",
    extra_system_instruction: str | None = None,
) -> types.GenerateContentConfig:
    """Get Gemini config with system instruction.

    Selects a config with or without thinking support based on the model.

    """
    system_instruction = dedent(
        SYSTEM_INSTRUCTION.format(language=target_language),
    ).strip()
    if extra_system_instruction is not None:
        system_instruction = (
            f"{system_instruction}\n\n{extra_system_instruction.strip()}"
        )
    return GEMINI_CONFIG.model_copy(
        update={
            "system_instruction": system_instruction,
            "thinking_config": (
                types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH)
                if model in MODELS_WITH_THINKING_SUPPORT
                else None
            ),
        },
    )


def resolve_mime_type(file: str) -> str:
    """Resolve the MIME type for a file path, with fallbacks."""
    mime_type = mimetypes.guess_type(file)[0]
    if mime_type is None:
        if file.endswith((".ogg", ".opus")):
            return "audio/ogg"
        if file.endswith(".mp3"):
            return "audio/mpeg"
        if file.endswith(".wav"):
            return "audio/wav"
        if file.endswith(".mp4"):
            return "video/mp4"
        return "application/octet-stream"
    return mime_type


def format_prefixed_summary(prefix: str, summary: str) -> str:
    """Format a prefixed summary with a stable blank line separator."""
    return f"{prefix}\n\n{summary.strip()}"


def upload_and_wait_for_audio_file(
    file: str,
    mime_type: str,
    sleep_time: int,
) -> types.File:
    """Upload a file to Gemini and wait for processing to finish."""
    audio_file = gemini_client.files.upload(file=file, config={"mime_type": mime_type})
    if audio_file.name is None:
        raise AttributeError
    audio_file_name = audio_file.name
    while audio_file.state == "PROCESSING":
        time.sleep(sleep_time)
        audio_file = gemini_client.files.get(name=audio_file_name)
    if audio_file.state == "FAILED":
        raise ValueError(audio_file.state)
    if audio_file.uri is None or audio_file.mime_type is None:
        raise AttributeError
    return audio_file
