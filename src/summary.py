import mimetypes
import time
from ssl import SSLEOFError
from textwrap import dedent

import google.generativeai as genai
import requests
from google.api_core import exceptions, retry
from loguru import logger
from sentry_sdk import capture_exception
from telebot.types import File
from youtube_transcript_api._errors import NoTranscriptAvailable, TranscriptsDisabled

from config import gemini_pro_model
from download import download_castro, download_tg, download_yt
from prompts import (
    BASIC_PROMPT_FOR_FILE,
    BASIC_PROMPT_FOR_TRANSCRIPT,
    BASIC_PROMPT_FOR_WEBPAGE,
)
from services import check_quota
from transcription import get_yt_transcript, transcribe
from utils import clean_up, compress_audio, generate_temporary_name


@retry.Retry(predicate=retry.if_transient_error, initial=30, timeout=300)
def summarize_with_file(file: str, sleep_time: int = 10) -> str:
    """Summarize the content of an audio file using Gemini Pro model.

    This function uploads an audio file to Gemini, waits for processing,
    and generates a summary of its content. It includes automatic retry logic
    for transient errors.

    Args:
        file (str): Path to the audio file to be summarized
        sleep_time (int, optional): Time in seconds to wait between processing
                                    status checks. Defaults to 10.

    Returns:
        str: Generated summary text of the audio content

    Raises:
        ValueError: If the audio file processing fails

    Note:
        The function automatically cleans up by deleting the uploaded file
        after processing.

    """
    prompt = BASIC_PROMPT_FOR_FILE
    # Deprecated since version 3.13 Use guess_file_type() for this.
    mime_type, _ = mimetypes.guess_type(file)
    try:
        audio_file = genai.upload_file(path=file, mime_type=mime_type)
    except SSLEOFError as e:
        raise requests.exceptions.ConnectionError from e  # to activate the retry
    while audio_file.state.name == "PROCESSING":
        time.sleep(sleep_time)
    if audio_file.state.name == "FAILED":
        raise ValueError(audio_file.state.name)
    check_quota(quantity=1)
    response = gemini_pro_model.generate_content(
        [prompt, audio_file],
        stream=False,
        request_options={"timeout": 120},
    )
    audio_file.delete()
    return response.text


def summarize_with_transcript(transcript: str) -> str:
    """Generate a summary of a transcript using the Gemini Pro model.

    This function takes a transcript text, combines it with a predefined prompt,
    and uses the Gemini Pro model to generate a summary of the content.

    Args:
        transcript (str): The transcript text to be summarized

    Returns:
        str: Generated summary of the transcript content

    Note:
        - Uses prompt template for consistent summarization
        - Checks quota before making the API call
        - Has a 120-second timeout for the API request

    """
    prompt = dedent(f"{BASIC_PROMPT_FOR_TRANSCRIPT} {transcript}").strip()
    check_quota(quantity=1)
    response = gemini_pro_model.generate_content(
        prompt,
        stream=False,
        request_options={"timeout": 120},
    )
    return response.text


def summarize_webpage(content: str) -> str:
    """Generate a summary of webpage content using the Gemini Pro model.

    This function takes webpage content, combines it with a predefined prompt,
    and uses the Gemini Pro model to generate a summary of the content.

    Args:
        content (str): The webpage content to be summarized

    Returns:
        str: Generated summary of the webpage content

    Note:
        - Uses prompt template for consistent summarization
        - Checks quota before making the API call
        - Has a 120-second timeout for the API request

    """
    prompt = f"{BASIC_PROMPT_FOR_WEBPAGE} {content}"
    check_quota(quantity=1)
    response = gemini_pro_model.generate_content(
        prompt,
        stream=False,
        request_options={"timeout": 120},
    )
    return response.text


def summarize(
    data: str | File,
    use_transcription: bool,
    use_yt_transcription: bool = False,
) -> str:
    """Summarize content from various sources using Gemini Pro model.

    This function handles multiple types of inputs (URL or files) and attempts
    different summarization strategies based on the input type and configuration.

    Args:
        data (str | File): Input data to summarize. Can be:
            - YouTube URL
            - Castro.fm episode URL
            - Telegram File object
        use_transcription (bool): Whether to fall back to transcription-based
                                  summarization if direct file summarization fails
        use_yt_transcription (bool, optional): Whether to use YouTube's transcript
                                               for YouTube videos.

    Returns:
        str: Generated summary of the content, prefixed with:
            - 📹 for YouTube transcript summaries
            - 📝 for fallback transcription summaries
            - No prefix for direct file summaries

    Note:
        - Automatically cleans up downloaded/temporary files
        - Falls back to transcription-based summarization if configured
        - Handles various error cases with appropriate logging

    """
    if isinstance(data, str):
        if data.startswith("https://castro.fm/episode/"):
            data = download_castro(data)
        if data.startswith(("https://youtu.be/", "https://www.youtube.com/")):
            if use_yt_transcription:
                try:
                    transcript = get_yt_transcript(data)
                    return dedent(f"""📹
                                {summarize_with_transcript(transcript)}""").strip()
                except (
                    TranscriptsDisabled,
                    NoTranscriptAvailable,
                    exceptions.ResourceExhausted,
                    exceptions.InternalServerError,
                ):
                    pass
            data = download_yt(data)
    if isinstance(data, File):
        data = download_tg(data)

    try:
        return summarize_with_file(data)
    except (exceptions.RetryError, TimeoutError, exceptions.DeadlineExceeded) as e:
        logger.warning(f"Error occurred while summarizing with file: {e}")
        if use_transcription:
            new_file = generate_temporary_name(ext=".ogg")
            compress_audio(input_file=data, output_file=new_file)
            try:
                transcription = transcribe(new_file)
                return dedent(f"""📝
                            {summarize_with_transcript(transcription)}""").strip()
            finally:
                clean_up(file=new_file)
        capture_exception(e)
        raise
    finally:
        clean_up(file=data)
