import time
from pathlib import Path
from xml.etree.ElementTree import ParseError

from replicate.exceptions import ModelError
from requests.exceptions import ProxyError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound
from youtube_transcript_api.formatters import TextFormatter

from config import PROXY, replicate_client


def transcribe(file: str, sleep_time: int = 10) -> str:
    model = replicate_client.models.get("vaibhavs10/incredibly-fast-whisper")
    version = model.versions.get(model.versions.list()[0].id)
    with Path(file).open("rb") as audio:
        prediction = replicate_client.predictions.create(
            version=version,
            input={"audio": audio},
        )
    while prediction.status != "succeeded":
        if prediction.status in ("failed", "canceled"):
            raise ModelError("File can't be transcribed")
        prediction.reload()
        time.sleep(sleep_time)
    return prediction.output["text"]


@retry(
    wait=wait_fixed(10),
    retry=retry_if_exception_type((ProxyError, ParseError)),
    reraise=True,
    stop=stop_after_attempt(3),
)  # type: ignore[call-overload]
def get_yt_transcript(url: str) -> str:
    if url.startswith("https://www.youtube.com/watch"):
        video_id = url.replace("https://www.youtube.com/watch?v=", "")
    elif url.startswith("https://youtu.be/"):
        video_id = url.replace("https://youtu.be/", "")
    elif url.startswith("https://www.youtube.com/live/"):
        video_id = url.replace("https://www.youtube.com/live/", "")
    else:
        raise ValueError("Unknown URL")

    try:
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            proxies={"https": PROXY},
        )
    except NoTranscriptFound:
        transcript_list = YouTubeTranscriptApi.list_transcripts(
            video_id,
            proxies={"https": PROXY},
        )
        language_codes = [transcript.language_code for transcript in transcript_list]
        transcript = transcript_list.find_transcript(language_codes).fetch()
    return TextFormatter().format_transcript(transcript)
