from typing import TYPE_CHECKING, TypedDict
from urllib.parse import urlsplit

from config import CASTRO_HOST, TG_MAX_FILE_SIZE, YT_HOSTS, bot
from download import download_tg
from services import get_file_with_retry, send_answer
from summary import summarize, summarize_webpage, summarize_with_document
from utils import clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    from telebot.types import Audio, Document, File, Message, Video, VideoNote, Voice

    from models import UsersOrm

    _SizedMedia = Audio | Voice | Video | VideoNote | Document


class SummaryKwargs(TypedDict):
    """Shared summarize() kwargs sourced from a user record."""

    model: str
    prompt_key: str
    target_language: str
    user_id: int
    daily_limit: int


def _summary_kwargs(user: UsersOrm) -> SummaryKwargs:
    """Build the recurring summarize() kwargs sourced from a user record."""
    return {
        "model": user.summarizing_model,
        "prompt_key": user.prompt_key_for_summary,
        "target_language": user.target_language,
        "user_id": user.user_id,
        "daily_limit": user.daily_limit,
    }


def _fetch_media(
    message: Message,
    media: _SizedMedia | None,
    missing_msg: str,
) -> File | None:
    """Validate a Telegram media object and return its downloaded File handle.

    Replies to the user and returns None when the media is missing or exceeds
    the Telegram 20MB getFile cap.

    """
    # file_id is declared non-Optional by telebot's stubs but can be missing
    # at runtime for partially-deserialized messages; check defensively.
    file_id = getattr(media, "file_id", None)
    if media is None or media.file_size is None or file_id is None:
        bot.reply_to(message, missing_msg)
        return None
    if media.file_size >= TG_MAX_FILE_SIZE:
        bot.reply_to(message, "File is too big.")
        return None
    return get_file_with_retry(media.file_id)


def handle_audio(message: Message, user: UsersOrm) -> None:
    """Handle audio file processing."""
    data = _fetch_media(message, message.audio, "No audio file found.")
    if data is None:
        return
    answer = summarize(
        data=data,
        use_transcription=user.use_transcription,
        **_summary_kwargs(user),
    )
    send_answer(message, answer)


def handle_voice(message: Message, user: UsersOrm) -> None:
    """Handle voice file processing."""
    data = _fetch_media(message, message.voice, "No voice message found.")
    if data is None:
        return
    answer = summarize(
        data=data,
        use_transcription=user.use_transcription,
        **_summary_kwargs(user),
    )
    send_answer(message, answer)


def _handle_video_like(message: Message, user: UsersOrm, data: File) -> None:
    """Shared video / video-note pipeline: download, compress, summarize."""
    downloaded_file = download_tg(data, ext=".mp4")
    compressed_file = generate_temporary_name(ext=".ogg")
    try:
        compress_audio(input_file=downloaded_file, output_file=compressed_file)
        answer = summarize(
            data=compressed_file,
            use_transcription=user.use_transcription,
            **_summary_kwargs(user),
        )
        send_answer(message, answer)
    finally:
        clean_up(file=downloaded_file)


def handle_video_note(message: Message, user: UsersOrm) -> None:
    """Handle video note file processing."""
    data = _fetch_media(message, message.video_note, "No video note found.")
    if data is None:
        return
    _handle_video_like(message, user, data)


def handle_video(message: Message, user: UsersOrm) -> None:
    """Handle video file processing."""
    data = _fetch_media(message, message.video, "No video file found.")
    if data is None:
        return
    _handle_video_like(message, user, data)


def handle_document(message: Message, user: UsersOrm) -> None:
    """Handle document file processing."""
    document = message.document
    data = _fetch_media(message, document, "No document found.")
    if data is None or document is None:
        return
    answer = summarize_with_document(
        file=data,
        mime_type=document.mime_type or "application/octet-stream",
        **_summary_kwargs(user),
    )
    send_answer(message, answer)


def _classify_url(url: str) -> str | None:
    """Return 'media' for https YT/Castro URLs, 'web' for any http(s) URL, else None."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    host = parts.hostname
    if host is None:
        return None
    if parts.scheme == "https" and host in YT_HOSTS:
        return "media"
    if (
        parts.scheme == "https"
        and host == CASTRO_HOST
        and parts.path.startswith("/episode/")
    ):
        return "media"
    return "web"


def handle_url(message: Message, user: UsersOrm, url: str) -> None:
    """Handle URL processing."""
    kind = _classify_url(url)
    if kind == "media":
        answer = summarize(
            data=url,
            use_transcription=user.use_transcription,
            use_yt_transcription=user.use_yt_transcription,
            **_summary_kwargs(user),
        )
        send_answer(message, answer)
    elif kind == "web":
        answer = summarize_webpage(content=url, **_summary_kwargs(user))
        send_answer(message, answer)
    else:
        bot.send_message(message.chat.id, "No data to proceed.")
