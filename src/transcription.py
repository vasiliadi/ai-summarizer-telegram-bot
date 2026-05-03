import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from defusedxml.ElementTree import ParseError
from replicate.exceptions import ModelError, ReplicateError
from requests.exceptions import ChunkedEncodingError, ProxyError, SSLError
from tenacity import (
    RetryError,
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
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from config import PROXY, replicate_client
from utils import clean_up, generate_temporary_name, vtt_to_text

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
    retry=retry_if_exception_type((ParseError, IpBlocked, RequestBlocked)),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def fetch_transcript_via_api(video_id: str) -> str:
    """Retrieve and format a YouTube transcript via youtube_transcript_api.

    Args:
        video_id (str): The YouTube video ID.

    Returns:
        str: The formatted transcript text.

    Raises:
        NoTranscriptFound: If no transcript is found in any language.
        RetryError: If IpBlocked, RequestBlocked, or ParseError persist after retries.

    """
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


def fetch_transcript_via_ytdlp(url: str) -> str:
    """Retrieve a YouTube transcript by downloading subtitles via yt-dlp.

    Tries English subtitles first (manual then auto-generated), then falls
    back to any available language. Always uses PROXY when configured.

    Args:
        url (str): The YouTube video URL.

    Returns:
        str: The transcript as plain text.

    Raises:
        DownloadError: If no subtitles are available or yt-dlp cannot fetch them.

    """
    temp_basename = generate_temporary_name()
    ydl_opts: dict[str, object] = {
        "proxy": PROXY,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en.*", "en"],
        "subtitlesformat": "vtt",
        "outtmpl": temp_basename,
        "quiet": True,
        "nocheckcertificate": False,
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    vtt_files = list(Path.cwd().glob(f"{temp_basename}.*.vtt"))

    if not vtt_files:
        ydl_opts_all = {**ydl_opts, "subtitleslangs": ["all"]}
        with YoutubeDL(ydl_opts_all) as ydl:
            ydl.extract_info(url, download=True)
        vtt_files = list(Path.cwd().glob(f"{temp_basename}.*.vtt"))

    if not vtt_files:
        msg = "No subtitles available via yt-dlp"
        raise DownloadError(msg)

    vtt_path = vtt_files[0]
    try:
        return vtt_to_text(vtt_path)
    finally:
        for f in vtt_files:
            clean_up(file=str(f))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(
        (
            ProxyError,
            SSLError,
            ChunkedEncodingError,
        ),
    ),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def get_yt_transcript(url: str) -> str:
    """Retrieve and format the transcript from a YouTube video URL.

    Tries youtube_transcript_api first. If blocked or unavailable, falls
    back to yt-dlp subtitle download. Transient network errors are retried
    up to 3 times before raising RetryError.

    Args:
        url (str): The YouTube video URL.

    Returns:
        str: The formatted transcript text from the video.

    Raises:
        ValueError: If the URL format is not recognized.
        DownloadError: If both the API and yt-dlp fallback fail to retrieve subtitles.
        RetryError: If proxy/SSL/network errors persist after all retry attempts.

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

    try:
        return fetch_transcript_via_api(video_id)
    except (NoTranscriptFound, RetryError) as api_err:
        logger.warning(
            "youtube_transcript_api failed (%s); trying yt-dlp fallback",
            api_err,
        )
        return fetch_transcript_via_ytdlp(url)
