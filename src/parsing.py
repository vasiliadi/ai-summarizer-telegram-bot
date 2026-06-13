from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, cast

from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import exa_client, tavily_client
from domain import PrefixedText
from exceptions import WebParseError

if TYPE_CHECKING:
    from exa_py import Exa
    from tavily import TavilyClient
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class ParserBackend(ABC):
    """Abstract base for URL content-extraction backends."""

    prefix: str

    @abstractmethod
    def parse(self, url: str) -> str:
        """Extract main textual content from a URL."""


class ExaBackend(ParserBackend):
    """Exa.ai URL extraction backend."""

    prefix = "🌐"

    def __init__(self, client: Exa) -> None:
        """Store the injected Exa client."""
        self._client = client

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(WebParseError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=True,
    )
    def parse(self, url: str) -> str:
        """Extract main textual content from a URL using Exa.ai.

        Raises:
            WebParseError: If Exa returns no results or empty content. Retried
                once (2 total attempts) before re-raising.

        """
        response = self._client.get_contents(
            urls=[url],
            text={"max_characters": 20000, "include_html_tags": True},
        )
        results = response.results or []
        if not results:
            msg = f"Exa could not extract content from {url}"
            logger.warning(msg)
            raise WebParseError(msg)
        content = (results[0].text or "").strip()
        if not content:
            msg = f"Exa returned empty content for {url}"
            logger.warning(msg)
            raise WebParseError(msg)
        return content


class TavilyBackend(ParserBackend):
    """Tavily URL extraction backend."""

    prefix = "🕸️"

    def __init__(self, client: TavilyClient) -> None:
        """Store the injected Tavily client."""
        self._client = client

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(TavilyTimeoutError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def parse(self, url: str) -> str:
        """Extract main textual content from a URL using Tavily.

        Raises:
            WebParseError: If Tavily returns no results or empty content.
            RetryError: If Tavily keeps timing out after all retry attempts.

        """
        response = self._client.extract(urls=[url], format="markdown")
        results = response.get("results") or []
        if not results:
            failed = response.get("failed_results") or []
            msg = f"Tavily could not extract content from {url}: {failed}"
            logger.warning(msg)
            raise WebParseError(msg)
        content = (results[0].get("raw_content") or "").strip()
        if not content:
            msg = f"Tavily returned empty content for {url}"
            logger.warning(msg)
            raise WebParseError(msg)
        return content


class WebParser:
    """Orchestrates URL parsing with a primary→fallback backend strategy."""

    def __init__(self, primary: ParserBackend, fallback: ParserBackend) -> None:
        """Store the primary and fallback backends."""
        self._primary = primary
        self._fallback = fallback

    def parse(self, url: str) -> PrefixedText:
        """Extract main textual content from a URL.

        Parses with the primary backend first, falls back to the secondary on
        failure.

        Returns:
            PrefixedText: The extracted content and source display prefix.

        Raises:
            WebParseError: If both backends fail.
            Exception: Any non-retryable primary error propagates immediately
                without attempting the fallback.

        """
        try:
            return PrefixedText(
                text=self._primary.parse(url),
                prefix=self._primary.prefix,
            )
        except WebParseError as primary_error:
            logger.warning(
                "Exa parsing backend failed, falling back to Tavily: %s",
                primary_error,
            )
            try:
                return PrefixedText(
                    text=self._fallback.parse(url),
                    prefix=self._fallback.prefix,
                )
            except (WebParseError, RetryError) as fallback_error:
                logger.warning(
                    "Tavily fallback backend also failed: %s",
                    fallback_error,
                )
                msg = "Both parsing backends failed"
                raise WebParseError(msg) from fallback_error


web_parser = WebParser(ExaBackend(exa_client), TavilyBackend(tavily_client))


def parse_url(url: str) -> PrefixedText:
    """Extract main textual content from a URL via the default WebParser."""
    return web_parser.parse(url)
