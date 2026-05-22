from __future__ import annotations

import logging

from config import tavily_client
from exceptions import WebParseError

logger = logging.getLogger(__name__)


def parse_url(url: str) -> str:
    """Extract main textual content from a URL using Tavily.

    Args:
        url (str): The webpage URL to parse.

    Returns:
        str: The extracted page content as markdown text.

    Raises:
        WebParseError: If Tavily returns no successful results or empty content.

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
