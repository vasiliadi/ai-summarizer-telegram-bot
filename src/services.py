from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

from langfuse import propagate_attributes
from limits import parse as parse_rate_limit
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

from config import DAILY_LIMIT_KEY, MINUTE_LIMIT_KEY
from exceptions import LimitExceededError
from prompts import prompt_version

if TYPE_CHECKING:
    from collections.abc import Generator

    import telebot
    from langfuse import Langfuse
    from limits import RateLimitItem
    from limits.strategies import FixedWindowRateLimiter
    from openai import OpenAI
    from telebot.types import File, Message
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class Messenger:
    """Handles all Telegram bot messaging with retry logic."""

    def __init__(self, bot: telebot.TeleBot) -> None:
        """Store the injected Telegram bot client."""
        self._bot = bot

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type((ApiTelegramException, ReadTimeout)),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=True,
    )
    def _reply_with_retry(
        self,
        message: Message,
        text: str,
        entities: list[dict[str, object]],
    ) -> None:
        """Send a reply with retry logic on Telegram API errors."""
        self._bot.reply_to(message, text, entities=entities)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(30),
        retry=retry_if_exception_type(ReadTimeout),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=True,
    )
    def get_file_with_retry(self, file_id: str) -> File:
        """Get file information from Telegram, with retries on timeout."""
        return self._bot.get_file(file_id)

    def send_answer(self, message: Message, answer: str) -> None:
        """Send a response message, splitting at Telegram's 4 096-code-unit limit."""
        text, entities = convert(answer)
        for index, (chunk_text, chunk_entities) in enumerate(
            split_entities(text, entities, max_utf16_len=4096),
        ):
            # Pace the follow-up chunks; Telegram throttles back-to-back sends.
            if index:
                time.sleep(1)
            self._reply_with_retry(
                message,
                chunk_text,
                entities=[entity.to_dict() for entity in chunk_entities],
            )


class QuotaManager:
    """Enforces per-user daily and global per-minute rate limits."""

    def __init__(
        self,
        rate_limiter: FixedWindowRateLimiter,
        per_minute_rate: RateLimitItem,
    ) -> None:
        """Store the injected rate limiter and its parsed per-minute rate."""
        self._rate_limiter = rate_limiter
        self._per_minute_rate = per_minute_rate

    def check_quota(self, user_id: int, daily_limit: int, quantity: int = 1) -> None:
        """Enforce rate limits; raise if daily exceeded; sleep on per-minute.

        Raises:
            LimitExceededError: If the user's daily budget is already spent.

        """
        if daily_limit <= 0:
            msg = "The daily limit for requests has been exceeded"
            raise LimitExceededError(msg)
        daily_rate = parse_rate_limit(f"{daily_limit} per day")
        daily_key = f"{DAILY_LIMIT_KEY}:{user_id}"
        # test(), not hit(cost=0), which reads an exhausted window as open. See
        # architecture.md → *Quota model*.
        if quantity == 0:
            allowed = self._rate_limiter.test(daily_rate, daily_key)
        else:
            allowed = self._rate_limiter.hit(daily_rate, daily_key, cost=quantity)
        if not allowed:
            msg = "The daily limit for requests has been exceeded"
            raise LimitExceededError(msg)
        while not self._rate_limiter.hit(
            self._per_minute_rate,
            MINUTE_LIMIT_KEY,
            cost=quantity,
        ):
            stats = self._rate_limiter.get_window_stats(
                self._per_minute_rate,
                MINUTE_LIMIT_KEY,
            )
            time.sleep(max(0.0, stats.reset_time - time.time()))

    def get_remaining_quota(self, user_id: int, daily_limit: int) -> int:
        """Return remaining daily requests for a user without consuming quota."""
        if daily_limit <= 0:
            return 0
        daily_rate = parse_rate_limit(f"{daily_limit} per day")
        stats = self._rate_limiter.get_window_stats(
            daily_rate,
            f"{DAILY_LIMIT_KEY}:{user_id}",
        )
        return max(0, stats.remaining)


class OpenRouterFiles:
    """Uploads documents to OpenRouter's Files API and deletes them afterwards."""

    def __init__(self, client: OpenAI) -> None:
        """Store the injected `openai` client, pointed at OpenRouter."""
        self._client = client

    def upload(self, file: str, mime_type: str) -> str:
        """Upload a local file and return its `or_file_…` id."""
        path = Path(file)
        with path.open("rb") as handle:
            uploaded = self._client.files.create(
                file=(path.name, handle, mime_type),
                purpose="user_data",
            )
        return uploaded.id

    def delete(self, file_id: str) -> None:
        """Delete an uploaded file; OpenRouter never expires one on its own."""
        self._client.files.delete(file_id)


class Tracer:
    """Names and attributes whatever Langfuse spans one Telegram message produces."""

    def __init__(self, client: Langfuse | None) -> None:
        """Store the injected Langfuse client (None when tracing is disabled)."""
        self._client = client

    def shutdown(self) -> None:
        """Flush buffered spans; a no-op when tracing is not configured."""
        if self._client is not None:
            self._client.shutdown()

    @contextmanager
    def observe_message(
        self,
        user_id: int,
        content_type: str,
        prompt_key: str,
        target_language: str,
        thinking_level: str,
    ) -> Generator[None]:
        """Name and attribute whatever trace one Telegram message produces.

        Opens no span itself, and is a no-op without Langfuse; see architecture.md
        → *Tracing (optional), text input only*.
        """
        if self._client is None:
            yield
            return
        with propagate_attributes(
            trace_name="handle_message",
            user_id=str(user_id),
            tags=[content_type],
            metadata={
                "prompt_key": prompt_key,
                "prompt_version": prompt_version(prompt_key),
                "target_language": target_language,
                "thinking_level": thinking_level,
            },
        ):
            yield
