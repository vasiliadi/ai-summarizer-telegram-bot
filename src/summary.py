from __future__ import annotations

import logging
from dataclasses import replace
from textwrap import dedent
from typing import TYPE_CHECKING, cast

from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import SSLError as CurlSSLError
from openai import APIError
from telebot.types import File
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import DEFAULT_MODEL_ID_FOR_SUMMARY, MODEL_SPECS
from domain import format_prefixed_summary
from exceptions import FetchTranscriptError
from prompts import PROMPTS
from utils import classify_url, clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    from tenacity import _utils as tenacity_utils

    from domain import SummarySettings
    from download import Downloader
    from llm import LLMClient
    from services import OpenRouterFiles, QuotaManager
    from transcription import AudioTranscriber, CastroTranscriber, YouTubeTranscriber

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class Summarizer:
    """Generates model-backed summaries from audio, video, documents, and URLs."""

    def __init__(
        self,
        quota_manager: QuotaManager,
        openrouter_files: OpenRouterFiles,
        llm_client: LLMClient,
        downloader: Downloader,
        audio_transcriber: AudioTranscriber,
        yt_transcriber: YouTubeTranscriber,
        castro_transcriber: CastroTranscriber,
    ) -> None:
        """Store the injected collaborators used to build a summary."""
        self._quota_manager = quota_manager
        self._openrouter_files = openrouter_files
        self._llm_client = llm_client
        self._downloader = downloader
        self._audio_transcriber = audio_transcriber
        self._yt_transcriber = yt_transcriber
        self._castro_transcriber = castro_transcriber

    def _summarize_uploaded_file(
        self,
        file: str,
        mime_type: str,
        settings: SummarySettings,
    ) -> str:
        """Upload a local document to OpenRouter, summarize it, then delete the upload.

        The caller owns `file` on disk, has already run the non-consuming quota
        pre-check, and carries the `@retry` this runs under — so this method must
        stay undecorated.
        """
        prompt = dedent(PROMPTS[settings.prompt_key]).strip()
        file_id = self._openrouter_files.upload(file=file, mime_type=mime_type)
        try:
            self._quota_manager.check_quota(
                user_id=settings.user_id,
                daily_limit=settings.daily_limit,
                quantity=1,
            )
            return self._llm_client.run(
                content=[prompt, self._llm_client.build_file_part(file_id)],
                model_id=settings.model,
                target_language=settings.target_language,
                thinking_level=settings.thinking_level,
            )
        finally:
            try:
                self._openrouter_files.delete(file_id)
            except Exception as e:
                logger.warning(
                    "Failed to delete OpenRouter file %s: %s",
                    file_id,
                    e,
                )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(30),
        retry=retry_if_exception_type((APIError, AttributeError)),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def summarize_text(
        self,
        text: str,
        settings: SummarySettings,
    ) -> str:
        """Summarize already-extracted text (a transcript or webpage content).

        The prompt and the content go in as two parts rather than one
        concatenated string, so a trace records them as separate fields — an
        evaluator can then swap either one without parsing them apart. A
        multi-part text prompt is still text-only, so the run stays traced.
        Blank `text` drops its part instead of sending an empty one.

        Raises:
            RetryError: If transient model errors persist, or the model keeps
                returning an empty response — the `AttributeError` that stands
                for it is retried and then wrapped, never re-raised.

        """
        prompt = dedent(PROMPTS[settings.prompt_key]).strip()
        # Silent or music-only audio gives WhisperX no segments, so a transcript
        # can be "", and an empty text part is not worth sending.
        content = [prompt, text] if text.strip() else [prompt]
        self._quota_manager.check_quota(
            user_id=settings.user_id,
            daily_limit=settings.daily_limit,
            quantity=1,
        )
        return self._llm_client.run(
            content=content,
            model_id=settings.model,
            target_language=settings.target_language,
            thinking_level=settings.thinking_level,
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(30),
        retry=retry_if_exception_type(
            (APIError, AttributeError, CurlSSLError, CurlConnectionError),
        ),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def summarize_with_document(
        self,
        file: File,
        mime_type: str,
        settings: SummarySettings,
    ) -> str:
        """Summarize document content by uploading it to OpenRouter's Files API.

        Audio documents take the Replicate transcription path instead, and so
        carry the 📝 prefix. Any other document sent to a model that takes no
        file is summarized by `DEFAULT_MODEL_ID_FOR_SUMMARY`.

        Raises:
            RetryError: If the operation fails after all retry attempts —
                including a failed upload and an empty model response, which
                arrives as a retried, then wrapped, `AttributeError`.

        """
        self._quota_manager.check_quota(
            user_id=settings.user_id,
            daily_limit=settings.daily_limit,
            quantity=0,
        )
        if mime_type.startswith("audio/"):
            data = self._downloader.download_tg(file, ext=".ogg")
            try:
                return self._summarize_via_transcription(
                    data=data,
                    settings=settings,
                )
            finally:
                clean_up(file=data)
        if not MODEL_SPECS[settings.model].supports_files:
            logger.warning(
                "%s takes no uploaded file, summarizing this document with %s",
                settings.model,
                DEFAULT_MODEL_ID_FOR_SUMMARY,
            )
            settings = replace(settings, model=DEFAULT_MODEL_ID_FOR_SUMMARY)
        data = self._downloader.download_tg(file)
        try:
            return self._summarize_uploaded_file(
                file=data,
                mime_type=mime_type,
                settings=settings,
            )
        finally:
            clean_up(file=data)

    def summarize(
        self,
        data: str | File,
        settings: SummarySettings,
    ) -> str:
        """Generate a summary from a YouTube/Castro URL, a Telegram file, or a path.

        Returns:
            str: The summary, prefixed with the source-provenance emoji of the
                transcript or the Replicate transcription it was made from.

        Raises:
            RetryError: If all summarization attempts fail after retries.

        """
        self._quota_manager.check_quota(
            user_id=settings.user_id,
            daily_limit=settings.daily_limit,
            quantity=0,
        )
        if isinstance(data, str):
            kind = classify_url(data)
            if kind in ("youtube", "castro"):
                transcriber = (
                    self._yt_transcriber
                    if kind == "youtube"
                    else self._castro_transcriber
                )
                try:
                    transcript_result = transcriber.get_transcript(data)
                except (FetchTranscriptError, ValueError) as e:
                    logger.warning(
                        "get_transcript failed, falling back to download: %s",
                        e,
                    )
                else:
                    return format_prefixed_summary(
                        transcript_result.prefix,
                        self.summarize_text(
                            text=transcript_result.text,
                            settings=settings,
                        ),
                    )
                data = (
                    self._downloader.download_yt(data)
                    if kind == "youtube"
                    else self._downloader.download_castro(data)
                )
        if isinstance(data, File):
            data = self._downloader.download_tg(data, ext=".ogg")

        try:
            return self._summarize_via_transcription(
                data=data,
                settings=settings,
            )
        finally:
            clean_up(file=data)

    def _summarize_via_transcription(
        self,
        data: str,
        settings: SummarySettings,
    ) -> str:
        """Transcribe an audio file with Replicate, then summarize the transcript.

        The only route for spoken content. The caller owns `data`; only the
        compressed copy made here is cleaned up.
        """
        new_file = generate_temporary_name(ext=".ogg")
        try:
            compress_audio(input_file=data, output_file=new_file)
            transcription = self._audio_transcriber.transcribe(new_file)
            return format_prefixed_summary(
                "📝",
                self.summarize_text(
                    text=transcription,
                    settings=settings,
                ),
            )
        finally:
            clean_up(file=new_file)
