from __future__ import annotations

import logging
import mimetypes
import time
from functools import lru_cache
from textwrap import dedent
from typing import TYPE_CHECKING, cast

from google.genai import types
from limits import parse as _parse_rate_limit
from requests.exceptions import ReadTimeout
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
    per_minute_rate,
    rate_limiter,
)
from domain import PrefixedText, format_prefixed_summary
from exceptions import LimitExceededError
from prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from telebot.types import File, Message
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)
parse_rate_limit = lru_cache(maxsize=64)(_parse_rate_limit)


class Messenger:
    """Handles all Telegram bot messaging with retry logic."""

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type((ApiTelegramException, ReadTimeout)),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=True,
    )
    def _reply_with_retry(
        message: Message,
        text: str,
        entities: list[dict[str, object]] | None = None,
    ) -> None:
        """Send a reply with retry logic on Telegram API errors."""
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
    def get_file_with_retry(self, file_id: str) -> File:
        """Get file information from Telegram, with retries on timeout."""
        return bot.get_file(file_id)

    def send_answer(self, message: Message, answer: str) -> None:
        """Send a response message, splitting at Telegram's 4 096-code-unit limit."""
        text, entities = convert(answer)
        chunks_iter = iter(split_entities(text, entities, max_utf16_len=4096))
        current = next(chunks_iter, None)
        while current is not None:
            chunk_text, chunk_entities = current
            serialized_entities = [entity.to_dict() for entity in chunk_entities]
            self._reply_with_retry(message, chunk_text, entities=serialized_entities)
            next_chunk = next(chunks_iter, None)
            if next_chunk is not None:
                time.sleep(1)
            current = next_chunk


class QuotaManager:
    """Enforces per-user daily and global per-minute rate limits."""

    def check_quota(self, user_id: int, daily_limit: int, quantity: int = 1) -> bool:
        """Enforce rate limits; raise if daily exceeded; sleep on per-minute."""
        if daily_limit <= 0:
            msg = "The daily limit for requests has been exceeded"
            raise LimitExceededError(msg)
        daily_rate = parse_rate_limit(f"{daily_limit} per day")
        if not rate_limiter.hit(
            daily_rate,
            f"{DAILY_LIMIT_KEY}:{user_id}",
            cost=quantity,
        ):
            msg = "The daily limit for requests has been exceeded"
            raise LimitExceededError(msg)
        while not rate_limiter.hit(per_minute_rate, MINUTE_LIMIT_KEY, cost=quantity):
            stats = rate_limiter.get_window_stats(per_minute_rate, MINUTE_LIMIT_KEY)
            time.sleep(max(0.0, stats.reset_time - time.time()))
        return True

    def get_remaining_quota(self, user_id: int, daily_limit: int) -> int:
        """Return remaining daily requests for a user without consuming quota."""
        if daily_limit <= 0:
            return 0
        daily_rate = parse_rate_limit(f"{daily_limit} per day")
        stats = rate_limiter.get_window_stats(
            daily_rate,
            f"{DAILY_LIMIT_KEY}:{user_id}",
        )
        return max(0, stats.remaining)


_EXT_MIME_FALLBACK = {
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
}


class GeminiHelper:
    """Utilities for Gemini model configuration and file management."""

    def get_gemini_config(
        self,
        target_language: str,
        thinking_level: str,
    ) -> types.GenerateContentConfig:
        """Get Gemini config with system instruction and thinking enabled."""
        system_instruction = dedent(
            SYSTEM_INSTRUCTION.format(language=target_language),
        ).strip()
        return GEMINI_CONFIG.model_copy(
            update={
                "system_instruction": system_instruction,
                "thinking_config": types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel(thinking_level),
                ),
            },
        )

    def resolve_mime_type(self, file: str) -> str:
        """Resolve the MIME type for a file path, with fallbacks."""
        mime_type = mimetypes.guess_type(file)[0]
        if mime_type is not None:
            return mime_type
        for ext, mt in _EXT_MIME_FALLBACK.items():
            if file.endswith(ext):
                return mt
        return "application/octet-stream"

    def upload_and_wait_for_file(
        self,
        file: str,
        mime_type: str,
        sleep_time: int,
    ) -> types.File:
        """Upload a file to Gemini and wait for processing to finish."""
        uploaded = gemini_client.files.upload(
            file=file,
            config={"mime_type": mime_type},
        )
        if uploaded.name is None:
            raise AttributeError
        file_name = uploaded.name
        while uploaded.state == "PROCESSING":
            time.sleep(sleep_time)
            uploaded = gemini_client.files.get(name=file_name)
        if uploaded.state == "FAILED":
            raise ValueError(uploaded.state)
        if uploaded.uri is None or uploaded.mime_type is None:
            raise AttributeError
        return uploaded


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

messenger = Messenger()
quota_manager = QuotaManager()
gemini_helper = GeminiHelper()


# ---------------------------------------------------------------------------
# Module-level aliases — keep the existing public API intact so that
# all importers and mocker.patch("services.*") calls continue to work.
# ---------------------------------------------------------------------------

_reply_with_retry = messenger._reply_with_retry  # noqa: SLF001
get_file_with_retry = messenger.get_file_with_retry
send_answer = messenger.send_answer

check_quota = quota_manager.check_quota
get_remaining_quota = quota_manager.get_remaining_quota

get_gemini_config = gemini_helper.get_gemini_config
resolve_mime_type = gemini_helper.resolve_mime_type
upload_and_wait_for_file = gemini_helper.upload_and_wait_for_file


# Re-export domain types so existing `from services import PrefixedText` imports work.
__all__ = [
    "PrefixedText",
    "_reply_with_retry",
    "check_quota",
    "format_prefixed_summary",
    "gemini_helper",
    "get_file_with_retry",
    "get_gemini_config",
    "get_remaining_quota",
    "messenger",
    "quota_manager",
    "resolve_mime_type",
    "send_answer",
    "upload_and_wait_for_file",
]
