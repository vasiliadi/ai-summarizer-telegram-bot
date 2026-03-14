import re
from typing import TYPE_CHECKING

from config import bot
from download import download_tg
from services import send_answer
from summary import summarize, summarize_webpage, summarize_with_document
from utils import clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    from telebot.types import Message

    from models import UsersOrm


def handle_audio(message: "Message", user: "UsersOrm") -> None:
    """Handle audio file processing."""
    audio = message.audio
    if audio is None or audio.file_size is None or audio.file_id is None:
        bot.reply_to(message, "No audio file found.")
        return
    if audio.file_size >= 20971520:  # 20MB  # noqa: PLR2004
        bot.reply_to(message, "File is too big.")
        return

    data = bot.get_file(
        audio.file_id,
    )  # Max 20MB https://core.telegram.org/bots/api#getfile
    answer = summarize(
        data=data,
        use_transcription=user.use_transcription,
        model=user.summarizing_model,
        prompt_key=user.prompt_key_for_summary,
        target_language=user.target_language,
    )
    send_answer(message, answer)


def handle_video_note(message: "Message", user: "UsersOrm") -> None:
    """Handle video note file processing."""
    video_note = message.video_note
    if video_note is None or video_note.file_size is None or video_note.file_id is None:
        bot.reply_to(message, "No video note found.")
        return
    if video_note.file_size >= 20971520:  # 20MB  # noqa: PLR2004
        bot.reply_to(message, "File is too big.")
        return

    data = bot.get_file(
        video_note.file_id,
    )  # Max 20MB https://core.telegram.org/bots/api#getfile
    downloaded_file = download_tg(data, ext=".mp4")
    compressed_file = generate_temporary_name(ext=".ogg")
    try:
        compress_audio(input_file=downloaded_file, output_file=compressed_file)
        answer = summarize(
            data=compressed_file,
            use_transcription=user.use_transcription,
            model=user.summarizing_model,
            prompt_key=user.prompt_key_for_summary,
            target_language=user.target_language,
        )
        send_answer(message, answer)
    finally:
        clean_up(file=downloaded_file)


def handle_voice(message: "Message", user: "UsersOrm") -> None:
    """Handle voice file processing."""
    voice = message.voice
    if voice is None or voice.file_size is None or voice.file_id is None:
        bot.reply_to(message, "No voice message found.")
        return
    if voice.file_size >= 20971520:  # 20MB  # noqa: PLR2004
        bot.reply_to(message, "File is too big.")
        return

    data = bot.get_file(
        voice.file_id,
    )  # Max 20MB https://core.telegram.org/bots/api#getfile
    answer = summarize(
        data=data,
        use_transcription=user.use_transcription,
        model=user.summarizing_model,
        prompt_key=user.prompt_key_for_summary,
        target_language=user.target_language,
    )
    send_answer(message, answer)


def handle_video(message: "Message", user: "UsersOrm") -> None:
    """Handle video file processing."""
    video = message.video
    if video is None or video.file_size is None or video.file_id is None:
        bot.reply_to(message, "No video file found.")
        return
    if video.file_size >= 20971520:  # 20MB  # noqa: PLR2004
        bot.reply_to(message, "File is too big.")
        return

    data = bot.get_file(
        video.file_id,
    )  # Max 20MB https://core.telegram.org/bots/api#getfile
    downloaded_file = download_tg(data, ext=".mp4")
    compressed_file = generate_temporary_name(ext=".ogg")
    try:
        compress_audio(input_file=downloaded_file, output_file=compressed_file)
        answer = summarize(
            data=compressed_file,
            use_transcription=user.use_transcription,
            model=user.summarizing_model,
            prompt_key=user.prompt_key_for_summary,
            target_language=user.target_language,
        )
        send_answer(message, answer)
    finally:
        clean_up(file=downloaded_file)


def handle_document(message: "Message", user: "UsersOrm") -> None:
    """Handle document file processing."""
    document = message.document
    if document is None or document.file_size is None or document.file_id is None:
        bot.reply_to(message, "No document found.")
        return
    if document.file_size >= 20971520:  # 20MB  # noqa: PLR2004
        bot.reply_to(message, "File is too big.")
        return

    data = bot.get_file(
        document.file_id,
    )  # Max 20MB https://core.telegram.org/bots/api#getfile
    answer = summarize_with_document(
        file=data,
        model=user.summarizing_model,
        prompt_key=user.prompt_key_for_summary,
        target_language=user.target_language,
        mime_type=document.mime_type or "application/octet-stream",
    )
    send_answer(message, answer)


def handle_url(message: "Message", user: "UsersOrm", url: str) -> None:
    """Handle URL processing."""
    # YouTube/Castro pattern
    yt_castro_pattern = (
        r"^https:\/\/(www\.youtube\.com\/*|youtu\.be\/|castro\.fm\/episode\/)[\S]*"
    )
    # Other URLs pattern
    other_url_pattern = r"^(?!https:\/\/(www\.youtube\.com\/|youtu\.be\/|castro\.fm\/episode\/)[\S]*)https?[\S]*"  # noqa: E501

    if re.match(yt_castro_pattern, url):
        answer = summarize(
            data=url,
            use_transcription=user.use_transcription,
            model=user.summarizing_model,
            prompt_key=user.prompt_key_for_summary,
            target_language=user.target_language,
            use_yt_transcription=user.use_yt_transcription,
        )
        send_answer(message, answer)
    elif re.match(other_url_pattern, url):
        answer = summarize_webpage(
            content=url,
            model=user.summarizing_model,
            prompt_key=user.prompt_key_for_summary,
            target_language=user.target_language,
        )
        send_answer(message, answer)
    else:
        bot.send_message(message.chat.id, "No data to proceed.")
