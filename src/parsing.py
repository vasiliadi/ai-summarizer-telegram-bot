from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import DEFAULT_PARSING_BACKEND, exa_client, tavily_client
from exceptions import WebParseError

if TYPE_CHECKING:
    from tenacity import (
        _utils as tenacity_utils,
    )

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(5),
    retry=retry_if_exception_type(TavilyTimeoutError),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def _parse_with_tavily(url: str) -> str:
    """Extract main textual content from a URL using Tavily.

    Args:
        url (str): The webpage URL to parse.

    Returns:
        str: The extracted page content as markdown text.

    Raises:
        WebParseError: If Tavily returns no successful results or empty content.
        RetryError: If Tavily keeps timing out after all retry attempts. The
            function is decorated with @retry and makes 2 total attempts (1
            retry with a 5-second wait) before raising RetryError.

    """
    response = tavily_client.extract(urls=[url], format="markdown")
    results = response.get("results") or []
    if not results:
        failed = response.get("failed_results") or []
        msg = f"Tavily could not extract content from {url}: {failed}"
        raise WebParseError(msg)
    content = (results[0].get("raw_content") or "").strip()
    if not content:
        msg = f"Tavily returned empty content for {url}"
        raise WebParseError(msg)
    return content


def _parse_with_exa(url: str) -> str:
    """Extract main textual content from a URL using Exa.ai.

    Args:
        url (str): The webpage URL to parse.

    Returns:
        str: The extracted page content as text (HTML tags included).

    Raises:
        WebParseError: If Exa returns no results or empty content.

    """
    result = exa_client.get_contents(
        urls=[url],
        text={"max_characters": 20000, "include_html_tags": True},
    )
    results = result.results or []
    if not results:
        msg = f"Exa could not extract content from {url}"
        raise WebParseError(msg)
    content = (results[0].text or "").strip()
    if not content:
        msg = f"Exa returned empty content for {url}"
        raise WebParseError(msg)
    return content


def parse_url(url: str, backend: str = DEFAULT_PARSING_BACKEND) -> str:
    """Extract main textual content from a URL using the selected backend.

    Args:
        url (str): The webpage URL to parse.
        backend (str): Parsing backend to use, "tavily" or "exa". Defaults to
            DEFAULT_PARSING_BACKEND.

    Returns:
        str: The extracted page content.

    Raises:
        WebParseError: If the backend is unknown, or the selected backend
            returns no successful results or empty content.
        RetryError: If the Tavily backend keeps timing out after all retry
            attempts (see _parse_with_tavily).

    """
    if backend == "tavily":
        return _parse_with_tavily(url)
    if backend == "exa":
        return _parse_with_exa(url)
    msg = f"Unknown parsing backend: {backend}"
    raise WebParseError(msg)
