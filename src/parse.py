import time

import requests
import trafilatura
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.proxy import Proxy, ProxyType
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from config import WEB_SCRAPE_PROXY


@retry(
    wait=wait_fixed(10),
    retry=retry_if_exception_type(WebDriverException),
    reraise=True,
    stop=stop_after_attempt(3),
)  # type: ignore[call-overload]
def parse_webpage(url: str) -> str:
    options = webdriver.ChromeOptions()
    options.accept_insecure_certs = False
    options.proxy = Proxy(
        {"proxyType": ProxyType.MANUAL, "httpProxy": WEB_SCRAPE_PROXY},
    )
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")

    with webdriver.Chrome(options=options) as driver:
        driver.get(requests.utils.requote_uri(url))
        time.sleep(10)
        html = driver.page_source
        if "Verifying you are human. This may take a few seconds." in html:  # WIP
            raise WebDriverException("Could not pass bot verification")

    return trafilatura.extract(html)
