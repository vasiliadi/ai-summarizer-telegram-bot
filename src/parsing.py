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

from config import tavily_client
from exceptions import WebParseError

if TYPE_CHECKING:
    from tenacity import (
        _utils as tenacity_utils,
    )

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(TavilyTimeoutError),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def parse_url(url: str) -> str:
    """Extract main textual content from a URL using Tavily.

    Args:
        url (str): The webpage URL to parse.

    Returns:
        str: The extracted page content as markdown text.

    Raises:
        WebParseError: If Tavily returns no successful results or empty content.
        RetryError: If Tavily keeps timing out after all retry attempts. The
            function is decorated with @retry and retries TavilyTimeoutError up
            to 3 times with a 10-second wait before raising RetryError.

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
