import random
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from config import CASTRO_HOST, PROTECTED_FILES, PROXIES, YT_HOSTS


def get_proxy() -> str:
    """Return a random proxy URL from PROXIES, or '' if none configured."""
    return random.choice(PROXIES) if PROXIES else ""  # noqa: S311


def classify_url(url: str) -> str | None:
    """Classify a URL by the pipeline that can summarize it.

    Single source of truth for URL routing: `handlers.handle_url` uses it to pick
    the summarize path, and `summary.summarize` uses it to pick the download path.
    Both must agree, so neither may re-derive the kind on its own.

    Args:
        url (str): The URL to classify.

    Returns:
        str | None: "youtube" or "castro" for https media URLs, "web" for any
            other http(s) URL, None when the URL has no usable scheme or host.

    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    if parts.scheme == "https" and host in YT_HOSTS:
        return "youtube"
    if (
        parts.scheme == "https"
        and host == CASTRO_HOST
        and parts.path.startswith("/episode/")
    ):
        return "castro"
    return "web"


def generate_temporary_name(ext: str = "") -> str:
    """Generate a unique temporary filename with an optional extension.

    Args:
        ext (str, optional): File extension to append to the generated name.

    Returns:
        str: A unique filename string consisting of a UUID with the optional extension.

    Example:
        >>> generate_temporary_name(".mp3")
        '123e4567-e89b-12d3-a456-426614174000.mp3'
        >>> generate_temporary_name()
        '123e4567-e89b-12d3-a456-426614174000'

    """
    return f"{uuid4()!s}{ext}"


def compress_audio(input_file: str, output_file: str) -> None:
    """Compress an audio file using FFmpeg with Opus codec.

    This function compresses the input file using FFmpeg with the following settings:
    - Single audio channel (mono)
    - Opus codec
    - 16kbps bitrate
    - Strips any video streams

    Args:
        input_file (str): Path to the input audio file to be compressed.
        output_file (str): Path where the compressed audio file will be saved.

    Raises:
        subprocess.CalledProcessError: If the ffmpeg command fails.

    Requirements:
        - ffmpeg must be installed and available in system PATH

    Example:
        >>> compress_audio("input.mp3", "output.ogg")

    """
    subprocess.run(
        [
            "ffmpeg",  # /usr/bin/ffmpeg
            "-y",
            "-i",
            input_file,
            "-vn",
            "-ac",
            "1",
            "-c:a",
            "libopus",
            "-b:a",
            "16k",
            output_file,
        ],
        check=True,
        capture_output=False,
        text=True,
    )


def clean_up(file: str | None = None, all_downloads: bool = False) -> None:
    """Remove temporary files from the current working directory.

    This function can either remove a single specified file or all non-protected files
    in the current working directory.

    Args:
        file (str | None, optional): Path to a specific file to remove.
        all_downloads (bool): If True, removes all non-protected files in the
                              current working directory.

    Example:
        >>> clean_up("temp.mp3")  # Remove a single file
        >>> clean_up(all_downloads=True)  # Remove all non-protected files

    """
    if all_downloads:
        for file_name in Path.cwd().iterdir():
            if file_name.is_file() and file_name.name not in PROTECTED_FILES:
                Path.unlink(file_name)
    elif file is not None:
        file_path = Path(file)
        if file_path.is_file() and file_path.name not in PROTECTED_FILES:
            Path.unlink(file_path)
