"""Composition root: builds the application object graph once, from config's clients."""

from __future__ import annotations

from dataclasses import dataclass

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

# main.py adopting the container (STG-135) is all that remains after this
# slice.


@dataclass(frozen=True)
class Container:
    """The wired-up collaborators the application runs on."""

    messenger: Messenger
    quota_manager: QuotaManager
    gemini_helper: GeminiHelper
    tracer: Tracer
    user_repo: UserRepository
    llm_client: LLMClient
    downloader: Downloader
    web_parser: WebParser
    audio_transcriber: AudioTranscriber
    yt_transcriber: YouTubeTranscriber
    summarizer: Summarizer
    handlers: MessageHandlers


def build_container() -> Container:
    """Construct the application object graph from config's clients."""
    messenger = Messenger(config.bot)
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
        messenger=messenger,
        quota_manager=quota_manager,
        gemini_helper=gemini_helper,
        tracer=Tracer(config.langfuse_client),
        user_repo=UserRepository(database.Session),
        llm_client=llm_client,
        downloader=downloader,
        web_parser=web_parser,
        audio_transcriber=audio_transcriber,
        yt_transcriber=yt_transcriber,
        summarizer=summarizer,
        handlers=MessageHandlers(
            config.bot,
            messenger,
            summarizer,
            web_parser,
            quota_manager,
            downloader,
        ),
    )
