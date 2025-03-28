import subprocess
from pathlib import Path
from uuid import uuid4

from config import PROTECTED_FILES


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
        subprocess.CalledProcessError: If ffmpeg command fails

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
