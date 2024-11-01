import time
from textwrap import dedent

import google.generativeai as genai
from google.api_core import exceptions, retry
from sentry_sdk import capture_exception
from youtube_transcript_api._errors import NoTranscriptAvailable, TranscriptsDisabled

from config import gemini_pro_model
from download import download_castro, download_yt
from transcription import get_yt_transcript, transcribe
from utils import compress_audio, generate_temporary_name


@retry.Retry(predicate=retry.if_transient_error, initial=10, timeout=120)
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
    prompt = dedent(f"""
                    I need you to analyze and summarize a YouTube video transcript using the Pyramid Method.
                    Please note that this transcript may contain speech recognition errors, inconsistent punctuation, non-verbal markers [music], [laughing], etc., and informal spoken language.
                    Please provide a structured summary following this hierarchy:

                    Core Message (Top of Pyramid)

                    Provide the single most important takeaway or main conclusion (1-2 sentences)
                    What's the fundamental message or purpose of this video?

                    Primary Arguments (Second Layer)

                    List 5-10 key arguments or major points that support the core message
                    Present these in order of importance
                    Connect each point to the core message
                    Clean up any obvious speech recognition errors

                    Supporting Evidence (Third Layer)

                    For each primary argument, provide:

                    Relevant data or statistics
                    Notable quotes (cleaned up for clarity)
                    Specific examples or case studies
                    Expert opinions or references cited
                    Real-world applications mentioned

                    Contextual Details (Base Layer)

                    Background information provided
                    Definitions or explanations of key terms
                    Historical context or industry trends mentioned
                    Related concepts or parallel examples
                    Tools, resources, or recommendations shared

                    Notes on handling transcript issues:

                    Ignore non-verbal markers ([music], [applause], etc.) unless content-relevant
                    Clean up obvious speech recognition errors when meaning is clear from context
                    If a section is unclear due to transcript quality, note "Potential transcript gap" and continue with next clear segment
                    Convert casual spoken language into clear, professional writing while preserving original meaning

                    Present all information in professional language, maintaining accuracy while improving clarity and readability.

                    Here is transcript: {transcript}
                    """).strip()  # noqa: E501
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
