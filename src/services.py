from __future__ import annotations

import logging
import mimetypes
import time
from contextlib import contextmanager
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

if TYPE_CHECKING:
    from collections.abc import Generator

    import telebot
    from google import genai
    from google.genai import types
    from langfuse import Langfuse
    from limits import RateLimitItem
    from limits.strategies import FixedWindowRateLimiter
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
        # quantity=0 is the non-consuming pre-check. hit(cost=0) increments by
        # nothing, so an exhausted window still compares <= the limit and reads
        # as open; test() asks whether one more unit would fit, without taking it.
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


class GeminiHelper:
    """Utilities for Gemini file management."""

    def __init__(self, client: genai.Client) -> None:
        """Store the injected Gemini client."""
        self._client = client

    def resolve_mime_type(self, file: str) -> str:
        """Resolve the MIME type for a file path, defaulting to octet-stream."""
        return mimetypes.guess_type(file)[0] or "application/octet-stream"

    def upload_and_wait_for_file(
        self,
        file: str,
        mime_type: str,
        sleep_time: int = 10,
    ) -> types.File:
        """Upload a file to Gemini and wait for processing to finish.

        `sleep_time` is the interval between polls of the processing state.
        """
        uploaded = self._client.files.upload(
            file=file,
            config={"mime_type": mime_type},
        )
        if uploaded.name is None:
            raise AttributeError
        file_name = uploaded.name
        while uploaded.state == "PROCESSING":
            time.sleep(sleep_time)
            uploaded = self._client.files.get(name=file_name)
        if uploaded.state == "FAILED":
            raise ValueError(uploaded.state)
        # Re-check name on the polled object, not just the upload response:
        # callers rely on name/uri/mime_type all being set on what is returned.
        if uploaded.name is None or uploaded.uri is None or uploaded.mime_type is None:
            raise AttributeError
        return uploaded

    def delete_file(self, name: str) -> None:
        """Delete a file from the provider's file API."""
        self._client.files.delete(name=name)


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

        The three settings go in as metadata because nothing else records them:
        pydantic-ai exports only the six numeric OTel model settings, so the
        thinking level — provider-specific and a string — never reaches a span,
        and the other two would otherwise have to be parsed back out of the
        prompt wording. Recording them keeps a trace filterable and replayable
        as an evaluation dataset item. The model id needs no entry; it is
        already on the generation span.

        Opens no span itself, so a message whose model calls all carry an
        uploaded file — which `LLMClient` leaves uninstrumented — produces no
        trace at all. A no-op when Langfuse is not configured.
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
                "target_language": target_language,
                "thinking_level": thinking_level,
            },
        ):
            yield
