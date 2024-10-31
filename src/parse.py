import requests
import trafilatura
from selenium import webdriver

from config import WEB_SCRAPE_PROXY


def parse_webpage_with_request(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",  # noqa: E501
    }  # https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
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


def parse_webpage_with_browser(url: str) -> str:
    options = webdriver.ChromeOptions()
    options.accept_insecure_certs = False
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument(f"--proxy-server={WEB_SCRAPE_PROXY}")

    with webdriver.Chrome(options=options) as driver:
        driver.implicitly_wait(10)
        driver.get(requests.utils.requote_uri(url))
        html = driver.page_source

    return trafilatura.extract(html)


def parse_webpage(url: str, strategy: str = "request") -> str:
    """
    Retrieves and parses the content of a webpage using the specified strategy.

    Args:
        url (str): The complete URL of the webpage to parse, including protocol
            (e.g., 'https://example.com')
        strategy (str): The strategy to use for parsing. Must be one of:
            - 'browser': Uses a headless browser for JavaScript-rendered content
            - 'request': Uses HTTP requests for static content

    Returns:
        str: The parsed webpage content as a string

    Examples:
        >>> content = parse_webpage('https://example.com', 'request')
        >>> content = parse_webpage('https://example.com', 'browser')
    """
    match strategy:
        case "browser":
            return parse_webpage_with_browser(url)
        case "request":
            return parse_webpage_with_request(url)
        case _:
            raise ValueError(f"Unsupported parsing strategy: {strategy}")
