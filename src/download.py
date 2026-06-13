from __future__ import annotations

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

from config import TG_API_TOKEN
from utils import generate_temporary_name, get_proxy

if TYPE_CHECKING:
    from typing import Any

    from telebot.types import File
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


def choose_yt_audio_format(info: dict[str, Any]) -> str:
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


class Downloader:
    """Downloads media from YouTube, Castro, and Telegram."""

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
            with Path(dest).open("wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
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
        """Download audio from a YouTube video and convert it to MP3 format.

        Args:
            url (str): The YouTube video URL to download from.

        Returns:
            str: Path to the downloaded temporary MP3 file.

        Raises:
            RetryError: If the download fails after 2 retry attempts.

        """
        temporary_file_name = generate_temporary_name(ext=".mp3")
        proxy = get_proxy()
        with YoutubeDL({"proxy": proxy, "nocheckcertificate": False}) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            msg = "Failed to extract info from YouTube URL."
            raise DownloadError(msg)
        audio_format = choose_yt_audio_format(cast("dict[str, Any]", info))
        ydl_opts = {
            "format": audio_format,
            "outtmpl": temporary_file_name.split(".", maxsplit=1)[0],
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
            ydl.download(url)
        return temporary_file_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(10),
        retry=retry_if_exception_type((SSLError, RequestsConnectionError)),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def download_castro(self, url: str) -> str:
        """Download audio from a Castro podcast URL and save it as an MP3 file.

        Args:
            url (str): The Castro podcast URL to download from.

        Returns:
            str: Path to the downloaded temporary MP3 file.

        Raises:
            ValueError: If the audio source tag or URL is missing on the page.
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
        """Download a file from Telegram and save it locally.

        Args:
            file_id (File): The Telegram File object containing file information.
            ext (str, optional): File extension for the output file.

        Returns:
            str: Path to the downloaded temporary file.

        Raises:
            ValueError: If the Telegram file path is missing.

        """
        temporary_file_name = generate_temporary_name(ext=ext)
        if file_id.file_path is None:
            msg = "Telegram file path is missing."
            raise ValueError(msg)
        file_url = (
            f"https://api.telegram.org/file/bot{TG_API_TOKEN}/{file_id.file_path}"
        )
        self._stream_to_file(file_url, temporary_file_name)
        return temporary_file_name


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

downloader = Downloader()


# ---------------------------------------------------------------------------
# Module-level aliases — preserve the existing public API
# ---------------------------------------------------------------------------

download_yt = downloader.download_yt
download_castro = downloader.download_castro
download_tg = downloader.download_tg
