import logging
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from config import NUMERIC_LOG_LEVEL, PROXY, bot, headers
from utils import generate_temporary_name

if TYPE_CHECKING:
    from telebot.types import File

logging.basicConfig(
    level=NUMERIC_LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@retry(
    wait=wait_fixed(10),
    retry=retry_if_exception_type(DownloadError),
    reraise=True,
    stop=stop_after_attempt(2),
)  # type: ignore[call-overload]
def download_yt(url: str) -> str:
    temprorary_file_name = generate_temporary_name()
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


def download_castro(url: str) -> str:
    temprorary_file_name = generate_temporary_name()
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
            logger.error("%s status code", r.status_code)
            raise
        with Path(temprorary_file_name).open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    logger.debug("File downloaded...")
    return temprorary_file_name


def download_tg(file_id: "File") -> str:
    temprorary_file_name = generate_temporary_name()
    downloaded_file = bot.download_file(file_id.file_path)
    with Path(temprorary_file_name).open("wb") as f:
        f.write(downloaded_file)
    return temprorary_file_name
