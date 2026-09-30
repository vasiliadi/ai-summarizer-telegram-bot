from __future__ import annotations

import ipaddress
import logging
import socket
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, cast
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

from config import (
    BLOCK_DETECTOR_MODEL_ID,
    OPENROUTER_APP_TITLE,
    OPENROUTER_APP_URL,
    OPENROUTER_DECISIONS_URL,
)
from domain import PrefixedText
from exceptions import WebParseError
from utils import get_proxy

if TYPE_CHECKING:
    from exa_py import Exa
    from tavily import TavilyClient
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class BlockedPageDetector:
    """Asks JEV whether an extraction is a block page rather than the content.

    Exa and Tavily are sometimes refused by the site and return what it shows
    instead — a region block, a bot check, an access-denied or login page — as
    ordinary non-empty text. JEV answers one yes/no question over the text with
    a probability; calibrated on 2026-09-30, block pages scored 0.83-0.99 and
    real pages (including an article *about* regional blocking) 0.01-0.03.
    """

    _QUESTION: ClassVar[str] = (
        "Is this page a block, access-denied or error page instead of the "
        "requested content?"
    )
    _CRITERIA: ClassVar[dict[str, str]] = {
        "true": (
            "The text is what a site shows instead of its content: a region or "
            "access block, a bot check or CAPTCHA, a login or paywall, a "
            "JavaScript-required notice, or an error page."
        ),
        "false": (
            "The text carries the page's actual content, such as an article, "
            "documentation, a post or a discussion, even if it mentions blocking "
            "or errors."
        ),
    }

    def __init__(
        self,
        api_key: str,
        model: str = BLOCK_DETECTOR_MODEL_ID,
        threshold: float = 0.5,
        timeout: int = 30,
    ) -> None:
        """Store the OpenRouter key, the JEV model id, and the block threshold."""
        self._api_key = api_key
        self._model = model
        self._threshold = threshold
        self._timeout = timeout

    def is_blocked(self, content: str, url: str) -> bool:
        """Return True when JEV judges the extraction to be a block page.

        Fails open: any detector error is logged and treated as not blocked, so
        a JEV outage can never break web parsing.
        """
        body = {
            "model": self._model,
            "state": content,
            "questions": {
                "blocked": {
                    "type": "noul",
                    "instructions": self._QUESTION,
                    "criteria": self._CRITERIA,
                },
            },
        }
        try:
            response = requests.post(
                OPENROUTER_DECISIONS_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "HTTP-Referer": OPENROUTER_APP_URL,
                    "X-Title": OPENROUTER_APP_TITLE,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            probability = float(response.json()["answers"]["blocked"]["noul"])
        except Exception:  # best-effort: never let detection break parsing
            logger.warning("Block-page check failed for %s", url, exc_info=True)
            return False
        if probability >= self._threshold:
            logger.warning("JEV flagged %s as a block page (p=%.2f)", url, probability)
            return True
        return False


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

    def __init__(
        self,
        client: Exa,
        detector: BlockedPageDetector | None = None,
    ) -> None:
        """Store the injected Exa client and the optional block-page detector."""
        self._client = client
        self._detector = detector

    def parse(self, url: str) -> str:
        """Extract main textual content from a URL using Exa.ai.

        A block page is rejected without re-running Exa: the site refused Exa,
        and asking again 5 s later would only fetch the same page.

        Raises:
            WebParseError: If Exa returns no results or empty content (retried
                once, 2 total attempts, before re-raising), or if the detector
                judges the extraction a block page.

        """
        content = self._extract(url)
        if self._detector is not None and self._detector.is_blocked(content, url):
            msg = f"Exa returned a block page for {url}"
            logger.warning(msg)
            raise WebParseError(msg)
        return content

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(WebParseError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=True,
    )
    def _extract(self, url: str) -> str:
        response = self._client.get_contents(
            urls=[url],
            text={"max_characters": 20000, "include_html_tags": True},
            max_age_hours=0,
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
        except OSError, UnicodeError:
            # UnicodeError: getaddrinfo rejects invalid/over-long IDNA labels.
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
