import trafilatura
from requests.utils import requote_uri
from selenium import webdriver
from selenium.webdriver.common.proxy import Proxy, ProxyType

from config import WEB_SCRAPE_PROXY


def parse_webpage(url: str) -> str:
    options = webdriver.ChromeOptions()
    options.accept_insecure_certs = False
    options.proxy = Proxy(
        {"proxyType": ProxyType.MANUAL, "httpProxy": WEB_SCRAPE_PROXY},
    )
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")

    with webdriver.Chrome(options=options) as driver:
        driver.get(requote_uri(url))
        html = driver.page_source

    return trafilatura.extract(html)
