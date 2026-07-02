from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING, Any, cast

from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import SSLError as CurlSSLError

# Private import: 2.10.0 exposes no public path for the Interactions error
# hierarchy. A canary test in tests/test_summary.py ("no_public_import_path")
# fails the suite when an SDK bump adds one — switch this import then.
from google.genai._gaos.lib.compat_errors import APIError as InteractionsAPIError
from google.genai.errors import ClientError, ServerError
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

from config import gemini_client
from domain import format_prefixed_summary
from download import download_castro, download_tg, download_yt
from exceptions import FetchTranscriptError, GeminiIncompleteResponseError
from prompts import PROMPTS
from services import (
    check_quota,
    get_gemini_kwargs,
    resolve_mime_type,
    upload_and_wait_for_file,
)
from transcription import get_yt_transcript, transcribe
from utils import clean_up, compress_audio, generate_temporary_name

if TYPE_CHECKING:
    from google.genai.interactions import Interaction
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class Summarizer:
    """Generates Gemini-powered summaries from audio, video, documents, and URLs."""

    @staticmethod
    def _generate_text(
        contents: str | list[Any],
        model: str,
        target_language: str,
        thinking_level: str,
    ) -> str:
        """Run a single Gemini interaction and return its non-empty text output."""
        interaction = cast(
            "Interaction",
            gemini_client.interactions.create(
                model=model,
                input=contents,
                **get_gemini_kwargs(target_language, thinking_level=thinking_level),
            ),
        )
        if not interaction.output_text:
            raise GeminiIncompleteResponseError
        return interaction.output_text

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(30),
        retry=retry_if_exception_type(
            (
                ServerError,
                GeminiIncompleteResponseError,
                ClientError,
                SSLError,
                InteractionsAPIError,
            ),
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
        """Summarize audio content using Gemini API with file upload.

        Args:
            file (str): Path to the audio file to be summarized.
            model (str): The Gemini model identifier.
            prompt_key (str): Key to retrieve the prompt template from PROMPTS.
            target_language (str): The language to translate the summary into.
            user_id (int): Telegram user ID for per-user quota enforcement.
            daily_limit (int): The user's configured daily request cap.
            thinking_level (str): AI thinking level.
            sleep_time (int, optional): Time between processing checks. Defaults to 10.

        Returns:
            str: Generated summary text from the audio content.

        Raises:
            GeminiIncompleteResponseError: If Gemini returns incomplete file or
                response metadata.
            ValueError: If Gemini reports a failed processing state.
            RetryError: If transient Gemini or network errors persist after retries.

        """
        check_quota(user_id=user_id, daily_limit=daily_limit, quantity=0)
        prompt = dedent(PROMPTS[prompt_key]).strip()
        mime_type = resolve_mime_type(file)
        audio_file = upload_and_wait_for_file(
            file=file,
            mime_type=mime_type,
            sleep_time=sleep_time,
        )
        audio_file_name = audio_file.name
        try:
            if audio_file.uri is None or audio_file.mime_type is None:
                raise GeminiIncompleteResponseError
            check_quota(user_id=user_id, daily_limit=daily_limit, quantity=1)
            return self._generate_text(
                [
                    {"type": "text", "text": prompt},
                    {
                        "type": "audio",
                        "uri": audio_file.uri,
                        "mime_type": audio_file.mime_type,
                    },
                ],
                model,
                target_language,
                thinking_level,
            )
        finally:
            if audio_file_name is not None:
                try:
                    gemini_client.files.delete(name=audio_file_name)
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
            (
                ServerError,
                GeminiIncompleteResponseError,
                ClientError,
                InteractionsAPIError,
            ),
        ),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def _summarize_text(
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

        Args:
            text (str): The text to summarize (transcript or pre-parsed webpage).
            model (str): The Gemini model identifier.
            prompt_key (str): Key to retrieve the prompt template from PROMPTS.
            target_language (str): The language to translate the summary into.
            user_id (int): Telegram user ID for per-user quota enforcement.
            daily_limit (int): The user's configured daily request cap.
            thinking_level (str): AI thinking level.

        Returns:
            str: Generated summary text.

        Raises:
            GeminiIncompleteResponseError: If Gemini returns an empty response.
            RetryError: If transient Gemini or network errors persist after retries.

        """
        prompt = (f"{dedent(PROMPTS[prompt_key])} {text}").strip()
        check_quota(user_id=user_id, daily_limit=daily_limit, quantity=1)
        return self._generate_text(prompt, model, target_language, thinking_level)

    def summarize_with_transcript(
        self,
        transcript: str,
        model: str,
        prompt_key: str,
        target_language: str,
        user_id: int,
        daily_limit: int,
        thinking_level: str,
    ) -> str:
        """Generate a summary from a transcript using Gemini API.

        Thin wrapper over :meth:`_summarize_text`; see it for the full contract.

        """
        return self._summarize_text(
            transcript,
            model,
            prompt_key,
            target_language,
            user_id,
            daily_limit,
            thinking_level,
        )

    def summarize_webpage(
        self,
        content: str,
        model: str,
        prompt_key: str,
        target_language: str,
        user_id: int,
        daily_limit: int,
        thinking_level: str,
    ) -> str:
        """Generate a summary from pre-parsed webpage content using Gemini API.

        Thin wrapper over :meth:`_summarize_text`; see it for the full contract.

        """
        return self._summarize_text(
            content,
            model,
            prompt_key,
            target_language,
            user_id,
            daily_limit,
            thinking_level,
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(30),
        retry=retry_if_exception_type(
            (
                ServerError,
                GeminiIncompleteResponseError,
                ClientError,
                SSLError,
                CurlSSLError,
                CurlConnectionError,
                InteractionsAPIError,
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
        """Summarize document content using Gemini API with file upload.

        Args:
            file (File): Telegram File object for the document to be summarized.
            model (str): The Gemini model identifier.
            prompt_key (str): Key to retrieve the prompt template from PROMPTS.
            target_language (str): The language to translate the summary into.
            mime_type (str): MIME type of the document being uploaded.
            user_id (int): Telegram user ID for per-user quota enforcement.
            daily_limit (int): The user's configured daily request cap.
            thinking_level (str): AI thinking level.
            sleep_time (int, optional): Time between processing checks. Defaults to 10.

        Returns:
            str: Generated summary text from the document content.

        Raises:
            GeminiIncompleteResponseError: If Gemini returns incomplete file or
                response metadata.
            ValueError: If the document processing fails on Gemini's side.
            RetryError: If the operation fails after all retry attempts.

        """
        data: str | None = None
        document_file_name: str | None = None
        try:
            check_quota(user_id=user_id, daily_limit=daily_limit, quantity=0)
            data = download_tg(file)
            prompt = dedent(PROMPTS[prompt_key]).strip()
            document_file = upload_and_wait_for_file(
                file=data,
                mime_type=mime_type,
                sleep_time=sleep_time,
            )
            document_file_name = document_file.name
            if document_file.uri is None or document_file.mime_type is None:
                raise GeminiIncompleteResponseError
            check_quota(user_id=user_id, daily_limit=daily_limit, quantity=1)
            summary_text = self._generate_text(
                [
                    {"type": "text", "text": prompt},
                    {
                        "type": "document",
                        "uri": document_file.uri,
                        "mime_type": document_file.mime_type,
                    },
                ],
                model,
                target_language,
                thinking_level,
            )
        finally:
            if document_file_name is not None:
                try:
                    gemini_client.files.delete(name=document_file_name)
                except Exception as e:
                    logger.warning(
                        "Failed to delete Gemini file %s: %s",
                        document_file_name,
                        e,
                    )
            if data is not None:
                clean_up(file=data)
        return summary_text

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
        """Generate a summary from various input sources using Gemini API.

        Args:
            data (str | File): Input data to summarize. Can be:
                - YouTube URL
                - Castro.fm episode URL
                - Telegram File object
            model (str): The Gemini model identifier.
            prompt_key (str): Key to retrieve the prompt template from PROMPTS.
            target_language (str): The language to translate the summary into.
            user_id (int): Telegram user ID for per-user quota enforcement.
            daily_limit (int): The user's configured daily request cap.
            thinking_level (str): AI thinking level.

        Returns:
            str: Generated summary of the content, prefixed with the source emoji.

        Raises:
            RetryError: If all summarization attempts fail after retries.

        """
        check_quota(user_id=user_id, daily_limit=daily_limit, quantity=0)
        if isinstance(data, str):
            if data.startswith("https://castro.fm/episode/"):
                data = download_castro(data)
            if data.startswith(
                (
                    "https://youtu.be/",
                    "https://www.youtube.com/",
                    "https://youtube.com/",
                ),
            ):
                try:
                    transcript_result = get_yt_transcript(data)
                except (FetchTranscriptError, ValueError) as e:
                    logger.warning(
                        "get_yt_transcript failed, falling back to download: %s",
                        e,
                    )
                else:
                    return format_prefixed_summary(
                        transcript_result.prefix,
                        self.summarize_with_transcript(
                            transcript=transcript_result.text,
                            model=model,
                            prompt_key=prompt_key,
                            target_language=target_language,
                            user_id=user_id,
                            daily_limit=daily_limit,
                            thinking_level=thinking_level,
                        ),
                    )
                data = download_yt(data)
        if isinstance(data, File):
            data = download_tg(data, ext=".ogg")

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
            new_file = generate_temporary_name(ext=".ogg")
            try:
                compress_audio(input_file=data, output_file=new_file)
                transcription = transcribe(new_file)
                return format_prefixed_summary(
                    "📝",
                    self.summarize_with_transcript(
                        transcript=transcription,
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
        finally:
            clean_up(file=data)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

summarizer = Summarizer()


# ---------------------------------------------------------------------------
# Module-level aliases — preserve the existing public API
# ---------------------------------------------------------------------------

summarize_with_file = summarizer.summarize_with_file
summarize_with_transcript = summarizer.summarize_with_transcript
summarize_webpage = summarizer.summarize_webpage
summarize_with_document = summarizer.summarize_with_document
summarize = summarizer.summarize
