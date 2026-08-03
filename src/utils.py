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

    Returns:
        str | None: "youtube" or "castro" for https media URLs, "web" for any
            other http(s) URL, None when the URL has no usable scheme or host.

    """
    try:
        parts = urlsplit(url)
    except ValueError:
        # urlsplit rejects bracket-malformed authorities ("https://[") outright,
        # so treat them as unusable rather than letting the error reach the user.
        return None
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
    """Generate a UUID filename, with `ext` appended when given."""
    return f"{uuid4()!s}{ext}"


def compress_audio(input_file: str, output_file: str) -> None:
    """Compress an audio file to mono 16 kbps Opus, stripping any video stream.

    Requires ffmpeg on PATH.

    Raises:
        subprocess.CalledProcessError: If the ffmpeg command fails.

    """
    subprocess.run(
        [
            "ffmpeg",
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
    """Remove `file`, or every download when `all_downloads` is set.

    Both paths skip anything in `config.PROTECTED_FILES`, the startup snapshot of
    the working directory.
    """
    if all_downloads:
        for file_name in Path.cwd().iterdir():
            if file_name.is_file() and file_name.name not in PROTECTED_FILES:
                Path.unlink(file_name)
    elif file is not None:
        file_path = Path(file)
        if file_path.is_file() and file_path.name not in PROTECTED_FILES:
            Path.unlink(file_path)
