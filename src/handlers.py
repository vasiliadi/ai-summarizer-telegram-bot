from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import DEFAULT_MODEL_ID_FOR_SUMMARY, MODEL_SPECS, TG_MAX_FILE_SIZE
from domain import SummarySettings, format_prefixed_summary
from utils import classify_url

if TYPE_CHECKING:
    import telebot
    from telebot.types import Audio, Document, File, Message, Video, VideoNote, Voice

    from models import UsersOrm
    from parsing import WebParser
    from services import Messenger, QuotaManager
    from summary import Summarizer

    _SizedMedia = Audio | Voice | Video | VideoNote | Document

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Per-content-type Telegram message handlers."""

    def __init__(
        self,
        bot: telebot.TeleBot,
        messenger: Messenger,
        summarizer: Summarizer,
        web_parser: WebParser,
        quota_manager: QuotaManager,
    ) -> None:
        """Store the injected collaborators used to handle Telegram messages."""
        self._bot = bot
        self._messenger = messenger
        self._summarizer = summarizer
        self._web_parser = web_parser
        self._quota_manager = quota_manager

    @staticmethod
    def _settings(user: UsersOrm) -> SummarySettings:
        """Build the summarization settings sourced from a user record."""
        model = user.summarizing_model
        # A row can outlive its model id. See architecture.md → *Dropping or
        # renaming a model id*.
        if model not in MODEL_SPECS:
            logger.warning(
                "%s is not registered, summarizing with %s",
                model,
                DEFAULT_MODEL_ID_FOR_SUMMARY,
            )
            model = DEFAULT_MODEL_ID_FOR_SUMMARY
        return SummarySettings(
            model=model,
            prompt_key=user.prompt_key_for_summary,
            target_language=user.target_language,
            user_id=user.user_id,
            daily_limit=user.daily_limit,
            thinking_level=user.thinking_level,
        )

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

    def _summarize_media(
        self,
        message: Message,
        user: UsersOrm,
        media: _SizedMedia | None,
        missing_msg: str,
    ) -> None:
        """Summarize a spoken-media message and send the answer."""
        data = self._fetch_media(message, media, missing_msg)
        if data is None:
            return
        answer = self._summarizer.summarize(
            data=data,
            settings=self._settings(user),
        )
        self._messenger.send_answer(message, answer)

    def handle_audio(self, message: Message, user: UsersOrm) -> None:
        """Handle audio file processing."""
        self._summarize_media(message, user, message.audio, "No audio file found.")

    def handle_voice(self, message: Message, user: UsersOrm) -> None:
        """Handle voice file processing."""
        self._summarize_media(message, user, message.voice, "No voice message found.")

    def handle_video_note(self, message: Message, user: UsersOrm) -> None:
        """Handle video note file processing."""
        self._summarize_media(
            message,
            user,
            message.video_note,
            "No video note found.",
        )

    def handle_video(self, message: Message, user: UsersOrm) -> None:
        """Handle video file processing."""
        self._summarize_media(message, user, message.video, "No video file found.")

    def handle_document(self, message: Message, user: UsersOrm) -> None:
        """Handle document file processing."""
        document = message.document
        data = self._fetch_media(message, document, "No document found.")
        if data is None or document is None:
            return
        answer = self._summarizer.summarize_with_document(
            file=data,
            mime_type=document.mime_type or "application/octet-stream",
            settings=self._settings(user),
        )
        self._messenger.send_answer(message, answer)

    def handle_url(self, message: Message, user: UsersOrm, url: str) -> None:
        """Handle URL processing."""
        kind = classify_url(url)
        if kind in ("youtube", "castro"):
            answer = self._summarizer.summarize(
                data=url,
                settings=self._settings(user),
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
                    settings=self._settings(user),
                ),
            )
            self._messenger.send_answer(message, answer)
        else:
            self._bot.send_message(message.chat.id, "No data to proceed.")
