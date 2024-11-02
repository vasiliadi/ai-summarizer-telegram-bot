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
                    You are tasked with summarizing a YouTube video transcript. The transcript is provided below:

                    <transcript>
                    {transcript}
                    </transcript>

                    This task comes with several challenges:
                    1. The transcript may contain errors due to incorrect word recognition.
                    2. There might be a lack of proper punctuation.
                    3. The text is more akin to video subtitles than a formal transcript.
                    4. The transcript may include non-verbal cues like [music] or [laughing].

                    To create a detailed summary, follow these steps:

                    1. Preprocessing:
                    a. Remove non-verbal cues (e.g., [music], [laughing]) unless they are crucial to understanding the content.
                    b. Attempt to add appropriate punctuation where it's clearly missing.
                    c. Correct obvious word recognition errors based on context.

                    2. Content Analysis:
                    a. Identify the main topic or themes of the video.
                    b. Note key points, arguments, or information presented.
                    c. Recognize any significant examples, case studies, or anecdotes used.
                    d. Identify any conclusions or call-to-actions presented.

                    3. Summarization:
                    a. Provide a brief introduction (1-2 sentences) stating the main topic of the video.
                    b. Outline the key points in order of presentation, explaining each in 1-3 sentences.
                    c. Include any important examples or case studies that illustrate these points.
                    d. Summarize any conclusions or final thoughts presented in the video.
                    e. If applicable, mention any call-to-action or next steps suggested in the video.

                    4. Review:
                    a. Ensure the summary captures the essence of the video content.
                    b. Check that the summary flows logically and is easy to understand.
                    c. Verify that no crucial information has been omitted.

                    Present your summary in the following format:

                    <summary>
                    Title: [Inferred title of the video based on content]

                    Introduction: [1-2 sentences introducing the main topic]

                    Key Points:
                    1. [First key point]
                    2. [Second key point]
                    3. [Third key point]
                    ...

                    Examples/Case Studies: [If applicable, briefly mention significant examples]

                    Conclusion: [Summarize the video's conclusion or final thoughts]

                    Call-to-Action: [If applicable, mention any suggested next steps or actions]
                    </summary>

                    Remember to focus on providing a coherent and informative summary, even if the original transcript contains errors or is difficult to follow. Use your best judgment to interpret the content and present it in a clear, organized manner.
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
