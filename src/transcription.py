import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from defusedxml.ElementTree import ParseError
from replicate.exceptions import ModelError, ReplicateError
from requests.exceptions import ChunkedEncodingError, ProxyError, SSLError
from tenacity import (
    _utils as tenacity_utils,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import IpBlocked, NoTranscriptFound, RequestBlocked
from youtube_transcript_api.formatters import TextFormatter
from youtube_transcript_api.proxies import GenericProxyConfig

from config import PROXY, replicate_client

if TYPE_CHECKING:
    from tenacity import (
        _utils as tenacity_utils,
    )

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(ReplicateError),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def transcribe(file: str, sleep_time: int = 10) -> str:
    """Transcribe an audio file using WhisperX model.

    Args:
        file (str): Path to the audio file to transcribe.
        sleep_time (int, optional): Time in seconds to wait between status checks.

    Returns:
        str: The transcribed text from the audio file.

    Raises:
        ModelError: If the transcription fails, is canceled, or output is invalid.
        RetryError: If Replicate errors persist after all retry attempts.

    """
    model = replicate_client.models.get("victor-upmeet/whisperx")
    version = model.versions.get(model.versions.list()[0].id)
    with Path(file).open("rb") as audio:
        prediction = replicate_client.predictions.create(
            version=version,
            input={"audio_file": audio},
        )
    while prediction.status != "succeeded":
        if prediction.status in ("failed", "canceled"):
            raise ModelError(prediction)
        prediction.reload()
        time.sleep(sleep_time)
    if prediction.output is None:
        raise ModelError(prediction)
    segments = prediction.output.get("segments")
    if not isinstance(segments, list):
        raise ModelError(prediction)
    return "".join(
        [segment.get("text", "") for segment in segments if isinstance(segment, dict)],
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(
        (
            ProxyError,
            SSLError,
            ChunkedEncodingError,
            ParseError,
            IpBlocked,
            RequestBlocked,
        ),
    ),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def get_yt_transcript(url: str) -> str:
    """Retrieve and format the transcript from a YouTube video URL.

    Args:
        url (str): The YouTube video URL.

    Returns:
        str: The formatted transcript text from the video.

    Raises:
        ValueError: If the URL format is not recognized.
        RetryError: If proxy/SSL/XML errors persist after retries.

    """
    if url.startswith("https://www.youtube.com/watch"):
        video_id = url.replace("https://www.youtube.com/watch?v=", "").split("?")[0]
    elif url.startswith("https://youtube.com/watch"):
        video_id = url.replace("https://youtube.com/watch?v=", "").split("?")[0]
    elif url.startswith("https://youtu.be/"):
        video_id = url.replace("https://youtu.be/", "").split("?")[0]
    elif url.startswith("https://www.youtube.com/live/"):
        video_id = url.replace("https://www.youtube.com/live/", "").split("?")[0]
    else:
        msg = "Unknown URL"
        raise ValueError(msg)

    if PROXY:
        ytt_api = YouTubeTranscriptApi(proxy_config=GenericProxyConfig(https_url=PROXY))
    else:
        ytt_api = YouTubeTranscriptApi()

    try:
        transcript = ytt_api.fetch(video_id)
    except NoTranscriptFound:
        transcript_list = ytt_api.list(video_id)
        language_codes = [transcript.language_code for transcript in transcript_list]
        transcript = ytt_api.fetch(video_id, languages=language_codes)
    return TextFormatter().format_transcript(transcript)
