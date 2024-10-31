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
                    I need you to analyze and summarize a YouTube video transcript that I'll provide. Please note that this transcript may have several challenges:

                    1. Speech recognition errors and misheard words
                    2. Limited or inconsistent punctuation
                    3. Non-verbal elements marked as [music], [laughing], [applause], etc.
                    4. Informal spoken language and filler words
                    5. Potential time stamps or speaker labels

                    Please provide a comprehensive summary following this structure:

                    Main Topic
                    - State the primary subject matter or theme of the video (2-3 sentences)

                    Key Points
                    - List 3-5 main arguments, ideas, or topics discussed
                    - Include relevant details or examples mentioned
                    - Ignore speech recognition errors unless they significantly impact meaning

                    Important Details
                    - Notable quotes or statements (clean up obvious speech recognition errors)
                    - Specific data, numbers, or statistics mentioned
                    - Key examples or case studies discussed
                    - Any resources or references cited

                    Structure and Flow
                    - How the content is organized
                    - Any significant transitions or shifts in topics
                    - Relationship between different segments

                    Technical Notes
                    - Note any parts where technical issues (audio quality, recognition errors) might have affected comprehension
                    - Flag any sections where meaning is unclear due to transcript quality

                    Please clean up obvious speech recognition errors when they can be understood from context, and note any sections where errors make the meaning unclear. Ignore non-verbal markers like [music] unless they're relevant to the content structure.

                    If you notice any patterns of errors or unclear sections, please mention them at the end of the summary.

                    Present the information in clear, professional language, converting casual spoken language into more formal written expression while maintaining the original meaning.

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
