import logging
import mimetypes
import time
from textwrap import dedent

import google.generativeai as genai
from google.api_core import exceptions, retry
from sentry_sdk import capture_exception
from telebot.types import File
from youtube_transcript_api._errors import NoTranscriptAvailable, TranscriptsDisabled

from config import NUMERIC_LOG_LEVEL, gemini_pro_model
from download import download_castro, download_tg, download_yt
from prompts import (
    BASIC_PROMPT_FOR_FILE,
    BASIC_PROMPT_FOR_TRANSCRIPT,
    BASIC_PROMPT_FOR_WEBPAGE,
)
from services import check_quota
from transcription import get_yt_transcript, transcribe
from utils import clean_up, compress_audio, generate_temporary_name

logging.basicConfig(
    level=NUMERIC_LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@retry.Retry(predicate=retry.if_transient_error, initial=30, timeout=300)
def summarize_with_file(file: str, sleep_time: int = 10) -> str:
    prompt = BASIC_PROMPT_FOR_FILE
    # Deprecated since version 3.13 Use guess_file_type() for this.
    mime_type = mimetypes.guess_type(file)[0]
    audio_file = genai.upload_file(path=file, mime_type=mime_type)
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
    prompt = dedent(f"{BASIC_PROMPT_FOR_TRANSCRIPT} {transcript}").strip()
    check_quota(quantity=1)
    response = gemini_pro_model.generate_content(
        prompt,
        stream=False,
        request_options={"timeout": 120},
    )
    return response.text


def summarize_webpage(content: str) -> str:
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
        logger.warning("Error occurred while summarizing with file: %s", e)
        if use_transcription:
            new_file = f"{generate_temporary_name().split('.', maxsplit=1)[0]}.ogg"
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
