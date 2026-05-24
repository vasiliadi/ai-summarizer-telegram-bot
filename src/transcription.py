from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from defusedxml.ElementTree import ParseError
from replicate.exceptions import ModelError, ReplicateError
from requests.exceptions import ChunkedEncodingError, ProxyError, SSLError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
)
from youtube_transcript_api.formatters import TextFormatter
from youtube_transcript_api.proxies import GenericProxyConfig
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from config import replicate_client
from utils import (
    clean_up,
    extract_youtube_video_id,
    generate_temporary_name,
    get_proxy,
    vtt_to_text,
)

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
    version = model.versions.list()[0]
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
    stop=stop_after_attempt(2),
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
        CouldNotRetrieveTranscript: Subclasses (TranscriptsDisabled, VideoUnavailable,
            AgeRestricted, etc.) propagate to the caller.
        RetryError: If IpBlocked, RequestBlocked, or ParseError persist after retries.

    """
    proxy = get_proxy()
    if proxy:
        ytt_api = YouTubeTranscriptApi(proxy_config=GenericProxyConfig(https_url=proxy))
    else:
        ytt_api = YouTubeTranscriptApi()

    try:
        transcript = ytt_api.fetch(video_id)
    except NoTranscriptFound:
        transcript_list = ytt_api.list(video_id)
        language_codes = [transcript.language_code for transcript in transcript_list]
        time.sleep(60)
        transcript = ytt_api.fetch(video_id, languages=language_codes)
    return TextFormatter().format_transcript(transcript)


def fetch_transcript_via_ytdlp(url: str) -> str:
    """Retrieve a YouTube transcript by downloading subtitles via yt-dlp.

    Probes available tracks first, prefers English, converts to vtt via ffmpeg.

    Args:
        url (str): The YouTube video URL.

    Returns:
        str: The transcript as plain text.

    Raises:
        DownloadError: If no subtitles are available or yt-dlp cannot fetch them.

    """
    temp_basename = generate_temporary_name()
    proxy = get_proxy()
    probe_opts: dict[str, Any] = {
        "proxy": proxy,
        "noplaylist": True,
        "skip_download": True,
        "quiet": True,
        "nocheckcertificate": False,
    }

    # Phase 1: probe available subtitle tracks (no download, no temp files written).
    try:
        with YoutubeDL(probe_opts) as ydl:  # pyrefly: ignore[bad-argument-type]
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        logger.warning("yt-dlp probe failed: %s: %s", type(e).__name__, e)
        raise
    except Exception as e:
        logger.warning("yt-dlp probe failed unexpectedly: %s: %s", type(e).__name__, e)
        msg = "yt-dlp probe failed"
        raise DownloadError(msg) from e

    if info is None:
        msg = "No subtitles available via yt-dlp"
        raise DownloadError(msg)

    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    available = list(dict.fromkeys([*manual.keys(), *auto.keys()]))

    if not available:
        msg = "No subtitles available via yt-dlp"
        raise DownloadError(msg)

    has_english = any(lang.startswith("en") for lang in available)
    chosen_langs = ["en.*"] if has_english else [available[0]]

    ydl_opts: dict[str, Any] = {
        "proxy": proxy,
        "noplaylist": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": chosen_langs,
        "subtitlesformat": "vtt/best",
        "postprocessors": [
            {
                "key": "FFmpegSubtitlesConvertor",
                "format": "vtt",
                "when": "before_dl",
            },
        ],
        "outtmpl": temp_basename,
        "quiet": True,
        "nocheckcertificate": False,
    }

    # Phase 2: download and convert subtitles.
    try:
        with YoutubeDL(ydl_opts) as ydl:  # pyrefly: ignore[bad-argument-type]
            ydl.download([url])

        vtt_files = list(Path.cwd().glob(f"{temp_basename}.*.vtt"))

        if not vtt_files:
            msg = "No subtitles available via yt-dlp"
            raise DownloadError(msg)  # noqa: TRY301

        return vtt_to_text(sorted(vtt_files)[0])
    except DownloadError as e:
        logger.warning("yt-dlp subtitle fetch failed: %s: %s", type(e).__name__, e)
        raise
    except Exception as e:
        logger.warning(
            "yt-dlp subtitle fetch failed unexpectedly: %s: %s",
            type(e).__name__,
            e,
        )
        msg = "yt-dlp subtitle fetch failed"
        raise DownloadError(msg) from e
    finally:
        for f in Path.cwd().glob(f"{temp_basename}.*"):
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
def get_yt_transcript(url: str, source: str) -> str:
    """Retrieve and format the transcript from a YouTube video URL.

    Dispatches to a single transcript backend based on `source`; there is no
    fallback between backends. Transient transport errors (proxy/SSL/network)
    are retried up to 3 times before raising RetryError.

    Args:
        url (str): The YouTube video URL.
        source (str): Transcript backend to use. Either "api"
            (youtube_transcript_api) or "ytdlp" (yt-dlp subtitle download).

    Returns:
        str: The formatted transcript text from the video.

    Raises:
        ValueError: If the URL format is not recognized, or if `source` is not
            a known backend.
        NoTranscriptFound: If the API backend cannot find a transcript.
        CouldNotRetrieveTranscript: Subclasses raised by the API backend
            (TranscriptsDisabled, VideoUnavailable, AgeRestricted, etc.).
        DownloadError: If the yt-dlp backend cannot fetch subtitles.
        RetryError: If proxy/SSL/network errors persist after all retry attempts,
            or if API-internal retries (IpBlocked/RequestBlocked/ParseError) are
            exhausted.

    """
    video_id = extract_youtube_video_id(url)
    if video_id is None:
        msg = "Unknown URL"
        raise ValueError(msg)

    if source == "api":
        return fetch_transcript_via_api(video_id)
    if source == "ytdlp":
        return fetch_transcript_via_ytdlp(url)
    msg = f"Unknown transcript source: {source}"
    raise ValueError(msg)
