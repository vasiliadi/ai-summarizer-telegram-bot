"""Composition root: builds the application object graph once, from config's clients."""

from __future__ import annotations

from dataclasses import dataclass

import config
from services import GeminiHelper, Messenger, QuotaManager, Tracer

# Later slices append user_repo, llm_client, downloader, web_parser,
# audio_transcriber, yt_transcriber, summarizer, and the handlers to this
# dataclass; main.py adopts the container in a later slice (STG-135).


@dataclass(frozen=True)
class Container:
    """The wired-up collaborators the application runs on."""

    messenger: Messenger
    quota_manager: QuotaManager
    gemini_helper: GeminiHelper
    tracer: Tracer


def build_container() -> Container:
    """Construct the application object graph from config's clients."""
    return Container(
        messenger=Messenger(config.bot),
        quota_manager=QuotaManager(config.rate_limiter, config.per_minute_rate),
        gemini_helper=GeminiHelper(config.gemini_client),
        tracer=Tracer(config.langfuse_client),
    )
