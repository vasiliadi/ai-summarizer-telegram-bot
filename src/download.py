from __future__ import annotations

import contextlib
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import ConnectionError as RequestsConnectionError
from curl_cffi.requests.exceptions import HTTPError, SSLError
from curl_cffi.requests.utils import requote_uri
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from utils import generate_temporary_name, get_proxy

if TYPE_CHECKING:
    from typing import Any

    from telebot.types import File
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class Downloader:
    """Downloads media from YouTube, Castro, and Telegram."""

    def __init__(self, tg_api_token: str) -> None:
        """Store the injected Telegram bot API token."""
        self._tg_api_token = tg_api_token

    @staticmethod
    def _choose_yt_audio_format(info: dict[str, Any]) -> str:
        """Return the most suitable audio format id for a YouTube video.

        Prefer audio-only formats when yt-dlp exposes them. Fall back to the
        combined format selector when the extractor does not provide a concrete
        audio-only id.

        """
        formats = info.get("formats") or []
        audio_only_formats = [
            fmt
            for fmt in formats
            if fmt.get("acodec") not in (None, "none") and fmt.get("vcodec") == "none"
        ]
        if not audio_only_formats:
            return "bestaudio/worst[acodec!=none]"

        def sort_key(fmt: dict[str, Any]) -> tuple[float, float]:
            abr = fmt.get("abr")
            tbr = fmt.get("tbr")
            return (
                float(abr) if abr is not None else math.inf,
                float(tbr) if tbr is not None else math.inf,
            )

        return str(min(audio_only_formats, key=sort_key)["format_id"])

    @staticmethod
    def _stream_to_file(
        url: str,
        dest: str,
        timeout: int = 120,
    ) -> None:
        """GET `url` and stream the body to `dest` in 8 KB chunks."""
        r = requests.get(
            url,
            stream=True,
            impersonate="chrome",
            verify=True,
            timeout=timeout,
        )
        try:
            try:
                r.raise_for_status()
            except HTTPError:
                logger.exception("%s: status code", r.status_code)
                raise
            try:
                with Path(dest).open("wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            except Exception:
                with contextlib.suppress(OSError):
                    Path(dest).unlink(missing_ok=True)
                raise
        finally:
            r.close()

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(10),
        retry=retry_if_exception_type(DownloadError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def download_yt(self, url: str) -> str:
        """Download a YouTube video's audio as MP3, returning the temp file path.

        Raises:
            RetryError: If the download fails after 2 retry attempts.

        """
        temporary_file_name = generate_temporary_name(ext=".mp3")
        output_stem = temporary_file_name.split(".", maxsplit=1)[0]
        proxy = get_proxy()
        with YoutubeDL({"proxy": proxy, "nocheckcertificate": False}) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            msg = "Failed to extract info from YouTube URL."
            raise DownloadError(msg)
        audio_format = self._choose_yt_audio_format(cast("dict[str, Any]", info))
        ydl_opts = {
            "format": audio_format,
            "outtmpl": output_stem,
            "nocheckcertificate": False,
            "proxy": proxy,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                },
            ],
        }
        with YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download(url)
            except DownloadError:
                # yt-dlp leaves partial fragment files (named after output_stem,
                # with no extension) on disk when a download or post-processing
                # step fails. Remove them so failed attempts don't accumulate.
                for leftover in Path.cwd().glob(f"{output_stem}*"):
                    with contextlib.suppress(OSError):
                        leftover.unlink(missing_ok=True)
                raise
        return temporary_file_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(10),
        retry=retry_if_exception_type((SSLError, RequestsConnectionError)),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def download_castro(self, url: str) -> str:
        """Scrape a Castro episode page for its audio URL and stream it to a file.

        The bytes are stored as fetched, with no transcoding; the `.mp3` temp name
        reflects the common case, not a verified container.

        Raises:
            ValueError: If the audio source tag or URL is missing on the page.
            TypeError: If the page's source `src` is not a string.
            HTTPError: If the HTTP request fails.
            RetryError: If SSL/connection failures persist after retries.

        """
        temporary_file_name = generate_temporary_name(ext=".mp3")
        logger.debug("Parsing URL...")
        response = requests.get(
            requote_uri(url),
            impersonate="chrome",
            verify=True,
            timeout=30,
        )
        try:
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
        finally:
            response.close()
        source_tag = soup.source
        if source_tag is None:
            msg = "Audio source tag not found in Castro page."
            raise ValueError(msg)
        audio_url = source_tag.get("src")
        if not audio_url:
            msg = "Audio URL not found in Castro page."
            raise ValueError(msg)
        if not isinstance(audio_url, str):
            msg = "Audio URL is not a string."
            raise TypeError(msg)
        logger.debug("URL parsed! Starting download...")
        self._stream_to_file(requote_uri(audio_url), temporary_file_name)
        logger.debug("File downloaded...")
        return temporary_file_name

    def download_tg(self, file_id: File, ext: str = "") -> str:
        """Fetch a Telegram file, returning the local temp path.

        Raises:
            ValueError: If the Telegram file path is missing.

        """
        temporary_file_name = generate_temporary_name(ext=ext)
        if file_id.file_path is None:
            msg = "Telegram file path is missing."
            raise ValueError(msg)
        file_url = (
            f"https://api.telegram.org/file/bot{self._tg_api_token}/{file_id.file_path}"
        )
        self._stream_to_file(file_url, temporary_file_name)
        return temporary_file_name
