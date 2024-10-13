import os
from uuid import uuid4
import subprocess
from pathlib import Path

from config import PROTECTED_FILES


def generate_temprorary_name():
    return f"{str(uuid4())}.mp3"


def compress_audio(input_file, output_file):
    try:
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
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise Exception(f"{e}")


def clean_up():
    for file_name in os.listdir(os.getcwd()):
        file_path = Path(file_name)
        if file_path.is_file() and file_name not in PROTECTED_FILES:
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"Error deleting {file_path}: {e}")
