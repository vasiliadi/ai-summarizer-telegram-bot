import time
from textwrap import dedent

import google.generativeai as genai
from google.api_core import exceptions
from sentry_sdk import capture_exception
from youtube_transcript_api._errors import NoTranscriptAvailable, TranscriptsDisabled

from config import gemini_pro_model
from download import download_castro, download_yt
from transcription import get_yt_transcript, transcribe
from utils import compress_audio, generate_temporary_name


# @retry.Retry(predicate=retry.if_transient_error)
def summarize_with_file(file: str, sleep_time: int = 10) -> str:
    prompt = "Listen carefully to the following audio file. Provide a detailed summary."
    audio_file = genai.upload_file(path=file)
    while audio_file.state.name == "PROCESSING":
        time.sleep(sleep_time)
    if audio_file.state.name == "FAILED":
        raise ValueError(audio_file.state.name)
    response = gemini_pro_model.generate_content(
        [prompt, audio_file],
        stream=False,
        request_options={"timeout": 120},
    )
    audio_file.delete()
    return response.text


def summarize_with_transcript(transcript: str) -> str:
    prompt = (
        f"Read carefully transcription and provide a detailed summary: {transcript}"
    )
    response = gemini_pro_model.generate_content(
        prompt,
        stream=False,
        request_options={"timeout": 120},
    )
    return response.text


def summarize_webpage(content: str) -> str:
    prompt = f"Read carefully webpage content and provide a detailed summary: {content}"
    response = gemini_pro_model.generate_content(
        prompt,
        stream=False,
        request_options={"timeout": 120},
    )
    return response.text


def summarize(data: str, use_transcription: bool, use_yt_transcription: bool) -> str:
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

    try:
        return summarize_with_file(data)
    except (exceptions.RetryError, TimeoutError, exceptions.DeadlineExceeded) as e:
        if use_transcription:
            new_file = f"{generate_temporary_name().split('.', maxsplit=1)[0]}.ogg"
            compress_audio(input_file=data, output_file=new_file)
            transcription = transcribe(new_file)
            return dedent(f"""📝
                          {summarize_with_transcript(transcription)}""").strip()
        capture_exception(e)
        raise
