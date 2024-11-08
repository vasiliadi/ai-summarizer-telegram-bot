import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from telebot.util import smart_split
from telegramify_markdown import markdownify

from config import (
    DAILY_LIMIT_KEY,
    MINUTE_LIMIT_KEY,
    PROTECTED_FILES,
    bot,
    per_day_limit,
    per_minute_limit,
)
from translate import translate

if TYPE_CHECKING:
    from telebot.types import Message

    from models import UsersOrm


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


def clean_up() -> None:
    for file_name in os.listdir(Path.cwd()):
        file_path = Path(file_name)
        if file_path.is_file() and file_name not in PROTECTED_FILES:
            Path.unlink(file_path)


def send_answer(message: "Message", user: "UsersOrm", answer: str) -> None:
    answer = markdownify(answer)
    if len(answer) > 4000:  # 4096 limit # noqa: PLR2004
        chunks = smart_split(answer, 4000)
        for text in chunks:
            bot.reply_to(message, text, parse_mode="MarkdownV2")
            time.sleep(1)
    else:
        bot.reply_to(message, answer, parse_mode="MarkdownV2")

    if user.use_translator:
        translation = translate(answer, target_language=user.target_language)
        translation = markdownify(translation)
        if len(translation) > 4096:  # noqa: PLR2004
            chunks = smart_split(translation, 4096)
            for text in chunks:
                bot.reply_to(message, text, parse_mode="MarkdownV2")
                time.sleep(1)
        else:
            bot.reply_to(message, translation, parse_mode="MarkdownV2")


def check_quota(quantity: int = 1) -> bool:
    rpd = per_day_limit.check(DAILY_LIMIT_KEY, quantity=quantity)
    if rpd.limited:
        raise Exception("The daily limit for requests has been exceeded")  # pylint: disable=W0719
    rpm = per_minute_limit.check(MINUTE_LIMIT_KEY, quantity=quantity)
    if rpm.limited:
        time_to_reset = max(0, rpm.reset_after.total_seconds())
        time.sleep(time_to_reset)
    return True
