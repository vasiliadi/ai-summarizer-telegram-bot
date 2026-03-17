from typing import TYPE_CHECKING, TypedDict
from urllib.parse import urlsplit

from config import bot
from download import download_tg
from services import get_file_with_retry, send_answer
from summary import summarize, summarize_webpage, summarize_with_document
from utils import clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    from telebot.types import Message

    from models import UsersOrm

FILE_TOO_BIG_BYTES = 20 * 1024 * 1024
YOUTUBE_HOSTS = {"www.youtube.com", "youtube.com"}
YOUTU_BE_HOST = "youtu.be"
CASTRO_HOST = "castro.fm"
SUPPORTED_WEB_SCHEMES = {"http", "https"}


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


def validate_media_file[TelegramMedia](
    message: "Message",
    media: TelegramMedia | None,
    missing_message: str,
) -> tuple[TelegramMedia, str] | None:
    """Validate Telegram media metadata and return the media object plus file id."""
    file_id = getattr(media, "file_id", None)
    file_size = getattr(media, "file_size", None)
    if media is None or file_id is None or file_size is None:
        bot.reply_to(message, missing_message)
        return None
    if file_size >= FILE_TOO_BIG_BYTES:
        bot.reply_to(message, "File is too big.")
        return None
    return media, file_id


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
    should_clean_compressed_file = True
    try:
        compress_audio(input_file=downloaded_file, output_file=compressed_file)
        should_clean_compressed_file = False
        answer = summarize(data=compressed_file, **get_summary_kwargs(user))
        send_answer(message, answer)
    finally:
        if should_clean_compressed_file:
            clean_up(file=compressed_file)
        clean_up(file=downloaded_file)


def classify_url(url: str) -> str | None:
    """Classify URL types supported by the bot."""
    parsed_url = urlsplit(url)
    host = parsed_url.hostname

    if parsed_url.scheme not in SUPPORTED_WEB_SCHEMES or host is None:
        return None
    if host in YOUTUBE_HOSTS or host == YOUTU_BE_HOST:
        return "media"
    if host == CASTRO_HOST and parsed_url.path.startswith("/episode/"):
        return "media"
    if parsed_url.netloc:
        return "webpage"
    return None


def normalize_media_url(url: str) -> str:
    """Normalize media URLs to the https scheme expected by summarize()."""
    if url.startswith("http://"):
        return f"https://{url.removeprefix('http://')}"
    return url


def handle_audio(message: "Message", user: "UsersOrm") -> None:
    """Handle audio file processing."""
    validated_media = validate_media_file(
        message,
        message.audio,
        "No audio file found.",
    )
    if validated_media is None:
        return
    _, file_id = validated_media

    answer = summarize_telegram_file(file_id, user)
    send_answer(message, answer)


def handle_video_note(message: "Message", user: "UsersOrm") -> None:
    """Handle video note file processing."""
    validated_media = validate_media_file(
        message,
        message.video_note,
        "No video note found.",
    )
    if validated_media is None:
        return
    _, file_id = validated_media

    handle_video_like_media(message, file_id, user)


def handle_voice(message: "Message", user: "UsersOrm") -> None:
    """Handle voice file processing."""
    validated_media = validate_media_file(
        message,
        message.voice,
        "No voice message found.",
    )
    if validated_media is None:
        return
    _, file_id = validated_media

    answer = summarize_telegram_file(file_id, user)
    send_answer(message, answer)


def handle_video(message: "Message", user: "UsersOrm") -> None:
    """Handle video file processing."""
    validated_media = validate_media_file(
        message,
        message.video,
        "No video file found.",
    )
    if validated_media is None:
        return
    _, file_id = validated_media

    handle_video_like_media(message, file_id, user)


def handle_document(message: "Message", user: "UsersOrm") -> None:
    """Handle document file processing."""
    validated_media = validate_media_file(
        message,
        message.document,
        "No document found.",
    )
    if validated_media is None:
        return
    document, file_id = validated_media

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
        normalized_url = normalize_media_url(url)
        answer = summarize(
            data=normalized_url,
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
