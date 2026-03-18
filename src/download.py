import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import requests
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import SSLError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from config import PROXY, TG_API_TOKEN, headers
from utils import generate_temporary_name

if TYPE_CHECKING:
    from telebot.types import File
    from tenacity import (
        _utils as tenacity_utils,
    )

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(DownloadError),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def download_yt(url: str) -> str:
    """Download audio from a YouTube video and convert it to MP3 format.

    Args:
        url (str): The YouTube video URL to download from.

    Returns:
        str: Path to the downloaded temporary MP3 file.

    Raises:
        RetryError: If the download fails after 2 retry attempts.
            Each retry attempt waits 10 seconds before retrying.

    Notes:
        - Downloads the lowest quality audio stream to minimize bandwidth
        - Uses FFmpeg to extract and convert the audio to MP3
        - The output file is given a temporary name with .mp3 extension

    """
    temporary_file_name = generate_temporary_name(ext=".mp3")
    ydl_opts = {
        "format": "worstaudio",
        "outtmpl": temporary_file_name.split(".", maxsplit=1)[0],
        "nocheckcertificate": False,
        "proxy": PROXY,
        "postprocessors": [
            {  # Extract audio using ffmpeg
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
def download_castro(url: str) -> str:
    """Download audio from a Castro podcast URL and save it as an MP3 file.

    Args:
        url (str): The Castro podcast URL to download from.

    Returns:
        str: Path to the downloaded temporary MP3 file.

    Raises:
        ValueError: If the audio source tag or URL is missing on the page.
        HTTPError: If the HTTP request fails or returns an error status code.
        Timeout: If the request exceeds the timeout limits
            (30s for parsing, 120s for download).
        RetryError: If SSL/connection failures persist after retries.

    Notes:
        - First parses the URL to extract the actual audio source URL
        - Downloads the audio file in chunks to manage memory usage
        - Uses a chunk size of 8192 bytes for streaming
        - The output file is given a temporary name with .mp3 extension

    """
    temporary_file_name = generate_temporary_name(ext=".mp3")
    logger.debug("Parsing URL...")
    soup = BeautifulSoup(
        requests.get(requests.utils.requote_uri(url), verify=True, timeout=30).content,
        "html.parser",
    )
    source_tag = soup.source
    if source_tag is None:
        msg = "Audio source tag not found in Castro page."
        raise ValueError(msg)
    audio_url = source_tag.get("src")
    if not audio_url:
        msg = "Audio URL not found in Castro page."
        raise ValueError(msg)
    logger.debug("URL parsed! Starting download...")
    with requests.get(
        requests.utils.requote_uri(audio_url),
        stream=True,
        headers=headers,
        verify=True,
        timeout=120,
    ) as r:
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            logger.error("%s: status code", r.status_code)
            raise
        with Path(temporary_file_name).open("wb") as f:
            f.writelines(r.iter_content(chunk_size=8192))
    logger.debug("File downloaded...")
    return temporary_file_name


def download_tg(file_id: "File", ext: str = "") -> str:
    """Download a file from Telegram and save it locally.

    Args:
        file_id (File): The Telegram File object containing file information.
        ext (str, optional): File extension for the output file.
                             Defaults to empty string.

    Returns:
        str: Path to the downloaded temporary file.

    Notes:
        - Uses the Telegram bot API to download the file
        - The output file is given a temporary name with the specified extension
        - File is written in binary mode

    """
    temporary_file_name = generate_temporary_name(ext=ext)
    if file_id.file_path is None:
        msg = "Telegram file path is missing."
        raise ValueError(msg)
    file_url = f"https://api.telegram.org/file/bot{TG_API_TOKEN}/{file_id.file_path}"
    with requests.get(
        file_url,
        stream=True,
        headers=headers,
        verify=True,
        timeout=120,
    ) as response:
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            logger.error("%s: status code", response.status_code)
            raise
        with Path(temporary_file_name).open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return temporary_file_name
