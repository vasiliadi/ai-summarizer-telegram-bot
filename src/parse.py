from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

import requests
import trafilatura
from seleniumbase import SB

from config import WEB_SCRAPE_PROXY, headers, perplexity_client
from prompts import BASIC_PROMPT_FOR_PERPLEXITY

if TYPE_CHECKING:
    from collections.abc import Iterable

    from openai.types.chat.chat_completion_message_param import (
        ChatCompletionMessageParam,
    )


def parse_webpage_with_requests(url: str) -> str | None:
    """Parse webpage content using HTTP requests for static content.

    Args:
        url (str): The URL of the webpage to parse.

    Returns:
        str | None: The extracted text content, or None if extraction fails.

    Raises:
        requests.exceptions.HTTPError: If the HTTP response indicates an error status.

    Notes:
        - Uses a proxy defined in WEB_SCRAPE_PROXY for making requests
        - SSL verification is disabled
        - Uses trafilatura for content extraction
        - Request timeout is set to 60 seconds

    """
    proxies = {
        "http": WEB_SCRAPE_PROXY,
        "https": WEB_SCRAPE_PROXY,
    }
    downloaded = requests.get(
        requests.utils.requote_uri(url),
        verify=False,  # noqa: S501
        headers=headers,
        timeout=60,
        proxies=proxies,
    )
    downloaded.raise_for_status()
    return trafilatura.extract(downloaded.text)


def parse_webpage_with_browser(url: str) -> str | None:  # beta
    """Parse webpage content using a headless browser for JavaScript-rendered content.

    Args:
        url (str): The URL of the webpage to parse.

    Returns:
        str | None: The extracted text content, or None if extraction fails.

    Notes:
        - Uses SeleniumBase (SB) with undetected-chromedriver (uc) mode
        - Runs in headless mode with Xvfb virtual display
        - Ignores SSL certificate errors
        - Blocks images for faster loading
        - Uses configured proxy from WEB_SCRAPE_PROXY
        - Attempts to handle CAPTCHA challenges automatically
        - Currently in beta status

    Example:
        >>> content = parse_webpage_with_browser("https://example.com")
        >>> if content:
        ...     print("Successfully extracted content")

    """
    with SB(
        uc=True,
        xvfb=True,
        chromium_arg="--ignore-certificate-errors",
        block_images=True,
        proxy=WEB_SCRAPE_PROXY,
    ) as sb:
        sb.uc_open_with_reconnect(requests.utils.requote_uri(url), 4)
        sb.uc_gui_click_captcha()
        html = sb.get_page_source()

    return trafilatura.extract(html)


def parse_webpage_with_perplexity(url: str) -> str | None:
    """Parse webpage content using Perplexity.ai's LLM capabilities.

    This function processes a URL by:
    1. Cleaning the URL (removing query parameters and fragments)
    2. Sending the URL to Perplexity.ai's API with a predefined prompt
    3. Returning the AI-generated summary of the webpage

    Args:
        url (str): The URL of the webpage to parse and summarize.

    Returns:
        str | None: The AI-generated content summarizing the webpage,
                    or None if the operation fails.

    Notes:
        - Uses the llama-3.1-sonar-large-128k-online model
        - Removes URL query parameters and fragments before processing
        - Converts URL to lowercase for consistency
        - Requires a configured Perplexity API client (perplexity_client)
        - Uses a predefined prompt template

    Example:
        >>> content = parse_webpage_with_perplexity("https://example.com")
        >>> if content:
        ...     print("Successfully generated webpage summary")

    """
    url_parsed = urlparse(url)
    url = urlunparse(
        (url_parsed.scheme, url_parsed.netloc, url_parsed.path, "", "", ""),
    ).lower()
    prompt = f"{BASIC_PROMPT_FOR_PERPLEXITY} {url}"
    messages: Iterable[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": (
                "You are an artificial intelligence assistant and you need to "
                "engage in a helpful, detailed, polite conversation with a user."
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]
    response = perplexity_client.chat.completions.create(
        model="llama-3.1-sonar-large-128k-online",
        messages=messages,
    )
    return response.choices[0].message.content


def parse_webpage(url: str, strategy: str = "requests") -> str | None:
    """Retrieves and parses the content of a webpage using the specified strategy.

    Args:
        url (str): The complete URL of the webpage to parse, including protocol
            (e.g., 'https://example.com')
        strategy (str): The strategy to use for parsing. Must be one of:
            - 'browser': Uses a headless browser for JavaScript-rendered content
            - 'requests': Uses HTTP requests for static content
            - 'perplexity' : Uses Perplexity.ai to summarize webpage

    Returns:
        str: The parsed webpage content as a string

    Examples:
        >>> content = parse_webpage("https://example.com", "browser")
        >>> content = parse_webpage("https://example.com", "requests")
        >>> content = parse_webpage("https://example.com", "perplexity")

    """
    match strategy:
        case "browser":
            return parse_webpage_with_browser(url)
        case "requests":
            return parse_webpage_with_requests(url)
        case "perplexity":
            return parse_webpage_with_perplexity(url)
        case _:
            msg = f"Unsupported parsing strategy: {strategy}"
            raise ValueError(msg)
