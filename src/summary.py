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
                    I need you to analyze and summarize a YouTube video transcript using the SOAP method.
                    Please note that this transcript may contain speech recognition errors, inconsistent punctuation, non-verbal markers [music], [laughing], etc., and informal spoken language.
                    Please analyze and summarize the content following this structure:

                    Subjective (S)

                    Presenter's stated opinions and beliefs
                    Personal experiences shared
                    Emotional responses or reactions described
                    Attitudes expressed towards the topic
                    Hypothetical scenarios presented
                    Arguments based on personal perspective
                    User/customer testimonials mentioned
                    Perceived challenges or opportunities discussed

                    Objective (O)

                    Factual information presented (5-10 key points)
                    Verifiable data and statistics
                    Research findings or studies cited
                    Historical events referenced
                    Technical specifications or processes explained
                    Industry standards mentioned
                    Market data or trends presented
                    Expert quotes or citations (cleaned up from transcript errors)
                    Measurable outcomes discussed

                    Assessment (A)
                    Analyze the relationship between subjective and objective elements:

                    How does the presenter use data to support their opinions?
                    What connections are made between personal experience and factual evidence?
                    Which arguments are supported by strong evidence vs. personal belief?
                    What patterns emerge from combining subjective and objective information?
                    How do examples and case studies reinforce the main points?
                    What gaps exist between opinions and available data?
                    How do different perspectives contribute to the overall message?

                    Plan (P)
                    Organize the information into a coherent narrative:

                    Main conclusion or key takeaway
                    Primary supporting arguments (minimum 5)
                    Practical applications or recommendations
                    Next steps or action items suggested
                    Resources or tools recommended
                    Future implications discussed
                    Call-to-action or key learnings emphasized

                    Notes on handling transcript issues:

                    Clean up obvious speech recognition errors when meaning is clear from context
                    Ignore non-verbal markers unless relevant to content meaning
                    If a section is unclear due to transcript quality, note "Potential transcript gap" and continue with next clear segment
                    Convert casual spoken language into professional writing while maintaining original meaning

                    Present all information in clear, professional language, organizing complex ideas into digestible segments while preserving important details and relationships.

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
