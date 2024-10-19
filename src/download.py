from pathlib import Path

import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL

from config import PROXY
from utils import generate_temprorary_name


def download_yt(url: str) -> str:
    temprorary_file_name = generate_temprorary_name()
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
        raise Exception("Problem with downloading the file")
    return temprorary_file_name


def download_castro(url: str) -> str:
    temprorary_file_name = generate_temprorary_name()
    url = BeautifulSoup(
        requests.get(requests.utils.requote_uri(url), verify=True, timeout=30).content,
        "html.parser",
    ).source.get("src")
    downloaded_file = requests.get(
        requests.utils.requote_uri(url),
        verify=True,
        timeout=120,
    )
    with Path(temprorary_file_name).open("wb") as f:
        f.write(downloaded_file.content)
    if not Path(temprorary_file_name).is_file():
        raise Exception("Problem with downloading the file")
    return temprorary_file_name
