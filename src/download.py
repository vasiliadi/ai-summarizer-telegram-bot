import logging
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from loguru import logger
from yt_dlp import YoutubeDL

from config import LOG_LEVEL, LOG_LVL, PROXY
from utils import generate_temporary_name

logger.remove()
logger.add(sys.stderr, level=LOG_LVL)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def download_yt(url: str) -> str:
    temprorary_file_name = generate_temporary_name()
    ydl_opts = {
        "format": "worstaudio",
        "outtmpl": temprorary_file_name.split(".", maxsplit=1)[0],
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
    if not Path(temprorary_file_name).is_file():
        raise OSError("Problem with downloading the file")
    return temprorary_file_name


def download_castro(url: str) -> str:
    temprorary_file_name = generate_temporary_name()
    logger.debug("Parsing url...")
    url = BeautifulSoup(
        requests.get(requests.utils.requote_uri(url), verify=True, timeout=30).content,
        "html.parser",
    ).source.get("src")
    logger.debug("Url parsed! Starting download...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",  # noqa: E501
    }
    downloaded_file = requests.get(
        requests.utils.requote_uri(url),
        headers=headers,
        verify=True,
        timeout=120,
    )
    logger.debug("File downloaded...")
    with Path(temprorary_file_name).open("wb") as f:
        f.write(downloaded_file.content)
    if not Path(temprorary_file_name).is_file():
        raise OSError("Problem with downloading the file")
    return temprorary_file_name
