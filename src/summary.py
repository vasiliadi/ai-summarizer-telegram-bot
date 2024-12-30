import logging
import time
from ssl import SSLEOFError
from textwrap import dedent

from google.genai import types
from google.genai.errors import ServerError
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
from prompts import PROMPTS
from services import check_quota
from transcription import get_yt_transcript, transcribe
from utils import clean_up, compress_audio, generate_temporary_name

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(
        (SSLEOFError, ServerError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def summarize_with_file(
    file: str,
    model: str,
    prompt_key: str,
    sleep_time: int = 10,
) -> str:
    """Summarize audio content using Gemini API with file upload.

    This function uploads an audio file to Gemini, waits for processing,
    and generates a summary using the specified model and prompt.

    Args:
        file (str): Path to the audio file to be summarized
        model (str): The Gemini model identifier to use for generation
        prompt_key (str): Key to retrieve the prompt template from PROMPTS
        sleep_time (int, optional): Time between processing checks. Defaults to 10.

    Returns:
        str: Generated summary text from the audio content

    Note:
        This function is decorated with @retry and will attempt the operation
        up to 3 times with a 30-second wait between attempts.

    """
    prompt = dedent(PROMPTS[prompt_key]).strip()
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
                    types.Part.from_text(prompt),
                    types.Part.from_uri(
                        file_uri=audio_file.uri,
                        mime_type=audio_file.mime_type,
                    ),
                ],
            ),
        ],
        config=GEMINI_CONFIG,
    )
    gemini_client.files.delete(name=audio_file.name)
    return response.text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(
        (ServerError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def summarize_with_transcript(transcript: str, model: str, prompt_key: str) -> str:
    """Generate a summary from a transcript using Gemini API.

    This function takes a transcript text, combines it with a predefined prompt
    template, and uses the Gemini API to generate a summary.

    Args:
        transcript (str): The text transcript to be summarized
        model (str): The Gemini model identifier to use for generation
        prompt_key (str): Key to retrieve the prompt template from PROMPTS

    Returns:
        str: Generated summary text from the transcript

    Note:
        The function checks quota usage before making the API call and uses
        GEMINI_CONFIG for model configuration.

    """
    prompt = (f"{dedent(PROMPTS[prompt_key])} {transcript}").strip()
    check_quota(quantity=1)
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=GEMINI_CONFIG,
    )
    return response.text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(
        (ServerError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def summarize_webpage(content: str, model: str, prompt_key: str) -> str:
    """Generate a summary from webpage content using Gemini API.

    This function takes webpage content, combines it with a predefined prompt template,
    and uses the Gemini API to generate a summary.

    Args:
        content (str): The webpage content to be summarized
        model (str): The Gemini model identifier to use for generation
        prompt_key (str): Key to retrieve the prompt template from PROMPTS

    Returns:
        str: Generated summary text from the webpage content

    Note:
        The function checks quota usage before making the API call and uses
        GEMINI_CONFIG for model configuration.

    """
    prompt = (f"{dedent(PROMPTS[prompt_key])} {content}").strip()
    check_quota(quantity=1)
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=GEMINI_CONFIG,
    )
    return response.text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(
        (ServerError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def summarize_with_document(
    file: str,
    model: str,
    prompt_key: str,
    mime_type: str,
    sleep_time: int = 10,
) -> str:
    """Summarize document content using Gemini API with file upload.

    This function downloads a document from Telegram, uploads it to Gemini,
    waits for processing, and generates a summary using the specified model
    and prompt.

    Args:
        file (str): Path or identifier of the document to be summarized
        model (str): The Gemini model identifier to use for generation
        prompt_key (str): Key to retrieve the prompt template from PROMPTS
        mime_type (str): MIME type of the document being uploaded
        sleep_time (int, optional): Time between processing checks. Defaults to 10.

    Returns:
        str: Generated summary text from the document content

    Raises:
        ValueError: If the document processing fails on Gemini's side
        RetryError: If the operation fails after all retry attempts

    Note:
        - This function is decorated with @retry and will attempt the operation
          up to 3 times with a 30-second wait between attempts.
        - Temporary files are automatically cleaned up after processing.
        - The function checks quota usage before making the API call.

    """
    try:
        data = download_tg(file)
        prompt = dedent(PROMPTS[prompt_key]).strip()
        document_file = gemini_client.files.upload(
            path=data,
            config={"mime_type": mime_type},
        )
        while document_file.state == "PROCESSING":
            time.sleep(sleep_time)
            document_file = gemini_client.files.get(name=document_file.name)
        if document_file.state == "FAILED":
            raise ValueError(document_file.state)
        check_quota(quantity=1)
        response = gemini_client.models.generate_content(
            model=model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(prompt),
                        types.Part.from_uri(
                            file_uri=document_file.uri,
                            mime_type=document_file.mime_type,
                        ),
                    ],
                ),
            ],
            config=GEMINI_CONFIG,
        )
        gemini_client.files.delete(name=document_file.name)
    finally:
        clean_up(file=data)
    return response.text


def summarize(
    data: str | File,
    use_transcription: bool,
    model: str,
    prompt_key: str,
    use_yt_transcription: bool = False,
) -> str:
    """Generate a summary from various input sources using Gemini API.

    This function handles multiple input types (URLs, files, etc.) and attempts
    different summarization strategies based on the input and configuration.

    Args:
        data (str | File): Input data to summarize. Can be:
            - YouTube URL
            - Castro.fm episode URL
            - Telegram File object
        use_transcription (bool): Whether to fall back to transcription if direct
            summarization fails
        model (str): The Gemini model identifier to use for generation
        prompt_key (str): Key to retrieve the prompt template from PROMPTS
        use_yt_transcription (bool, optional): Whether to attempt using YouTube's
            built-in transcripts for YouTube URLs. Defaults to False.

    Returns:
        str: Generated summary of the content, prefixed with:
            - 📹 for YouTube transcript summaries
            - 📝 for fallback transcription summaries
            - No prefix for direct file summaries

    Raises:
        RetryError: If all summarization attempts fail after retries

    Note:
        The function follows this process:
        1. For URLs: Downloads content from YouTube or Castro.fm
        2. For YouTube: Attempts to use built-in transcripts if enabled
        3. For files: Attempts direct summarization
        4. On failure: Falls back to transcription if enabled
        5. Cleans up temporary files after processing

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
                                  {summarize_with_transcript(transcript=transcript,
                                                             model=model,
                                                             prompt_key=prompt_key)}
                                  """).strip()
                except (
                    TranscriptsDisabled,
                    NoTranscriptAvailable,
                    RetryError,
                ):
                    pass
            data = download_yt(data)
    if isinstance(data, File):
        data = download_tg(data, ext=".ogg")

    try:
        return summarize_with_file(file=data, model=model, prompt_key=prompt_key)
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
                              {summarize_with_transcript(transcript=transcription,
                                                         model=model,
                                                         prompt_key=prompt_key)}
                              """).strip()
            finally:
                clean_up(file=new_file)
        capture_exception(e)
        raise
    finally:
        clean_up(file=data)
