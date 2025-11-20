import re
from typing import TYPE_CHECKING

from config import bot
from services import send_answer
from summary import summarize, summarize_webpage, summarize_with_document

if TYPE_CHECKING:
    from telebot.types import Message

    from models import UsersOrm


def handle_audio(message: "Message", user: "UsersOrm") -> None:
    """Handle audio file processing."""
    if message.audio.file_size >= 20971520:  # 20MB  # noqa: PLR2004
        bot.reply_to(message, "File is too big.")
        return

    data = bot.get_file(
        message.audio.file_id,
    )  # Max 20MB https://core.telegram.org/bots/api#getfile
    answer = summarize(
        data=data,
        use_transcription=user.use_transcription,
        model=user.summarizing_model,
        prompt_key=user.prompt_key_for_summary,
        target_language=user.target_language,
    )
    send_answer(message, answer)


def handle_document(message: "Message", user: "UsersOrm") -> None:
    """Handle document file processing."""
    if message.document.file_size >= 20971520:  # 20MB  # noqa: PLR2004
        bot.reply_to(message, "File is too big.")
        return

    data = bot.get_file(
        message.document.file_id,
    )  # Max 20MB https://core.telegram.org/bots/api#getfile
    answer = summarize_with_document(
        file=data,
        model=user.summarizing_model,
        prompt_key=user.prompt_key_for_summary,
        target_language=user.target_language,
        mime_type=message.document.mime_type,
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
