"""Composition root: builds the application object graph once, from config's clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import config
import database
from database import UserRepository
from download import Downloader
from handlers import MessageHandlers
from llm import LLMClient
from parsing import ExaBackend, TavilyBackend, UrlResolver, WebParser
from services import GeminiHelper, Messenger, QuotaManager, Tracer
from summary import Summarizer
from transcription import ApiBackend, AudioTranscriber, YouTubeTranscriber, YtDlpBackend

if TYPE_CHECKING:
    import telebot


@dataclass(frozen=True)
class Container:
    """The wired-up collaborators `main.build_app` runs on.

    Only the roots BotApp holds directly; everything else in the graph is reached
    through `handlers`, which owns the collaborators it needs.
    """

    bot: telebot.TeleBot
    quota_manager: QuotaManager
    tracer: Tracer
    user_repo: UserRepository
    handlers: MessageHandlers


def build_container() -> Container:
    """Construct the application object graph from config's clients."""
    bot = config.bot
    messenger = Messenger(bot)
    quota_manager = QuotaManager(config.rate_limiter, config.per_minute_rate)
    gemini_helper = GeminiHelper(config.gemini_client)
    llm_client = LLMClient(config.gemini_client)
    downloader = Downloader(config.TG_API_TOKEN)
    web_parser = WebParser(
        ExaBackend(config.exa_client),
        TavilyBackend(config.tavily_client),
        UrlResolver(),
    )
    audio_transcriber = AudioTranscriber(config.replicate_client)
    yt_transcriber = YouTubeTranscriber(ApiBackend(), YtDlpBackend())
    summarizer = Summarizer(
        quota_manager,
        gemini_helper,
        llm_client,
        downloader,
        audio_transcriber,
        yt_transcriber,
    )
    return Container(
        bot=bot,
        quota_manager=quota_manager,
        tracer=Tracer(config.langfuse_client),
        user_repo=UserRepository(database.Session),
        handlers=MessageHandlers(
            bot,
            messenger,
            summarizer,
            web_parser,
            quota_manager,
            downloader,
        ),
    )
