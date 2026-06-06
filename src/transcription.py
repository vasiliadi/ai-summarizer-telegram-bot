from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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

from config import YT_TRANSCRIPT_SOURCE, replicate_client
from exceptions import (
    FetchTranscriptViaApiError,
    FetchTranscriptViaYtdlpError,
    TranscriptDownloadError,
)
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


@dataclass(frozen=True)
class TranscriptResult:
    """Transcript text with the display prefix for the source that succeeded."""

    text: str
    prefix: str


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
    retry=retry_if_exception_type(
        (
            ParseError,
            IpBlocked,
            RequestBlocked,
            ProxyError,
            SSLError,
            ChunkedEncodingError,
        ),
    ),
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
        RetryError: If IpBlocked, RequestBlocked, ParseError, ProxyError, SSLError,
            or ChunkedEncodingError persist after retries.

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


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(10),
    retry=retry_if_exception_type(TranscriptDownloadError),
    before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
    reraise=False,
)
def fetch_transcript_via_ytdlp(url: str) -> str:  # noqa: C901, PLR0912, PLR0915
    """Retrieve a YouTube transcript by downloading subtitles via yt-dlp.

    Probes available tracks first, preferring genuine manual subtitles (English
    when present) and otherwise the video's original-language automatic captions,
    then converts to vtt via ffmpeg.

    Args:
        url (str): The YouTube video URL.

    Returns:
        str: The transcript as plain text.

    Raises:
        DownloadError: If no subtitles are available for the video (sentinel
            paths: extract_info returned no data, no subtitle languages
            offered, or no vtt file appeared after download), or if vtt
            conversion/reading fails unexpectedly after a successful download.
        TranscriptDownloadError: Wraps transient yt-dlp failures from
            extract_info / download. Up to 2 total attempts (1 retry); on
            exhaustion tenacity raises RetryError to the caller.
        RetryError: If TranscriptDownloadError persists after all retries.

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
        raise TranscriptDownloadError(str(e)) from e
    except Exception as e:
        logger.warning("yt-dlp probe failed unexpectedly: %s: %s", type(e).__name__, e)
        msg = "yt-dlp probe failed"
        raise TranscriptDownloadError(msg) from e

    if info is None:
        msg = "No subtitles available via yt-dlp"
        raise DownloadError(msg)

    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    # yt-dlp lists "live_chat" under subtitles for live-stream replays; it is not a
    # real subtitle track and cannot be converted to vtt, so drop it.
    manual_langs = [lang for lang in manual if lang != "live_chat"]

    if manual_langs:
        # Human-uploaded tracks are genuine: prefer English, then the video's original
        # language, then the first offered key.
        en_manual = next((lang for lang in manual_langs if lang.startswith("en")), None)
        orig = info.get("language")
        chosen_langs = [
            en_manual or (orig if orig in manual_langs else manual_langs[0]),
        ]
    elif auto:
        # automatic_captions include machine translations for ~every language, so an
        # "en" key here is usually a translation, not a real track — request the
        # video's original language and let the summarizer translate.
        orig = info.get("language")
        if orig and orig in auto:
            chosen_langs = [orig]
        else:
            chosen_langs = [
                next(
                    (lang for lang in auto if lang.endswith("-orig")),
                    next(iter(auto)),
                ),
            ]
    else:
        msg = "No subtitles available via yt-dlp"
        raise DownloadError(msg)

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
        try:
            with YoutubeDL(ydl_opts) as ydl:  # pyrefly: ignore[bad-argument-type]
                ydl.download([url])
        except DownloadError as e:
            logger.warning(
                "yt-dlp subtitle fetch failed: %s: %s",
                type(e).__name__,
                e,
            )
            raise TranscriptDownloadError(str(e)) from e
        except Exception as e:
            logger.warning(
                "yt-dlp subtitle fetch failed unexpectedly: %s: %s",
                type(e).__name__,
                e,
            )
            msg = "yt-dlp subtitle fetch failed"
            raise TranscriptDownloadError(msg) from e

        vtt_files = list(Path.cwd().glob(f"{temp_basename}.*.vtt"))

        if not vtt_files:
            msg = "No subtitles available via yt-dlp"
            raise DownloadError(msg)

        return vtt_to_text(sorted(vtt_files)[0])
    finally:
        for f in Path.cwd().glob(f"{temp_basename}.*"):
            clean_up(file=str(f))


def _fallback_source(source: str) -> str:
    if source == "api":
        return "ytdlp"
    return "api"


def _fetch_transcript(source: str, url: str, video_id: str) -> str:
    if source == "api":
        try:
            return fetch_transcript_via_api(video_id)
        except Exception as e:
            msg = "API transcript backend failed"
            raise FetchTranscriptViaApiError(msg) from e
    try:
        return fetch_transcript_via_ytdlp(url)
    except Exception as e:
        msg = "yt-dlp transcript backend failed"
        raise FetchTranscriptViaYtdlpError(msg) from e


def get_yt_transcript(
    url: str,
    source: str = YT_TRANSCRIPT_SOURCE,
) -> TranscriptResult:
    """Retrieve and format the transcript from a YouTube video URL.

    Dispatches to the configured transcript backend first and tries the other
    backend as a fallback when retrieval fails.

    Args:
        url (str): The YouTube video URL.
        source (str): Transcript backend to use. Either "api"
            (youtube_transcript_api) or "ytdlp" (yt-dlp subtitle download).

    Returns:
        TranscriptResult: The transcript text and display prefix. The 📹
            prefix means the configured backend succeeded; 📺 means the
            fallback backend succeeded.

    Raises:
        ValueError: If the URL format is not recognized, or if `source` is not
            a known backend.
        FetchTranscriptViaApiError: If the API backend fails and is the final
            attempted backend.
        FetchTranscriptViaYtdlpError: If the yt-dlp backend fails and is the
            final attempted backend.

    """
    if source not in {"api", "ytdlp"}:
        msg = f"Unknown transcript source: {source}"
        raise ValueError(msg)

    video_id = extract_youtube_video_id(url)
    if video_id is None:
        msg = "Unknown URL"
        raise ValueError(msg)

    try:
        text = _fetch_transcript(source, url, video_id)
    except (FetchTranscriptViaApiError, FetchTranscriptViaYtdlpError) as primary_error:
        fallback = _fallback_source(source)
        logger.warning(
            "Transcript backend %s failed, falling back to %s: %s",
            source,
            fallback,
            primary_error,
        )
        try:
            text = _fetch_transcript(fallback, url, video_id)
        except (
            FetchTranscriptViaApiError,
            FetchTranscriptViaYtdlpError,
        ) as fallback_error:
            logger.warning(
                "Fallback backend %s also failed: %s",
                fallback,
                fallback_error,
            )
            raise fallback_error from primary_error
        return TranscriptResult(text=text, prefix="📺")
    return TranscriptResult(text=text, prefix="📹")
