import logging
from pathlib import Path
from typing import TYPE_CHECKING

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

from config import PROXY, bot, headers
from utils import generate_temporary_name

if TYPE_CHECKING:
    from telebot.types import File

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(DownloadError),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def download_yt(url: str) -> str:
    """Download audio from a YouTube video and convert it to MP3 format.

    Args:
        url (str): The YouTube video URL to download from.

    Returns:
        str: Path to the downloaded temporary MP3 file.

    Raises:
        DownloadError: If the download fails after 2 retry attempts.
            Each retry attempt waits 10 seconds before retrying.

    Notes:
        - Downloads the lowest quality audio stream to minimize bandwidth
        - Uses FFmpeg to extract and convert the audio to MP3
        - The output file is given a temporary name with .mp3 extension

    """
    temprorary_file_name = generate_temporary_name(ext=".mp3")
    ydl_opts = {
        "format": "worstaudio",
        "outtmpl": temprorary_file_name.split(".", maxsplit=1)[0],
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
    return temprorary_file_name


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    retry=retry_if_exception_type((SSLError, RequestsConnectionError)),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def download_castro(url: str) -> str:
    """Download audio from a Castro podcast URL and save it as an MP3 file.

    Args:
        url (str): The Castro podcast URL to download from.

    Returns:
        str: Path to the downloaded temporary MP3 file.

    Raises:
        HTTPError: If the HTTP request fails or returns an error status code.
        Timeout: If the request exceeds the timeout limits
                 (30s for parsing, 120s for download).

    Notes:
        - First parses the URL to extract the actual audio source URL
        - Downloads the audio file in chunks to manage memory usage
        - Uses a chunk size of 8192 bytes for streaming
        - The output file is given a temporary name with .mp3 extension

    """
    temprorary_file_name = generate_temporary_name(ext=".mp3")
    logger.debug("Parsing url...")
    url = BeautifulSoup(
        requests.get(requests.utils.requote_uri(url), verify=True, timeout=30).content,
        "html.parser",
    ).source.get("src")
    logger.debug("Url parsed! Starting download...")
    with requests.get(
        requests.utils.requote_uri(url),
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
        with Path(temprorary_file_name).open("wb") as f:
            f.writelines(r.iter_content(chunk_size=8192))
    logger.debug("File downloaded...")
    return temprorary_file_name


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
    temprorary_file_name = generate_temporary_name(ext=ext)
    downloaded_file = bot.download_file(file_id.file_path)
    with Path(temprorary_file_name).open("wb") as f:
        f.write(downloaded_file)
    return temprorary_file_name
