import os

import requests
from yt_dlp import YoutubeDL
from bs4 import BeautifulSoup

from utils import generate_temprorary_name
from config import PROXY


def download_yt(input: str) -> str:
    temprorary_file_name = generate_temprorary_name()
    ydl_opts = {
        "format": "worstaudio",
        "outtmpl": temprorary_file_name.split(".")[0],
        "proxy": PROXY,
        "postprocessors": [
            {  # Extract audio using ffmpeg
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download(input)
    if not os.path.isfile(temprorary_file_name):
        raise Exception("Problem with downloading the file")
    return temprorary_file_name


def download_castro(input: str) -> str:
    temprorary_file_name = generate_temprorary_name()
    input = BeautifulSoup(
        requests.get(requests.utils.requote_uri(input), verify=True).content,
        "html.parser",
    ).source.get("src")
    downloaded_file = requests.get(requests.utils.requote_uri(input), verify=True)
    with open(temprorary_file_name, "wb") as f:
        f.write(downloaded_file.content)
    if not os.path.isfile(temprorary_file_name):
        raise Exception("Problem with downloading the file")
    return temprorary_file_name
