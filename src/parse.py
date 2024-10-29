import requests
import trafilatura

from config import WEB_SCRAPE_PROXY


def parse_webpage(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",  # noqa: E501
    }  # https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
    downloaded = requests.get(
        requests.utils.requote_uri(url),
        verify=False,  # noqa: S501
        headers=headers,
        timeout=30,
        proxies={"https": WEB_SCRAPE_PROXY},
    )
    downloaded.raise_for_status()
    return trafilatura.extract(downloaded.text)
