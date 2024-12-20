import logging
import time
from ssl import SSLEOFError
from textwrap import dedent

from google.genai import types
from sentry_sdk import capture_exception
from telebot.types import File
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from youtube_transcript_api._errors import NoTranscriptAvailable, TranscriptsDisabled

from config import GEMINI_CONFIG, gemini_client
from download import download_castro, download_tg, download_yt
from prompts import (
    BASIC_PROMPT_FOR_FILE,
    BASIC_PROMPT_FOR_TRANSCRIPT,
    BASIC_PROMPT_FOR_WEBPAGE,
)
from services import check_quota
from transcription import get_yt_transcript, transcribe
from utils import clean_up, compress_audio, generate_temporary_name

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(
        (SSLEOFError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def summarize_with_file(file: str, model: str, sleep_time: int = 10) -> str:
    """Summarize audio content from a file using Gemini API.

    This function uploads an audio file to Gemini, waits for processing,
    and generates a summary of the content.

    Args:
        file (str): Path to the audio file to be summarized
        model (str): The Gemini model identifier to use for summarization
        sleep_time (int, optional): Time to wait between processing status checks.
                                    Defaults to 10.

    Returns:
        str: Generated summary text of the audio content

    Raises:
        ValueError: If the file processing fails
        RetryError: If maximum retries are exceeded for SSL errors

    """
    prompt = BASIC_PROMPT_FOR_FILE
    audio_file = gemini_client.files.upload(path=file)
    while audio_file.state == "PROCESSING":
        time.sleep(sleep_time)
        audio_file = gemini_client.files.get(name=audio_file.name)
    if audio_file.state == "FAILED":
        raise ValueError(audio_file.state)
    check_quota(quantity=1)
    response = gemini_client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(
                        file_uri=audio_file.uri,
                        mime_type=audio_file.mime_type,
                    ),
                    types.Part.from_text(prompt),
                ],
            ),
        ],
        config=GEMINI_CONFIG,
    )
    gemini_client.files.delete(name=audio_file.name)
    return response.text


def summarize_with_transcript(transcript: str, model: str) -> str:
    """Summarize content from a transcript using Gemini API.

    This function takes a transcript text and generates a summary using the specified
    Gemini model. It prepends a predefined prompt to the transcript before sending
    it to the API.

    Args:
        transcript (str): The transcript text to be summarized
        model (str): The Gemini model identifier to use for summarization

    Returns:
        str: Generated summary text of the transcript content

    Note:
        This function checks the API quota before making the request and uses
        the global GEMINI_CONFIG for API configuration settings.

    """
    prompt = (f"{dedent(BASIC_PROMPT_FOR_TRANSCRIPT)} {transcript}").strip()
    check_quota(quantity=1)
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=GEMINI_CONFIG,
    )
    return response.text


def summarize_webpage(content: str, model: str) -> str:
    """Summarize content from a webpage using Gemini API.

    This function takes webpage content and generates a summary using the specified
    Gemini model. It prepends a predefined prompt to the content before sending
    it to the API.

    Args:
        content (str): The webpage content to be summarized
        model (str): The Gemini model identifier to use for summarization

    Returns:
        str: Generated summary text of the webpage content

    Note:
        This function checks the API quota before making the request and uses
        the global GEMINI_CONFIG for API configuration settings.

    """
    prompt = f"{BASIC_PROMPT_FOR_WEBPAGE} {content}"
    check_quota(quantity=1)
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=GEMINI_CONFIG,
    )
    return response.text


def summarize(
    data: str | File,
    use_transcription: bool,
    model: str,
    use_yt_transcription: bool = False,
) -> str:
    """Process and summarize content from various sources using Gemini API.

    This function handles multiple content types and sources, including:
    - Castro.fm podcast episodes
    - YouTube videos (with optional transcript-based summarization)
    - Telegram audio files

    Args:
        data (str | File): Either a URL (str) to content or a Telegram File object.
            Supported URLs include Castro.fm episodes and YouTube videos.
        use_transcription (bool): Whether to fall back to transcription-based
            summarization if direct file summarization fails.
        model (str): The Gemini model identifier to use for summarization.
        use_yt_transcription (bool, optional): Whether to attempt using YouTube's
            built-in transcripts for YouTube URLs. Defaults to False.

    Returns:
        str: Generated summary of the content, prefixed with:
            - 📹 for YouTube transcript summaries
            - 📝 for fallback transcription summaries
            - No prefix for direct file summaries

    Note:
        The function automatically handles cleanup of temporary files after
        processing, regardless of success or failure.

    """
    if isinstance(data, str):
        if data.startswith("https://castro.fm/episode/"):
            data = download_castro(data)
        if data.startswith(("https://youtu.be/", "https://www.youtube.com/")):
            if use_yt_transcription:
                try:
                    transcript = get_yt_transcript(data)
                    return dedent(f"""
                                  📹
                                  {summarize_with_transcript(transcript, model)}
                                  """).strip()
                except (
                    TranscriptsDisabled,
                    NoTranscriptAvailable,
                    RetryError,
                ):
                    pass
            data = download_yt(data)
    if isinstance(data, File):
        data = download_tg(data)

    try:
        return summarize_with_file(data, model)
    except RetryError as e:
        logger.warning("Error occurred while summarizing with file: %s", e)
        if use_transcription:
            new_file = generate_temporary_name(ext=".ogg")
            compress_audio(input_file=data, output_file=new_file)
            try:
                transcription = transcribe(new_file)
                # If it fails, a RetryError will raise
                return dedent(f"""
                              📝
                              {summarize_with_transcript(transcription, model)}
                              """).strip()
            finally:
                clean_up(file=new_file)
        capture_exception(e)
        raise
    finally:
        clean_up(file=data)
