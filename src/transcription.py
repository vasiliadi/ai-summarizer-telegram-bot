import time

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from youtube_transcript_api._errors import NoTranscriptFound

from config import replicate_client, PROXY


def transcribe(file: str, sleep_time: int = 10) -> str:
    model = replicate_client.models.get("vaibhavs10/incredibly-fast-whisper")
    version = model.versions.get(model.versions.list()[0].id)
    with open(file, "rb") as audio:
        prediction = replicate_client.predictions.create(
            version=version, input={"audio": audio}
        )
    while prediction.status != "succeeded":
        if prediction.status == "failed" or prediction.status == "canceled":
            raise Exception("File can't be transcribed")
        prediction.reload()
        time.sleep(sleep_time)
    return prediction.output["text"]


def get_yt_transcript(url: str) -> str:
    if url.startswith("https://www.youtube.com/"):
        video_id = url.replace("https://www.youtube.com/watch?v=", "")
    elif url.startswith("https://youtu.be/"):
        video_id = url.replace("https://youtu.be/", "")
    else:
        raise ValueError("Unknown URL")

    try:
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id, proxies={"https": PROXY}
        )
    except NoTranscriptFound:
        transcript_list = YouTubeTranscriptApi.list_transcripts(
            video_id, proxies={"https": PROXY}
        )
        language_codes = [transcript.language_code for transcript in transcript_list]
        transcript = transcript_list.find_transcript(language_codes).fetch()
    transcript = TextFormatter().format_transcript(transcript)
    return transcript
