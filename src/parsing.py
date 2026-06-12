from __future__ import annotations

import logging
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
        logger.warning(msg)
        raise WebParseError(msg)
    content = (results[0].get("raw_content") or "").strip()
    if not content:
        msg = f"Tavily returned empty content for {url}"
        logger.warning(msg)
        raise WebParseError(msg)
    return content


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(5),
    retry=retry_if_exception_type(WebParseError),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=True,
)
def _parse_with_exa(url: str) -> str:
    """Extract main textual content from a URL using Exa.ai.

    Args:
        url (str): The webpage URL to parse.

    Returns:
        str: The extracted page content as text (HTML tags included).

    Raises:
        WebParseError: If Exa returns no results or empty content. Exa's
            get_contents is intermittent and may return an empty result for a
            URL it can normally extract, so the function is decorated with
            @retry and makes 2 total attempts (1 retry with a 5-second wait)
            before re-raising WebParseError.

    """
    response = exa_client.get_contents(
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


def parse_url(url: str) -> str:
    """Extract main textual content from a URL.

    Parses with Tavily first and falls back to Exa.ai when Tavily fails.

    Args:
        url (str): The webpage URL to parse.

    Returns:
        str: The extracted page content.

    Raises:
        WebParseError: If both the Tavily and Exa.ai backends fail to return
            usable content.
        Exception: Any non-retryable error raised by the Tavily backend
            propagates immediately without attempting the Exa.ai fallback.

    """
    try:
        return _parse_with_tavily(url)
    except (WebParseError, RetryError) as tavily_error:
        logger.warning(
            "Tavily parsing backend failed, falling back to Exa: %s",
            tavily_error,
        )
        try:
            return _parse_with_exa(url)
        except WebParseError as exa_error:
            logger.warning("Exa fallback backend also failed: %s", exa_error)
            msg = "Both parsing backends failed"
            raise WebParseError(msg) from exa_error
