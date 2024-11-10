import os
import subprocess
from pathlib import Path
from uuid import uuid4

from config import PROTECTED_FILES


def generate_temporary_name() -> str:
    return f"{uuid4()!s}.mp3"


def compress_audio(input_file: str, output_file: str) -> None:
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
        capture_output=True,
        text=True,
    )


def clean_up(file: str | None = None, all_downloads: bool = False) -> None:
    if all_downloads:
        for file_name in os.listdir(Path.cwd()):
            file_path = Path(file_name)
            if file_path.is_file() and file_name not in PROTECTED_FILES:
                Path.unlink(file_path)
    elif file is not None:
        file_path = Path(file)
        if file_path.is_file() and file not in PROTECTED_FILES:
            Path.unlink(file_path)
