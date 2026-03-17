import re
from typing import TYPE_CHECKING, TypedDict

from config import bot
from download import download_tg
from services import get_file_with_retry, send_answer
from summary import summarize, summarize_webpage, summarize_with_document
from utils import clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    from telebot.types import Message

    from models import UsersOrm

FILE_TOO_BIG_BYTES = 20 * 1024 * 1024
YOUTUBE_OR_CASTRO_PATTERN = re.compile(
    r"^https:\/\/(www\.youtube\.com\/*|youtu\.be\/|castro\.fm\/episode\/)[\S]*",
)
OTHER_URL_PATTERN = re.compile(
    r"^(?!https:\/\/(www\.youtube\.com\/|youtu\.be\/|castro\.fm\/episode\/)[\S]*)https?[\S]*",
)


class SummaryKwargs(TypedDict):
    """Typed keyword arguments shared across summarize() calls."""

    use_transcription: bool
    model: str
    prompt_key: str
    target_language: str


def get_summary_kwargs(user: "UsersOrm") -> SummaryKwargs:
    """Build the common summarization settings from user preferences."""
    return {
        "use_transcription": user.use_transcription,
        "model": user.summarizing_model,
        "prompt_key": user.prompt_key_for_summary,
        "target_language": user.target_language,
    }


def validate_media_file(
    message: "Message",
    media: object,
    missing_message: str,
) -> str | None:
    """Validate Telegram media metadata and return the file id if valid."""
    file_id = getattr(media, "file_id", None)
    file_size = getattr(media, "file_size", None)
    if media is None or file_id is None or file_size is None:
        bot.reply_to(message, missing_message)
        return None
    if file_size >= FILE_TOO_BIG_BYTES:
        bot.reply_to(message, "File is too big.")
        return None
    return file_id


def summarize_telegram_file(file_id: str, user: "UsersOrm") -> str:
    """Fetch a Telegram file and summarize it with the user's settings."""
    data = get_file_with_retry(file_id)
    return summarize(data=data, **get_summary_kwargs(user))


def handle_video_like_media(
    message: "Message",
    file_id: str,
    user: "UsersOrm",
) -> None:
    """Handle video-style Telegram media by downloading and compressing audio."""
    data = get_file_with_retry(file_id)
    downloaded_file = download_tg(data, ext=".mp4")
    compressed_file = generate_temporary_name(ext=".ogg")
    try:
        compress_audio(input_file=downloaded_file, output_file=compressed_file)
        answer = summarize(data=compressed_file, **get_summary_kwargs(user))
        send_answer(message, answer)
    finally:
        clean_up(file=downloaded_file)


def classify_url(url: str) -> str | None:
    """Classify URL types supported by the bot."""
    if YOUTUBE_OR_CASTRO_PATTERN.match(url):
        return "media"
    if OTHER_URL_PATTERN.match(url):
        return "webpage"
    return None


def handle_audio(message: "Message", user: "UsersOrm") -> None:
    """Handle audio file processing."""
    file_id = validate_media_file(message, message.audio, "No audio file found.")
    if file_id is None:
        return

    answer = summarize_telegram_file(file_id, user)
    send_answer(message, answer)


def handle_video_note(message: "Message", user: "UsersOrm") -> None:
    """Handle video note file processing."""
    file_id = validate_media_file(message, message.video_note, "No video note found.")
    if file_id is None:
        return

    handle_video_like_media(message, file_id, user)


def handle_voice(message: "Message", user: "UsersOrm") -> None:
    """Handle voice file processing."""
    file_id = validate_media_file(message, message.voice, "No voice message found.")
    if file_id is None:
        return

    answer = summarize_telegram_file(file_id, user)
    send_answer(message, answer)


def handle_video(message: "Message", user: "UsersOrm") -> None:
    """Handle video file processing."""
    file_id = validate_media_file(message, message.video, "No video file found.")
    if file_id is None:
        return

    handle_video_like_media(message, file_id, user)


def handle_document(message: "Message", user: "UsersOrm") -> None:
    """Handle document file processing."""
    document = message.document
    file_id = validate_media_file(message, document, "No document found.")
    if file_id is None:
        return
    if document is None:
        return

    data = get_file_with_retry(file_id)
    answer = summarize_with_document(
        file=data,
        model=user.summarizing_model,
        prompt_key=user.prompt_key_for_summary,
        target_language=user.target_language,
        mime_type=(document.mime_type or "application/octet-stream"),
    )
    send_answer(message, answer)


def handle_url(message: "Message", user: "UsersOrm", url: str) -> None:
    """Handle URL processing."""
    url_type = classify_url(url)
    if url_type == "media":
        answer = summarize(
            data=url,
            **get_summary_kwargs(user),
            use_yt_transcription=user.use_yt_transcription,
        )
        send_answer(message, answer)
    elif url_type == "webpage":
        answer = summarize_webpage(
            content=url,
            model=user.summarizing_model,
            prompt_key=user.prompt_key_for_summary,
            target_language=user.target_language,
        )
        send_answer(message, answer)
    else:
        bot.send_message(message.chat.id, "No data to proceed.")
