import requests
import trafilatura
from seleniumbase import SB

from config import WEB_SCRAPE_PROXY, headers


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


def parse_webpage(url: str, strategy: str = "requests") -> str | None:
    """Retrieves and parses the content of a webpage using the specified strategy.

    Args:
        url (str): The complete URL of the webpage to parse, including protocol
            (e.g., 'https://example.com')
        strategy (str): The strategy to use for parsing. Must be one of:
            - 'browser': Uses a headless browser for JavaScript-rendered content
            - 'requests': Uses HTTP requests for static content

    Returns:
        str: The parsed webpage content as a string

    Examples:
        >>> content = parse_webpage("https://example.com", "browser")
        >>> content = parse_webpage("https://example.com", "requests")

    """
    match strategy:
        case "browser":
            return parse_webpage_with_browser(url)
        case "requests":
            return parse_webpage_with_requests(url)
        case _:
            msg = f"Unsupported parsing strategy: {strategy}"
            raise ValueError(msg)
