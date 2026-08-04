from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from config import TG_MAX_FILE_SIZE
from domain import format_prefixed_summary
from utils import classify_url, clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    import telebot
    from telebot.types import Audio, Document, File, Message, Video, VideoNote, Voice

    from download import Downloader
    from models import UsersOrm
    from parsing import WebParser
    from services import Messenger, QuotaManager
    from summary import Summarizer

    _SizedMedia = Audio | Voice | Video | VideoNote | Document


class SummaryKwargs(TypedDict):
    """Shared summarize() kwargs sourced from a user record."""

    model: str
    prompt_key: str
    target_language: str
    user_id: int
    daily_limit: int
    thinking_level: str


class MessageHandlers:
    """Per-content-type Telegram message handlers."""

    def __init__(
        self,
        bot: telebot.TeleBot,
        messenger: Messenger,
        summarizer: Summarizer,
        web_parser: WebParser,
        quota_manager: QuotaManager,
        downloader: Downloader,
    ) -> None:
        """Store the injected collaborators used to handle Telegram messages."""
        self._bot = bot
        self._messenger = messenger
        self._summarizer = summarizer
        self._web_parser = web_parser
        self._quota_manager = quota_manager
        self._downloader = downloader

    @staticmethod
    def _summary_kwargs(user: UsersOrm) -> SummaryKwargs:
        """Build the recurring summarize() kwargs sourced from a user record."""
        return {
            "model": user.summarizing_model,
            "prompt_key": user.prompt_key_for_summary,
            "target_language": user.target_language,
            "user_id": user.user_id,
            "daily_limit": user.daily_limit,
            "thinking_level": user.thinking_level,
        }

    def _fetch_media(
        self,
        message: Message,
        media: _SizedMedia | None,
        missing_msg: str,
    ) -> File | None:
        """Validate a Telegram media object and return its downloaded File handle.

        Replies to the user and returns None when the media is missing or exceeds
        the Telegram 20MB getFile cap.

        """
        if media is None or media.file_size is None:
            self._bot.reply_to(message, missing_msg)
            return None
        if media.file_size > TG_MAX_FILE_SIZE:
            self._bot.reply_to(message, "File is too big.")
            return None
        return self._messenger.get_file_with_retry(media.file_id)

    def handle_audio(self, message: Message, user: UsersOrm) -> None:
        """Handle audio file processing."""
        data = self._fetch_media(message, message.audio, "No audio file found.")
        if data is None:
            return
        answer = self._summarizer.summarize(
            data=data,
            **self._summary_kwargs(user),
        )
        self._messenger.send_answer(message, answer)

    def handle_voice(self, message: Message, user: UsersOrm) -> None:
        """Handle voice file processing."""
        data = self._fetch_media(message, message.voice, "No voice message found.")
        if data is None:
            return
        answer = self._summarizer.summarize(
            data=data,
            **self._summary_kwargs(user),
        )
        self._messenger.send_answer(message, answer)

    def _handle_video_like(self, message: Message, user: UsersOrm, data: File) -> None:
        """Shared video / video-note pipeline: download, compress, summarize."""
        downloaded_file = self._downloader.download_tg(data, ext=".mp4")
        compressed_file = generate_temporary_name(ext=".ogg")
        try:
            compress_audio(input_file=downloaded_file, output_file=compressed_file)
            answer = self._summarizer.summarize(
                data=compressed_file,
                **self._summary_kwargs(user),
            )
            self._messenger.send_answer(message, answer)
        finally:
            clean_up(file=downloaded_file)
            clean_up(file=compressed_file)

    def handle_video_note(self, message: Message, user: UsersOrm) -> None:
        """Handle video note file processing."""
        data = self._fetch_media(message, message.video_note, "No video note found.")
        if data is None:
            return
        self._handle_video_like(message, user, data)

    def handle_video(self, message: Message, user: UsersOrm) -> None:
        """Handle video file processing."""
        data = self._fetch_media(message, message.video, "No video file found.")
        if data is None:
            return
        self._handle_video_like(message, user, data)

    def handle_document(self, message: Message, user: UsersOrm) -> None:
        """Handle document file processing."""
        document = message.document
        data = self._fetch_media(message, document, "No document found.")
        if data is None or document is None:
            return
        answer = self._summarizer.summarize_with_document(
            file=data,
            mime_type=document.mime_type or "application/octet-stream",
            **self._summary_kwargs(user),
        )
        self._messenger.send_answer(message, answer)

    def handle_url(self, message: Message, user: UsersOrm, url: str) -> None:
        """Handle URL processing."""
        kind = classify_url(url)
        if kind in ("youtube", "castro"):
            answer = self._summarizer.summarize(
                data=url,
                **self._summary_kwargs(user),
            )
            self._messenger.send_answer(message, answer)
        elif kind == "web":
            self._quota_manager.check_quota(
                user_id=user.user_id,
                daily_limit=user.daily_limit,
                quantity=0,
            )
            parsed = self._web_parser.parse(url)
            answer = format_prefixed_summary(
                parsed.prefix,
                self._summarizer.summarize_text(
                    text=parsed.text,
                    **self._summary_kwargs(user),
                ),
            )
            self._messenger.send_answer(message, answer)
        else:
            self._bot.send_message(message.chat.id, "No data to proceed.")
