"""Composition root: builds the application object graph once, from config's clients."""

from __future__ import annotations

from dataclasses import dataclass

import config
import database
from database import UserRepository
from download import Downloader
from llm import LLMClient
from parsing import ExaBackend, TavilyBackend, UrlResolver, WebParser
from services import GeminiHelper, Messenger, QuotaManager, Tracer
from transcription import ApiBackend, AudioTranscriber, YouTubeTranscriber, YtDlpBackend

# Later slices append summarizer and the handlers to this dataclass; main.py
# adopts the container in a later slice (STG-135).


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


def build_container() -> Container:
    """Construct the application object graph from config's clients."""
    return Container(
        messenger=Messenger(config.bot),
        quota_manager=QuotaManager(config.rate_limiter, config.per_minute_rate),
        gemini_helper=GeminiHelper(config.gemini_client),
        tracer=Tracer(config.langfuse_client),
        user_repo=UserRepository(database.Session),
        llm_client=LLMClient(config.gemini_client),
        downloader=Downloader(config.TG_API_TOKEN),
        web_parser=WebParser(
            ExaBackend(config.exa_client),
            TavilyBackend(config.tavily_client),
            UrlResolver(),
        ),
        audio_transcriber=AudioTranscriber(config.replicate_client),
        yt_transcriber=YouTubeTranscriber(ApiBackend(), YtDlpBackend()),
    )
