import time

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

from config import replicate_client, PROXY


def transcribe(file, sleep_time=10):
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


def get_yt_transcript(url):
    if url.startswith("https://www.youtube.com/"):
        video_id = url.replace("https://www.youtube.com/watch?v=", "")
    elif url.startswith("https://youtu.be/"):
        video_id = url.replace("https://youtu.be/", "")
    else:
        raise ValueError("Unknown URL")

    transcript = YouTubeTranscriptApi.get_transcript(video_id, proxies={"https": PROXY})
    transcript = TextFormatter().format_transcript(transcript)
    return transcript
