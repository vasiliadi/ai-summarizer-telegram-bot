import requests
import trafilatura

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
