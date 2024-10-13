import time

import google.generativeai as genai
from google.api_core import retry, exceptions

from config import gemini_pro_model
from transcription import transcribe, get_yt_transcript
from utils import generate_temprorary_name, compress_audio
from download import download_castro, download_yt


@retry.Retry(predicate=retry.if_transient_error)
def summarize_with_file(file, sleep_time=10):
    prompt = "Listen carefully to the following audio file. Provide a detailed summary."
    audio_file = genai.upload_file(path=file)
    while audio_file.state.name == "PROCESSING":
        time.sleep(sleep_time)
    if audio_file.state.name == "FAILED":
        raise ValueError(audio_file.state.name)
    response = gemini_pro_model.generate_content(
        [prompt, audio_file], stream=False, request_options={"timeout": 120}
    )
    audio_file.delete()
    return response.text


@retry.Retry(predicate=retry.if_transient_error)
def summarize_with_transcription(transcription):
    prompt = (
        f"Read carefully transcription and provide a detailed summary: {transcription}"
    )
    response = gemini_pro_model.generate_content(
        prompt, stream=False, request_options={"timeout": 120}
    )
    return response.text


def summarize(data, use_transcription, use_yt_transcription):

    if data.startswith("https://castro.fm/episode/"):
        data = download_castro(data)

    if data.startswith("https://youtu.be/") or data.startswith(
        "https://www.youtube.com/"
    ):
        if use_yt_transcription:
            try:
                transcription = get_yt_transcript(data)
                return f"**Summarized with YT transcription:** {summarize_with_transcription(transcription)}"
            except:
                pass
        data = download_yt(data)

    try:
        return summarize_with_file(data)
    except (exceptions.RetryError, TimeoutError, exceptions.DeadlineExceeded):
        if use_transcription:
            new_file = f"{generate_temprorary_name().split('.')[0]}.ogg"
            compress_audio(input_file=data, output_file=new_file)
            transcription = transcribe(new_file)
            return f"**Summarized with transcription:** {summarize_with_transcription(transcription)}"
