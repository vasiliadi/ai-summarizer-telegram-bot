import logging
import time
from pathlib import Path

from replicate.exceptions import ModelError
from requests.exceptions import ChunkedEncodingError, ProxyError, SSLError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound
from youtube_transcript_api.formatters import TextFormatter
from youtube_transcript_api.proxies import GenericProxyConfig

from config import PROXY, replicate_client

logger = logging.getLogger(__name__)


def transcribe(file: str, sleep_time: int = 10) -> str:
    """Transcribe an audio file using the Incredibly Fast Whisper model.

    Args:
        file (str): Path to the audio file to transcribe.
        sleep_time (int, optional): Time in seconds to wait between status checks.

    Returns:
        str: The transcribed text from the audio file.

    Raises:
        ModelError: If the transcription fails or is canceled.

    """
    model = replicate_client.models.get("vaibhavs10/incredibly-fast-whisper")
    version = model.versions.get(model.versions.list()[0].id)
    with Path(file).open("rb") as audio:
        prediction = replicate_client.predictions.create(
            version=version,
            input={"audio": audio},
        )
    while prediction.status != "succeeded":
        if prediction.status in ("failed", "canceled"):
            msg = "File can't be transcribed"
            raise ModelError(msg)
        prediction.reload()
        time.sleep(sleep_time)
    return prediction.output["text"]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(
        (ProxyError, SSLError, ChunkedEncodingError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def get_yt_transcript(url: str) -> str:
    """Retrieve and format the transcript from a YouTube video URL.

    Args:
        url (str): The YouTube video URL.

    Returns:
        str: The formatted transcript text from the video.

    """
    if url.startswith("https://www.youtube.com/watch"):
        video_id = url.replace("https://www.youtube.com/watch?v=", "")
    elif url.startswith("https://youtu.be/"):
        video_id = url.replace("https://youtu.be/", "")
    elif url.startswith("https://www.youtube.com/live/"):
        video_id = url.replace("https://www.youtube.com/live/", "")
    else:
        msg = "Unknown URL"
        raise ValueError(msg)

    ytt_api = YouTubeTranscriptApi(proxy_config=GenericProxyConfig(https_url=PROXY))

    try:
        transcript = ytt_api.fetch(video_id)
    except NoTranscriptFound:
        transcript_list = ytt_api.list(video_id)
        language_codes = [transcript.language_code for transcript in transcript_list]
        transcript = ytt_api.fetch(video_id, languages=language_codes)
    return TextFormatter().format_transcript(transcript)
