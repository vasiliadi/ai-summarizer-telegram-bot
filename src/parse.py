import trafilatura
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random
from urllib3.exceptions import MaxRetryError

from config import WEB_SCRAPE_PROXY


@retry(
    wait=wait_random(min=10, max=20),
    retry=retry_if_exception_type(MaxRetryError),
    reraise=True,
    stop=stop_after_attempt(3),
)  # type: ignore[call-overload]
def parse_webpage(url: str) -> str:
    trafilatura.downloads.PROXY_URL = WEB_SCRAPE_PROXY
    downloaded = trafilatura.fetch_url(url, no_ssl=True)
    if downloaded is None:
        raise ValueError("No content to proceed")
    return trafilatura.extract(downloaded)
