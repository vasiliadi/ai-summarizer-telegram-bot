import trafilatura

from config import WEB_SCRAPE_PROXY


def parse_webpage(url: str) -> str:
    trafilatura.downloads.PROXY_URL = WEB_SCRAPE_PROXY
    downloaded = trafilatura.fetch_url(url, no_ssl=True)
    if downloaded is None:
        raise ValueError("No content to proceed")
    content = trafilatura.extract(downloaded)
    if content is None:
        raise ValueError("No content to summarize")
    return content
