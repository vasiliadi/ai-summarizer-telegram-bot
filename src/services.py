import logging
import mimetypes
import time
from textwrap import dedent
from typing import TYPE_CHECKING, cast

from google.genai import types
from requests.exceptions import ReadTimeout
from rush.exceptions import DataChangedInStoreError, MismatchedDataError
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
    bot,
    gemini_client,
    per_day_limit,
    per_minute_limit,
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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type((ApiTelegramException, ReadTimeout)),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=True,
)
def reply_with_retry(
    message: "Message",
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
def get_file_with_retry(file_id: str) -> "File":
    """Get file information from Telegram, with retries on timeout.

    Args:
        file_id (str): The Telegram file ID to retrieve.

    Returns:
        File: The downloaded file information.

    """
    return bot.get_file(file_id)


def send_answer(message: "Message", answer: str) -> None:
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
def check_quota(quantity: int = 1) -> bool:
    """Check if the request is within rate limits and handle any delays.

    This function checks both daily and per-minute rate limits. If the daily limit
    is exceeded, it raises an exception. If the per-minute limit is exceeded, it
    waits until the limit resets.

    Args:
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
    rpd = per_day_limit.check(DAILY_LIMIT_KEY, quantity=quantity)
    if rpd.limited:
        msg = "The daily limit for requests has been exceeded"
        raise LimitExceededError(msg)
    rpm = per_minute_limit.check(MINUTE_LIMIT_KEY, quantity=quantity)
    if rpm.limited:
        time_to_reset = max(0, rpm.reset_after.total_seconds())
        time.sleep(time_to_reset)
    return True


def get_gemini_config(target_language: str) -> types.GenerateContentConfig:
    """Get Gemini config with system instruction."""
    return GEMINI_CONFIG.model_copy(
        update={
            "system_instruction": dedent(
                SYSTEM_INSTRUCTION.format(language=target_language),
            ).strip(),
        },
    )


def upload_and_wait_for_file(
    file: str,
    mime_type: str,
    sleep_time: int,
) -> types.File:
    """Upload a file to Gemini and wait for processing to finish."""
    uploaded_file = gemini_client.files.upload(
        file=file,
        config={"mime_type": mime_type},
    )
    if uploaded_file.name is None:
        raise AttributeError
    uploaded_file_name = uploaded_file.name
    while uploaded_file.state == "PROCESSING":
        time.sleep(sleep_time)
        uploaded_file = gemini_client.files.get(name=uploaded_file_name)
    if uploaded_file.state == "FAILED":
        raise ValueError(uploaded_file.state)
    if uploaded_file.uri is None or uploaded_file.mime_type is None:
        raise AttributeError
    return uploaded_file


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


def upload_and_wait_for_audio_file(
    file: str,
    mime_type: str,
    sleep_time: int,
) -> types.File:
    """Upload a file to Gemini and wait for processing to finish."""
    return upload_and_wait_for_file(
        file=file,
        mime_type=mime_type,
        sleep_time=sleep_time,
    )
