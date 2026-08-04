from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING, cast

from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import SSLError as CurlSSLError
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from requests.exceptions import SSLError
from telebot.types import File
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import MODEL_SPECS
from domain import format_prefixed_summary
from exceptions import FetchTranscriptError
from prompts import PROMPTS
from utils import classify_url, clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    from tenacity import _utils as tenacity_utils

    from download import Downloader
    from llm import LLMClient
    from services import GeminiHelper, QuotaManager
    from transcription import AudioTranscriber, YouTubeTranscriber

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class Summarizer:
    """Generates model-backed summaries from audio, video, documents, and URLs."""

    def __init__(
        self,
        quota_manager: QuotaManager,
        gemini_helper: GeminiHelper,
        llm_client: LLMClient,
        downloader: Downloader,
        audio_transcriber: AudioTranscriber,
        yt_transcriber: YouTubeTranscriber,
    ) -> None:
        """Store the injected collaborators used to build a summary."""
        self._quota_manager = quota_manager
        self._gemini_helper = gemini_helper
        self._llm_client = llm_client
        self._downloader = downloader
        self._audio_transcriber = audio_transcriber
        self._yt_transcriber = yt_transcriber

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(30),
        retry=retry_if_exception_type(
            (ModelAPIError, AttributeError, UnexpectedModelBehavior, SSLError),
        ),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def summarize_with_file(
        self,
        file: str,
        model: str,
        prompt_key: str,
        target_language: str,
        user_id: int,
        daily_limit: int,
        thinking_level: str,
        sleep_time: int = 10,
    ) -> str:
        """Summarize audio content by uploading it to the provider's file API.

        Raises:
            AttributeError: If the model returns an empty response, or the upload
                helper reports incomplete file metadata.
            ValueError: If the provider reports a failed processing state.
            RetryError: If transient model or network errors persist after retries.

        """
        self._quota_manager.check_quota(
            user_id=user_id,
            daily_limit=daily_limit,
            quantity=0,
        )
        prompt = dedent(PROMPTS[prompt_key]).strip()
        mime_type = self._gemini_helper.resolve_mime_type(file)
        audio_file = self._gemini_helper.upload_and_wait_for_file(
            file=file,
            mime_type=mime_type,
            sleep_time=sleep_time,
        )
        audio_file_name = cast("str", audio_file.name)
        try:
            self._quota_manager.check_quota(
                user_id=user_id,
                daily_limit=daily_limit,
                quantity=1,
            )
            return self._llm_client.run(
                content=[
                    prompt,
                    self._llm_client.build_uploaded_file(
                        model_id=model,
                        file=audio_file,
                    ),
                ],
                model_id=model,
                target_language=target_language,
                thinking_level=thinking_level,
            )
        finally:
            try:
                self._gemini_helper.delete_file(audio_file_name)
            except Exception as e:
                logger.warning(
                    "Failed to delete Gemini file %s: %s",
                    audio_file_name,
                    e,
                )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(30),
        retry=retry_if_exception_type(
            (ModelAPIError, AttributeError, UnexpectedModelBehavior),
        ),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def summarize_text(
        self,
        text: str,
        model: str,
        prompt_key: str,
        target_language: str,
        user_id: int,
        daily_limit: int,
        thinking_level: str,
    ) -> str:
        """Summarize already-extracted text (a transcript or webpage content).

        Raises:
            AttributeError: If the model returns an empty response.
            RetryError: If transient model or network errors persist after retries.

        """
        prompt = (f"{dedent(PROMPTS[prompt_key])} {text}").strip()
        self._quota_manager.check_quota(
            user_id=user_id,
            daily_limit=daily_limit,
            quantity=1,
        )
        return self._llm_client.run(
            content=prompt,
            model_id=model,
            target_language=target_language,
            thinking_level=thinking_level,
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(30),
        retry=retry_if_exception_type(
            (
                ModelAPIError,
                AttributeError,
                UnexpectedModelBehavior,
                SSLError,
                CurlSSLError,
                CurlConnectionError,
            ),
        ),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def summarize_with_document(
        self,
        file: File,
        model: str,
        prompt_key: str,
        target_language: str,
        mime_type: str,
        user_id: int,
        daily_limit: int,
        thinking_level: str,
        sleep_time: int = 10,
    ) -> str:
        """Summarize document content by uploading it to the provider's file API.

        Audio documents sent to a model that cannot read audio take the Replicate
        transcription path instead, and so carry the 📝 prefix.

        Raises:
            AttributeError: If the provider returns incomplete file metadata, or
                the model returns an empty response.
            ValueError: If the document processing fails on the provider's side.
            RetryError: If the operation fails after all retry attempts.

        """
        data: str | None = None
        document_file_name: str | None = None
        if mime_type.startswith("audio/") and not MODEL_SPECS[model].supports_audio:
            self._quota_manager.check_quota(
                user_id=user_id,
                daily_limit=daily_limit,
                quantity=0,
            )
            data = self._downloader.download_tg(file, ext=".ogg")
            try:
                return self._summarize_via_transcription(
                    data=data,
                    model=model,
                    prompt_key=prompt_key,
                    target_language=target_language,
                    user_id=user_id,
                    daily_limit=daily_limit,
                    thinking_level=thinking_level,
                )
            finally:
                clean_up(file=data)
        try:
            self._quota_manager.check_quota(
                user_id=user_id,
                daily_limit=daily_limit,
                quantity=0,
            )
            data = self._downloader.download_tg(file)
            prompt = dedent(PROMPTS[prompt_key]).strip()
            document_file = self._gemini_helper.upload_and_wait_for_file(
                file=data,
                mime_type=mime_type,
                sleep_time=sleep_time,
            )
            document_file_name = document_file.name
            self._quota_manager.check_quota(
                user_id=user_id,
                daily_limit=daily_limit,
                quantity=1,
            )
            summary = self._llm_client.run(
                content=[
                    prompt,
                    self._llm_client.build_uploaded_file(
                        model_id=model,
                        file=document_file,
                    ),
                ],
                model_id=model,
                target_language=target_language,
                thinking_level=thinking_level,
            )
        finally:
            if document_file_name is not None:
                try:
                    self._gemini_helper.delete_file(document_file_name)
                except Exception as e:
                    logger.warning(
                        "Failed to delete Gemini file %s: %s",
                        document_file_name,
                        e,
                    )
            if data is not None:
                clean_up(file=data)
        return summary

    def summarize(
        self,
        data: str | File,
        model: str,
        prompt_key: str,
        target_language: str,
        user_id: int,
        daily_limit: int,
        thinking_level: str,
    ) -> str:
        """Generate a summary from a YouTube/Castro URL, a Telegram file, or a path.

        Returns:
            str: The summary, carrying a source-provenance prefix on the
                transcript and Replicate-transcription paths only.

        Raises:
            RetryError: If all summarization attempts fail after retries.

        """
        self._quota_manager.check_quota(
            user_id=user_id,
            daily_limit=daily_limit,
            quantity=0,
        )
        if isinstance(data, str):
            kind = classify_url(data)
            if kind == "castro":
                data = self._downloader.download_castro(data)
            elif kind == "youtube":
                try:
                    transcript_result = self._yt_transcriber.get_transcript(data)
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
                            model=model,
                            prompt_key=prompt_key,
                            target_language=target_language,
                            user_id=user_id,
                            daily_limit=daily_limit,
                            thinking_level=thinking_level,
                        ),
                    )
                data = self._downloader.download_yt(data)
        if isinstance(data, File):
            data = self._downloader.download_tg(data, ext=".ogg")

        try:
            if not MODEL_SPECS[model].supports_audio:
                return self._summarize_via_transcription(
                    data=data,
                    model=model,
                    prompt_key=prompt_key,
                    target_language=target_language,
                    user_id=user_id,
                    daily_limit=daily_limit,
                    thinking_level=thinking_level,
                )
            # Nested so that a RetryError raised by the transcription path itself
            # propagates instead of re-entering it.
            try:
                return self.summarize_with_file(
                    file=data,
                    model=model,
                    prompt_key=prompt_key,
                    target_language=target_language,
                    user_id=user_id,
                    daily_limit=daily_limit,
                    thinking_level=thinking_level,
                )
            except RetryError as e:
                logger.warning("Error occurred while summarizing with file: %s", e)
                return self._summarize_via_transcription(
                    data=data,
                    model=model,
                    prompt_key=prompt_key,
                    target_language=target_language,
                    user_id=user_id,
                    daily_limit=daily_limit,
                    thinking_level=thinking_level,
                )
        finally:
            clean_up(file=data)

    def _summarize_via_transcription(
        self,
        data: str,
        model: str,
        prompt_key: str,
        target_language: str,
        user_id: int,
        daily_limit: int,
        thinking_level: str,
    ) -> str:
        """Transcribe an audio file with Replicate, then summarize the transcript.

        Serves both the rescue path, when the provider's file API fails, and
        models that cannot read audio at all. The caller owns `data`; only the
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
                    model=model,
                    prompt_key=prompt_key,
                    target_language=target_language,
                    user_id=user_id,
                    daily_limit=daily_limit,
                    thinking_level=thinking_level,
                ),
            )
        finally:
            clean_up(file=new_file)
