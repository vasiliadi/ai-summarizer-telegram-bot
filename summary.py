import time

import google.generativeai as genai
from google.api_core import retry, exceptions

from config import gemini_pro_model
from transcription import transcribe
from utils import generate_temprorary_name, compress_audio, clean_up


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


def summarize(file, use_transcription):
    try:
        return summarize_with_file(file)
    except (exceptions.RetryError, TimeoutError, exceptions.DeadlineExceeded):
        if use_transcription:
            new_file = f"{generate_temprorary_name().split('.')[0]}.ogg"
            compress_audio(input_file=file, output_file=new_file)
            transcription = transcribe(new_file)
            clean_up(new_file)
            # return summarize_with_transcription(transcription)
            return f"**Summarized with transcription:** {summarize_with_transcription(transcription)}"
        raise Exception("Something went wrong, try again.")
