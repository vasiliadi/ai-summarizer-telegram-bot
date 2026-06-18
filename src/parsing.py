from __future__ import annotations

import ipaddress
import logging
import socket
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

from curl_cffi import requests
from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import exa_client, tavily_client
from domain import PrefixedText
from exceptions import WebParseError
from utils import get_proxy

if TYPE_CHECKING:
    from exa_py import Exa
    from tavily import TavilyClient
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class ParserBackend(ABC):
    """Abstract base for URL content-extraction backends."""

    name: str
    prefix: str

    @abstractmethod
    def parse(self, url: str) -> str:
        """Extract main textual content from a URL."""


class ExaBackend(ParserBackend):
    """Exa.ai URL extraction backend."""

    name = "Exa"
    prefix = "🌐"

    def __init__(self, client: Exa) -> None:
        """Store the injected Exa client."""
        self._client = client

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(WebParseError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=True,
    )
    def parse(self, url: str) -> str:
        """Extract main textual content from a URL using Exa.ai.

        Raises:
            WebParseError: If Exa returns no results or empty content. Retried
                once (2 total attempts) before re-raising.

        """
        response = self._client.get_contents(
            urls=[url],
            text={"max_characters": 20000, "include_html_tags": True},
        )
        results = response.results or []
        if not results:
            msg = f"Exa could not extract content from {url}"
            logger.warning(msg)
            raise WebParseError(msg)
        content = (results[0].text or "").strip()
        if not content:
            msg = f"Exa returned empty content for {url}"
            logger.warning(msg)
            raise WebParseError(msg)
        return content


class TavilyBackend(ParserBackend):
    """Tavily URL extraction backend."""

    name = "Tavily"
    prefix = "🕸️"

    def __init__(self, client: TavilyClient) -> None:
        """Store the injected Tavily client."""
        self._client = client

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(TavilyTimeoutError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def parse(self, url: str) -> str:
        """Extract main textual content from a URL using Tavily.

        Raises:
            WebParseError: If Tavily returns no results or empty content.
            RetryError: If Tavily keeps timing out after all retry attempts.

        """
        response = self._client.extract(urls=[url], format="markdown")
        results = response.get("results") or []
        if not results:
            failed = response.get("failed_results") or []
            msg = f"Tavily could not extract content from {url}: {failed}"
            logger.warning(msg)
            raise WebParseError(msg)
        content = (results[0].get("raw_content") or "").strip()
        if not content:
            msg = f"Tavily returned empty content for {url}"
            logger.warning(msg)
            raise WebParseError(msg)
        return content


class UrlResolver:
    """Resolves a URL to its final post-redirect destination, guarding against SSRF."""

    def __init__(self, timeout: int = 10) -> None:
        """Store the per-request timeout in seconds."""
        self._timeout = timeout

    def resolve(self, url: str) -> str:
        """Return the final URL after following redirects; the original on failure.

        Best-effort pre-check: issues a streamed GET (browser-impersonated,
        routed through the proxy pool, body never read) and follows 301/302
        redirects so the parser receives the real destination. Any failure
        (timeout, network error) is logged and the original URL is returned
        unchanged. Non-public hosts (private, loopback, link-local) are
        rejected before the request and after redirect to prevent SSRF.
        """
        if not self._is_public(url):
            logger.warning("Blocked non-public URL: %s", url)
            return url
        try:
            response = requests.get(
                url,
                stream=True,
                allow_redirects=True,
                impersonate="chrome",
                verify=True,
                timeout=self._timeout,
                proxy=get_proxy() or None,
            )
            try:
                resolved = response.url or url
            finally:
                response.close()
        except Exception:  # best-effort: never let resolution break parsing
            logger.warning("Could not resolve redirects for %s", url, exc_info=True)
            return url
        if not self._is_public(resolved):
            logger.warning(
                "Blocked redirect to non-public host: %s -> %s",
                url,
                resolved,
            )
            return url
        if resolved != url:
            logger.info("Resolved %s -> %s", url, resolved)
        return resolved

    @staticmethod
    def _is_public(url: str) -> bool:
        """Return True only if every resolved IP for the hostname is globally routable.

        Rejects localhost, private RFC1918 ranges, link-local (169.254.x.x / ::1),
        and any other non-global address to block SSRF.
        """
        hostname = (urlsplit(url).hostname or "").rstrip(".")
        if not hostname:
            return False
        try:
            results = socket.getaddrinfo(hostname, None)
        except OSError:
            return False
        return bool(results) and all(
            ipaddress.ip_address(addr[4][0]).is_global for addr in results
        )


class WebParser:
    """Orchestrate redirect resolution, then primary→fallback content extraction."""

    def __init__(
        self,
        primary: ParserBackend,
        fallback: ParserBackend,
        resolver: UrlResolver,
    ) -> None:
        """Store the primary/fallback backends and the URL resolver."""
        self._primary = primary
        self._fallback = fallback
        self._resolver = resolver

    def parse(self, url: str) -> PrefixedText:
        """Resolve redirects, then extract main textual content from the URL.

        Resolves the final destination (best-effort, SSRF-guarded), parses with
        the primary backend first, and falls back to the secondary on failure.

        Returns:
            PrefixedText: The extracted content and source display prefix.

        Raises:
            WebParseError: If both backends fail.
            Exception: Any non-retryable primary error propagates immediately
                without attempting the fallback.

        """
        url = self._resolver.resolve(url)
        try:
            return PrefixedText(
                text=self._primary.parse(url),
                prefix=self._primary.prefix,
            )
        except WebParseError as primary_error:
            logger.warning(
                "%s parsing backend failed, falling back to %s: %s",
                self._primary.name,
                self._fallback.name,
                primary_error,
            )
            try:
                return PrefixedText(
                    text=self._fallback.parse(url),
                    prefix=self._fallback.prefix,
                )
            except (WebParseError, RetryError) as fallback_error:
                logger.warning(
                    "%s fallback backend also failed: %s",
                    self._fallback.name,
                    fallback_error,
                )
                msg = "Both parsing backends failed"
                raise WebParseError(msg) from fallback_error


web_parser = WebParser(
    ExaBackend(exa_client),
    TavilyBackend(tavily_client),
    UrlResolver(),
)


def parse_url(url: str) -> PrefixedText:
    """Extract main textual content from a URL via the default WebParser."""
    return web_parser.parse(url)
