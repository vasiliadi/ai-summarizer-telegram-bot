from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlsplit

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

from config import YT_HOSTS, replicate_client
from domain import PrefixedText
from exceptions import (
    FetchTranscriptError,
    TranscriptDownloadError,
)
from utils import (
    clean_up,
    generate_temporary_name,
    get_proxy,
)

if TYPE_CHECKING:
    import replicate as replicate_lib
    from tenacity import _utils as tenacity_utils

logger = logging.getLogger(__name__)
tenacity_logger = cast("tenacity_utils.LoggerProtocol", logger)


class AudioTranscriber:
    """Transcribes audio files via the Replicate WhisperX model."""

    def __init__(self, client: replicate_lib.Client) -> None:
        """Store the injected Replicate client."""
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(10),
        retry=retry_if_exception_type(ReplicateError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def transcribe(self, file: str, sleep_time: int = 10) -> str:
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
        model = self._client.models.get("victor-upmeet/whisperx")
        version = model.versions.list()[0]
        with Path(file).open("rb") as audio:
            prediction = self._client.predictions.create(
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
            [
                segment.get("text", "")
                for segment in segments
                if isinstance(segment, dict)
            ],
        )


class TranscriptBackend(ABC):
    """Abstract base for YouTube transcript-fetching backends."""

    name: str
    prefix: str

    @abstractmethod
    def fetch(self, url: str, video_id: str) -> str:
        """Fetch transcript text; backends use the argument(s) they need."""


class ApiBackend(TranscriptBackend):
    """youtube_transcript_api transcript backend (fallback by default)."""

    name = "youtube_transcript_api"
    prefix = "📺"

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
    def fetch_via_api(self, video_id: str) -> str:
        """Retrieve and format a YouTube transcript via youtube_transcript_api.

        Args:
            video_id (str): The YouTube video ID.

        Returns:
            str: The formatted transcript text.

        Raises:
            NoTranscriptFound: If no transcript is found in any language.
            CouldNotRetrieveTranscript: Subclasses propagate to the caller.
            RetryError: If transient errors persist after retries.

        """
        proxy = get_proxy()
        if proxy:
            ytt_api = YouTubeTranscriptApi(
                proxy_config=GenericProxyConfig(https_url=proxy),
            )
        else:
            ytt_api = YouTubeTranscriptApi()

        try:
            transcript = ytt_api.fetch(video_id)
        except NoTranscriptFound:
            transcript_list = ytt_api.list(video_id)
            language_codes = [t.language_code for t in transcript_list]
            # Deliberate cooldown between back-to-back requests: rapid calls get
            # rate-limited/blocked by YouTube. Do not shorten or remove.
            # See https://github.com/jdepoix/youtube-transcript-api/issues/572
            time.sleep(60)
            transcript = ytt_api.fetch(video_id, languages=language_codes)
        return TextFormatter().format_transcript(transcript)

    def fetch(self, url: str, video_id: str) -> str:  # noqa: ARG002
        """Adapt the uniform backend interface to youtube_transcript_api."""
        return self.fetch_via_api(video_id)


class YtDlpBackend(TranscriptBackend):
    """yt-dlp subtitle-download transcript backend (primary by default)."""

    name = "yt-dlp"
    prefix = "📹"

    @staticmethod
    def _vtt_to_text(vtt_path: Path) -> str:
        """Convert a VTT subtitle file to deduplicated plain text.

        Args:
            vtt_path (Path): Path to the .vtt file.

        Returns:
            str: Clean transcript text with duplicate lines removed.

        """
        lines = vtt_path.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        prev = ""
        in_note = False
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line:
                in_note = False
                continue
            if in_note:
                continue
            if "-->" in line:
                continue
            if line.startswith(("WEBVTT", "Kind:", "Language:")):
                continue
            if line.startswith("NOTE"):
                in_note = True
                continue
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if "-->" in next_line:
                continue
            clean = re.sub(r"<[^>]*>", "", line)
            clean = (
                clean.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
            )
            if clean and clean != prev:
                out.append(clean)
                prev = clean
        return "\n".join(out)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(10),
        retry=retry_if_exception_type(TranscriptDownloadError),
        before_sleep=before_sleep_log(tenacity_logger, log_level=logging.WARNING),
        reraise=False,
    )
    def fetch_via_ytdlp(self, url: str) -> str:  # noqa: C901, PLR0912, PLR0915
        """Retrieve a YouTube transcript by downloading subtitles via yt-dlp.

        Probes available tracks first, preferring genuine manual subtitles (English
        when present) and otherwise the video's original-language automatic captions,
        then converts to vtt via ffmpeg.

        Args:
            url (str): The YouTube video URL.

        Returns:
            str: The transcript as plain text.

        Raises:
            DownloadError: If no subtitles are available or vtt conversion fails.
            TranscriptDownloadError: Wraps transient yt-dlp failures; retried once.
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

        # Phase 1: probe available subtitle tracks (no download, no temp files).
        try:
            with YoutubeDL(probe_opts) as ydl:  # pyrefly: ignore[bad-argument-type]
                info = ydl.extract_info(url, download=False)
        except DownloadError as e:
            logger.warning("yt-dlp probe failed: %s: %s", type(e).__name__, e)
            raise TranscriptDownloadError(str(e)) from e
        except Exception as e:
            logger.warning(
                "yt-dlp probe failed unexpectedly: %s: %s",
                type(e).__name__,
                e,
            )
            msg = "yt-dlp probe failed"
            raise TranscriptDownloadError(msg) from e

        if info is None:
            msg = "No subtitles available via yt-dlp"
            raise DownloadError(msg)

        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}

        # yt-dlp lists "live_chat" under subtitles for live-stream replays; it is not
        # a real subtitle track and cannot be converted to vtt, so drop it.
        manual_langs = [lang for lang in manual if lang != "live_chat"]

        if manual_langs:
            en_manual = next(
                (lang for lang in manual_langs if lang.startswith("en")),
                None,
            )
            orig = info.get("language")
            chosen_langs = [
                en_manual or (orig if orig in manual_langs else manual_langs[0]),
            ]
        elif auto:
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

            try:
                return self._vtt_to_text(sorted(vtt_files)[0])
            except Exception as e:
                msg = "Failed to read downloaded VTT file"
                raise DownloadError(msg) from e
        finally:
            for f in Path.cwd().glob(f"{temp_basename}.*"):
                clean_up(file=str(f))

    def fetch(self, url: str, video_id: str) -> str:  # noqa: ARG002
        """Adapt the uniform backend interface to yt-dlp."""
        return self.fetch_via_ytdlp(url)


class YouTubeTranscriber:
    """Orchestrate primary→fallback transcript fetching across backends."""

    def __init__(
        self,
        primary: TranscriptBackend,
        fallback: TranscriptBackend,
    ) -> None:
        """Store the primary and fallback transcript backends."""
        self._primary = primary
        self._fallback = fallback

    @staticmethod
    def _extract_video_id(url: str) -> str | None:
        """Extract the video id from any supported YouTube URL form.

        Returns None when the host is not a known YouTube host or the id cannot
        be located in the path/query.

        """
        parts = urlsplit(url)
        hostname = (parts.hostname or "").lower()
        hostname = hostname.removeprefix("www.")
        if hostname not in YT_HOSTS:
            return None
        if hostname == "youtu.be":
            video_id = parts.path.lstrip("/").split("/", 1)[0]
            return video_id or None
        path_parts = [p for p in parts.path.split("/") if p]
        prefixed_paths = ("live", "shorts", "embed")
        if len(path_parts) >= 2 and path_parts[0] in prefixed_paths:  # noqa: PLR2004
            return path_parts[1]
        if path_parts and path_parts[0] == "watch":
            return parse_qs(parts.query).get("v", [None])[0]
        return None

    @staticmethod
    def _fetch_validated(
        backend: TranscriptBackend,
        url: str,
        video_id: str,
    ) -> str:
        """Fetch from a backend, treating an empty transcript as a failure.

        An empty/whitespace result is a soft failure: raising lets the
        orchestrator fall back to the other backend instead of returning a
        useless empty transcript.

        Raises:
            FetchTranscriptError: If the backend returns empty content.

        """
        text = backend.fetch(url, video_id)
        if not text.strip():
            msg = f"{backend.name} returned an empty transcript"
            raise FetchTranscriptError(msg)
        return text

    def get_transcript(self, url: str) -> PrefixedText:
        """Retrieve the transcript from a YouTube video URL.

        Tries the primary backend first, falling back to the secondary on any
        failure (including an empty result). With the default wiring this means
        the API first, then yt-dlp.

        Args:
            url (str): The YouTube video URL.

        Returns:
            PrefixedText: The transcript text and display prefix. 📺 =
                youtube_transcript_api; 📹 = yt-dlp.

        Raises:
            ValueError: If the URL format is not recognized.
            FetchTranscriptError: If both backends fail.

        """
        video_id = self._extract_video_id(url)
        if video_id is None:
            msg = "Unknown URL"
            raise ValueError(msg)

        try:
            text = self._fetch_validated(self._primary, url, video_id)
        except Exception as primary_error:
            # Any primary failure — expected or not — should try the fallback;
            # crashing here would skip the second engine entirely.
            logger.warning(
                "%s transcript backend failed, falling back to %s: %s",
                self._primary.name,
                self._fallback.name,
                primary_error,
            )
            try:
                text = self._fetch_validated(self._fallback, url, video_id)
            except Exception as fallback_error:
                logger.warning(
                    "%s fallback backend also failed: %s",
                    self._fallback.name,
                    fallback_error,
                )
                msg = "Both transcript backends failed"
                raise FetchTranscriptError(msg) from fallback_error
            return PrefixedText(text=text, prefix=self._fallback.prefix)
        return PrefixedText(text=text, prefix=self._primary.prefix)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

audio_transcriber = AudioTranscriber(replicate_client)
api_backend = ApiBackend()
ytdlp_backend = YtDlpBackend()
yt_transcriber = YouTubeTranscriber(api_backend, ytdlp_backend)


# ---------------------------------------------------------------------------
# Module-level aliases — preserve the existing public API
# ---------------------------------------------------------------------------

transcribe = audio_transcriber.transcribe
fetch_transcript_via_api = api_backend.fetch_via_api
fetch_transcript_via_ytdlp = ytdlp_backend.fetch_via_ytdlp
get_yt_transcript = yt_transcriber.get_transcript
