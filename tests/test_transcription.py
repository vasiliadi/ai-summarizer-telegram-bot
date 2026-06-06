import textwrap

import pytest
from replicate.exceptions import ModelError
from requests.exceptions import ChunkedEncodingError, ProxyError, SSLError
from tenacity import RetryError
from defusedxml.ElementTree import ParseError
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
)
from yt_dlp.utils import DownloadError

from exceptions import (
    FetchTranscriptViaApiError,
    FetchTranscriptViaYtdlpError,
    TranscriptDownloadError,
)
from transcription import (
    TranscriptResult,
    fetch_transcript_via_api,
    fetch_transcript_via_ytdlp,
    get_yt_transcript,
    transcribe,
)
from utils import vtt_to_text


def test_get_yt_transcript_youtube_watch_url(mocker):
    """Test get_yt_transcript with standard YouTube watch URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    # Mocking the fetch results
    mock_ytt.return_value.fetch.return_value = [
        {"text": "Hello", "start": 0, "duration": 1}
    ]
    mock_formatter.return_value.format_transcript.return_value = "Hello"

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url, source="api")

    assert result == TranscriptResult(text="Hello", prefix="📹")
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")


def test_get_yt_transcript_youtu_be_url(mocker):
    """Test get_yt_transcript with short youtu.be URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    mock_ytt.return_value.fetch.return_value = []
    mock_formatter.return_value.format_transcript.return_value = "Hello short"

    url = "https://youtu.be/dQw4w9WgXcQ"
    result = get_yt_transcript(url, source="api")

    assert result == TranscriptResult(text="Hello short", prefix="📹")
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")


def test_get_yt_transcript_youtube_live_url(mocker):
    """Test get_yt_transcript with YouTube live URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    mock_ytt.return_value.fetch.return_value = []
    mock_formatter.return_value.format_transcript.return_value = "Hello live"

    url = "https://www.youtube.com/live/dQw4w9WgXcQ"
    result = get_yt_transcript(url, source="api")

    assert result == TranscriptResult(text="Hello live", prefix="📹")
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")


def test_get_yt_transcript_unknown_url(mocker):
    """Test get_yt_transcript raises ValueError for unknown URL formats."""
    mock_api = mocker.patch("transcription.fetch_transcript_via_api")
    mock_ytdlp = mocker.patch("transcription.fetch_transcript_via_ytdlp")

    with pytest.raises(ValueError, match="Unknown URL"):
        get_yt_transcript("https://example.com/not-youtube", source="api")

    mock_api.assert_not_called()
    mock_ytdlp.assert_not_called()


def test_get_yt_transcript_fallback_languages(mocker):
    """Test get_yt_transcript falls back to other languages if NoTranscriptFound."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    # First call to fetch raises NoTranscriptFound
    mock_ytt.return_value.fetch.side_effect = [
        NoTranscriptFound("vid", "en", []),
        [{"text": "Hola"}],
    ]
    # Mock list to return language codes
    mock_transcript = mocker.MagicMock()
    mock_transcript.language_code = "es"
    mock_ytt.return_value.list.return_value = [mock_transcript]

    mock_formatter.return_value.format_transcript.return_value = "Hola"

    url = "https://youtu.be/dQw4w9WgXcQ"
    result = get_yt_transcript(url, source="api")

    assert result == TranscriptResult(text="Hola", prefix="📹")
    # Verify it was called twice, once without languages, once with languages
    calls = mock_ytt.return_value.fetch.call_args_list
    assert calls[0].args == ("dQw4w9WgXcQ",)
    assert calls[1].args == ("dQw4w9WgXcQ",)
    assert calls[1].kwargs == {"languages": ["es"]}


def test_get_yt_transcript_source_ytdlp(mocker, tmp_path):
    """Test get_yt_transcript with source='ytdlp' uses yt-dlp and does not touch the API."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = textwrap.dedent("""\
        WEBVTT

        00:00:01.000 --> 00:00:03.000
        Hello world
    """)
    vtt_file = tmp_path / "fake-uuid.en.vtt"
    vtt_file.write_text(vtt_content, encoding="utf-8")

    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    mock_ydl_inst = mock_ydl_cls.return_value.__enter__.return_value
    mock_ydl_inst.extract_info.return_value = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }
    mock_api = mocker.patch("transcription.fetch_transcript_via_api")

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url, source="ytdlp")

    assert "Hello world" in result.text
    assert result.prefix == "📹"
    mock_ydl_inst.download.assert_called_once_with([url])
    mock_api.assert_not_called()


def test_get_yt_transcript_source_api_falls_back_to_ytdlp(mocker):
    """Test get_yt_transcript with source='api' falls back to yt-dlp."""
    mocker.patch(
        "transcription.fetch_transcript_via_api",
        side_effect=TranscriptsDisabled("dQw4w9WgXcQ"),
    )
    mock_ytdlp = mocker.patch(
        "transcription.fetch_transcript_via_ytdlp",
        return_value="from fallback",
    )

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url, source="api")

    assert result == TranscriptResult(text="from fallback", prefix="📺")
    mock_ytdlp.assert_called_once_with(url)


def test_get_yt_transcript_source_ytdlp_falls_back_to_api(mocker):
    """Test get_yt_transcript with source='ytdlp' falls back to the API."""
    mocker.patch(
        "transcription.fetch_transcript_via_ytdlp",
        side_effect=DownloadError("no subs"),
    )
    mock_api = mocker.patch(
        "transcription.fetch_transcript_via_api",
        return_value="from fallback",
    )

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url, source="ytdlp")

    assert result == TranscriptResult(text="from fallback", prefix="📺")
    mock_api.assert_called_once_with("dQw4w9WgXcQ")


def test_get_yt_transcript_source_fallback_failure_raises_fallback_error(mocker):
    """Test get_yt_transcript raises fallback errors chained from primary failures."""
    primary_error = TranscriptsDisabled("dQw4w9WgXcQ")
    fallback_error = DownloadError("no subs")
    mocker.patch("transcription.fetch_transcript_via_api", side_effect=primary_error)
    mocker.patch("transcription.fetch_transcript_via_ytdlp", side_effect=fallback_error)

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with pytest.raises(FetchTranscriptViaYtdlpError) as exc_info:
        get_yt_transcript(url, source="api")

    assert isinstance(exc_info.value.__cause__, FetchTranscriptViaApiError)
    assert exc_info.value.__cause__.__cause__ is primary_error


def test_get_yt_transcript_unknown_source_raises_value_error(mocker):
    """Test get_yt_transcript raises ValueError for an unknown source."""
    mock_api = mocker.patch("transcription.fetch_transcript_via_api")
    mock_ytdlp = mocker.patch("transcription.fetch_transcript_via_ytdlp")

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with pytest.raises(ValueError, match="Unknown transcript source"):
        get_yt_transcript(url, source="bogus")

    mock_api.assert_not_called()
    mock_ytdlp.assert_not_called()


def test_get_yt_transcript_defaults_source_to_config(mocker):
    """Test get_yt_transcript uses the configured backend (default "ytdlp") when omitted."""
    mock_ytdlp = mocker.patch(
        "transcription.fetch_transcript_via_ytdlp",
        return_value="from config",
    )
    mock_api = mocker.patch("transcription.fetch_transcript_via_api")

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert result == TranscriptResult(text="from config", prefix="📹")
    mock_ytdlp.assert_called_once_with(url)
    mock_api.assert_not_called()


def test_vtt_to_text_dedupes_and_strips_tags(tmp_path):
    """Test vtt_to_text removes headers, timestamps, HTML tags, entities, and duplicates."""
    vtt_content = textwrap.dedent("""\
        WEBVTT
        Kind: captions
        Language: en

        NOTE This is a note

        00:00:01.000 --> 00:00:03.000
        <00:00:01.500><c>Hello</c> &amp; world

        00:00:03.000 --> 00:00:05.000
        Hello &amp; world

        00:00:05.000 --> 00:00:07.000
        Second line
    """)
    vtt_path = tmp_path / "test.vtt"
    vtt_path.write_text(vtt_content, encoding="utf-8")

    result = vtt_to_text(vtt_path)

    assert result == "Hello & world\nSecond line"


def test_vtt_to_text_skips_cue_identifiers(tmp_path):
    """Test vtt_to_text skips cue identifier lines (numeric or text) before timestamps."""
    vtt_content = textwrap.dedent("""\
        WEBVTT

        1
        00:00:01.000 --> 00:00:03.000
        Hello

        intro
        00:00:03.000 --> 00:00:05.000
        World
    """)
    vtt_path = tmp_path / "test.vtt"
    vtt_path.write_text(vtt_content, encoding="utf-8")

    result = vtt_to_text(vtt_path)

    assert result == "Hello\nWorld"


def test_vtt_to_text_skips_multiline_note_block(tmp_path):
    """Test vtt_to_text skips all lines inside a multiline NOTE block."""
    vtt_content = textwrap.dedent("""\
        WEBVTT

        NOTE
        This comment should not appear
        in the transcript output.

        00:00:01.000 --> 00:00:03.000
        Hello

        NOTE This inline note also skipped

        00:00:03.000 --> 00:00:05.000
        World
    """)
    vtt_path = tmp_path / "test.vtt"
    vtt_path.write_text(vtt_content, encoding="utf-8")

    result = vtt_to_text(vtt_path)

    assert result == "Hello\nWorld"
    assert "comment" not in result
    assert "inline" not in result


def test_vtt_to_text_keeps_nonconsecutive_duplicates(tmp_path):
    """Test vtt_to_text only skips consecutive duplicate lines, not non-consecutive ones."""
    vtt_content = textwrap.dedent("""\
        WEBVTT

        00:00:01.000 --> 00:00:03.000
        Hello

        00:00:03.000 --> 00:00:05.000
        World

        00:00:05.000 --> 00:00:07.000
        Hello
    """)
    vtt_path = tmp_path / "test.vtt"
    vtt_path.write_text(vtt_content, encoding="utf-8")

    result = vtt_to_text(vtt_path)

    assert result == "Hello\nWorld\nHello"


def test_fetch_transcript_via_api_uses_proxy_when_configured(mocker):
    """Test fetch_transcript_via_api passes GenericProxyConfig when PROXY is set."""
    mocker.patch("transcription.get_proxy", return_value="http://proxy:8080")
    mock_proxy_cfg = mocker.patch("transcription.GenericProxyConfig")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mocker.patch(
        "transcription.TextFormatter"
    ).return_value.format_transcript.return_value = "Hello"
    mock_ytt.return_value.fetch.return_value = []

    result = fetch_transcript_via_api("vid")

    assert result == "Hello"
    mock_proxy_cfg.assert_called_once_with(https_url="http://proxy:8080")
    mock_ytt.assert_called_once_with(proxy_config=mock_proxy_cfg.return_value)


def test_fetch_transcript_via_ytdlp_download_error_logged_and_retried(
    mocker, tmp_path
):
    """Test fetch_transcript_via_ytdlp retries DownloadError from yt-dlp twice then raises RetryError."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }
    ctx.download.side_effect = DownloadError("Sign in to confirm")
    mock_logger = mocker.patch("transcription.logger")

    with pytest.raises(RetryError):
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert ctx.download.call_count == 2
    mock_logger.warning.assert_any_call(
        "yt-dlp subtitle fetch failed: %s: %s",
        "DownloadError",
        mocker.ANY,
    )


def test_fetch_transcript_via_ytdlp_unexpected_error_wrapped_and_retried(
    mocker, tmp_path
):
    """Test fetch_transcript_via_ytdlp wraps non-DownloadError exceptions and retries."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }
    ctx.download.side_effect = ConnectionError("network failure")
    mock_logger = mocker.patch("transcription.logger")

    with pytest.raises(RetryError):
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert ctx.download.call_count == 2
    mock_logger.warning.assert_any_call(
        "yt-dlp subtitle fetch failed unexpectedly: %s: %s",
        "ConnectionError",
        mocker.ANY,
    )


def test_fetch_transcript_via_ytdlp_unexpected_error_preserves_cause(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp preserves original cause through RetryError on exhaustion."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }
    original_exc = ConnectionError("network failure")
    ctx.download.side_effect = original_exc

    with pytest.raises(RetryError) as exc_info:
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    last_exc = exc_info.value.last_attempt.exception()
    assert isinstance(last_exc, TranscriptDownloadError)
    assert last_exc.__cause__ is original_exc


def test_fetch_transcript_via_ytdlp_probe_download_error_logged_and_retried(
    mocker, tmp_path
):
    """Test fetch_transcript_via_ytdlp retries probe DownloadError twice then raises RetryError."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.side_effect = DownloadError("Private video")
    mock_logger = mocker.patch("transcription.logger")

    with pytest.raises(RetryError):
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert ctx.extract_info.call_count == 2
    mock_logger.warning.assert_any_call(
        "yt-dlp probe failed: %s: %s",
        "DownloadError",
        mocker.ANY,
    )
    ctx.download.assert_not_called()


def test_fetch_transcript_via_ytdlp_probe_unexpected_error_wrapped_and_retried(
    mocker, tmp_path
):
    """Test fetch_transcript_via_ytdlp wraps and retries unexpected errors from extract_info."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    original_exc = ValueError("unexpected extractor failure")
    ctx.extract_info.side_effect = original_exc
    mock_logger = mocker.patch("transcription.logger")

    with pytest.raises(RetryError) as exc_info:
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    last_exc = exc_info.value.last_attempt.exception()
    assert isinstance(last_exc, TranscriptDownloadError)
    assert isinstance(last_exc.__cause__, ValueError)
    assert ctx.extract_info.call_count == 2
    mock_logger.warning.assert_any_call(
        "yt-dlp probe failed unexpectedly: %s: %s",
        "ValueError",
        mocker.ANY,
    )
    ctx.download.assert_not_called()


def test_fetch_transcript_via_ytdlp_succeeds_on_second_attempt(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp returns transcript when first probe fails but second succeeds."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello\n"
    vtt_path = tmp_path / "fake-uuid.en.vtt"

    class MockYDL:
        attempt = 0

        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            MockYDL.attempt += 1
            if MockYDL.attempt == 1:
                raise DownloadError("transient network blip")
            return {"subtitles": {"en": [{}]}, "automatic_captions": {}}

        def download(self, url_list: list[str]) -> int:
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Hello"
    assert MockYDL.attempt == 2


def test_fetch_transcript_via_api_propagates_non_retryable_error(mocker):
    """Test fetch_transcript_via_api propagates CouldNotRetrieveTranscript subclasses."""
    mocker.patch("transcription.get_proxy", return_value="")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_ytt.return_value.fetch.side_effect = TranscriptsDisabled("vid")

    with pytest.raises(TranscriptsDisabled):
        fetch_transcript_via_api("vid")


@pytest.mark.parametrize(
    "exc",
    [
        IpBlocked("vid"),
        RequestBlocked("vid"),
        ParseError(),
        ProxyError(),
        SSLError(),
        ChunkedEncodingError(),
    ],
)
def test_fetch_transcript_via_api_retries_on_retryable_exception(mocker, exc):
    """Test fetch_transcript_via_api retries on each retryable exception then raises RetryError."""
    mocker.patch("time.sleep")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_ytt.return_value.fetch.side_effect = exc

    with pytest.raises(RetryError):
        fetch_transcript_via_api("vid")

    assert mock_ytt.return_value.fetch.call_count == 2


def test_fetch_transcript_via_ytdlp_non_english_fallback(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp requests the available language when no English is offered."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nBonjour\n"
    vtt_path = tmp_path / "fake-uuid.fr.vtt"
    download_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            return {"subtitles": {"fr": [{}]}, "automatic_captions": {}}

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            download_calls.append(langs)
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Bonjour"
    assert download_calls == [["fr"]]


def test_fetch_transcript_via_ytdlp_prefers_english_when_available(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp picks English even when other languages are present."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello\n"
    vtt_path = tmp_path / "fake-uuid.en.vtt"
    download_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            return {"subtitles": {"fr": [{}], "en": [{}]}, "automatic_captions": {}}

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            download_calls.append(langs)
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Hello"
    assert download_calls == [["en"]]


def test_fetch_transcript_via_ytdlp_manual_prefers_original_language_over_first_key(
    mocker,
    tmp_path,
):
    """Test manual-subtitle branch prefers info['language'] when no English track exists.

    When a video has multiple manual subtitle languages but none is English, the
    selection should prefer the video's original language (info['language']) rather
    than the first dict key (which is insertion-order dependent).
    """
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nGuten Tag\n"
    vtt_path = tmp_path / "fake-uuid.de.vtt"
    download_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            # "fr" comes first in the dict, but the video's original language is "de"
            return {
                "subtitles": {"fr": [{}], "de": [{}]},
                "automatic_captions": {},
                "language": "de",
            }

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            download_calls.append(langs)
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Guten Tag"
    assert download_calls == [["de"]]


def test_fetch_transcript_via_ytdlp_auto_captions_uses_original_language(
    mocker,
    tmp_path,
):
    """Test fetch_transcript_via_ytdlp requests the original language, not translated English.

    automatic_captions list machine translations (incl. "en") for ~every language,
    so for a non-English video with no manual subs we must request the original
    language (info["language"]) rather than the translated "en" track.
    """
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nBonjour\n"
    vtt_path = tmp_path / "fake-uuid.fr.vtt"
    download_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            return {
                "subtitles": {},
                "automatic_captions": {"en": [{}], "fr": [{}]},
                "language": "fr",
            }

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            download_calls.append(langs)
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Bonjour"
    assert download_calls == [["fr"]]


def test_fetch_transcript_via_ytdlp_auto_captions_prefers_orig_key_when_language_missing(
    mocker,
    tmp_path,
):
    """Test auto-captions branch picks the *-orig key when info['language'] is absent.

    When no info['language'] is available (or it isn't in auto) but a '*-orig' key
    exists in automatic_captions, that key should be preferred over the first dict key.
    """
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHallo\n"
    vtt_path = tmp_path / "fake-uuid.de-orig.vtt"
    download_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            # no 'language' key; auto has a '*-orig' key that should be preferred
            return {
                "subtitles": {},
                "automatic_captions": {"en": [{}], "de-orig": [{}], "fr": [{}]},
            }

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            download_calls.append(langs)
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Hallo"
    assert download_calls == [["de-orig"]]


def test_fetch_transcript_via_ytdlp_auto_captions_falls_back_to_first_key(
    mocker,
    tmp_path,
):
    """Test auto-captions branch falls back to first key when no language or *-orig key.

    When info['language'] is absent and no '*-orig' key exists in automatic_captions,
    the first key in the dict is used as a last resort.
    """
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHola\n"
    vtt_path = tmp_path / "fake-uuid.es.vtt"
    download_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            # no 'language' key, no '*-orig' key → must fall back to first key ("es")
            return {
                "subtitles": {},
                "automatic_captions": {"es": [{}], "fr": [{}]},
            }

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            download_calls.append(langs)
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Hola"
    assert download_calls == [["es"]]


def test_fetch_transcript_via_ytdlp_ignores_live_chat_pseudo_track(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp skips the "live_chat" subtitles entry.

    yt-dlp lists a "live_chat" key under subtitles for live-stream replays; it is
    not a real subtitle track. It must be ignored so selection falls through to the
    video's original-language automatic captions rather than requesting "live_chat".
    """
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nBonjour\n"
    vtt_path = tmp_path / "fake-uuid.fr.vtt"
    download_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            return {
                "subtitles": {"live_chat": [{}]},
                "automatic_captions": {"fr": [{}]},
                "language": "fr",
            }

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            download_calls.append(langs)
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Bonjour"
    assert download_calls == [["fr"]]


def test_fetch_transcript_via_ytdlp_no_subtitles_skips_download(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp raises without calling download when no subtitles exist."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {"subtitles": {}, "automatic_captions": {}}

    with pytest.raises(DownloadError, match="No subtitles available via yt-dlp"):
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    ctx.download.assert_not_called()


def test_fetch_transcript_via_ytdlp_extract_info_none_raises(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp raises when extract_info returns None."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = None

    with pytest.raises(DownloadError, match="No subtitles available via yt-dlp"):
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    ctx.download.assert_not_called()


def test_fetch_transcript_via_ytdlp_no_vtt_after_download_raises(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp raises when download writes no vtt file."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("transcription.clean_up")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {"subtitles": {"en": [{}]}, "automatic_captions": {}}
    # download() succeeds but writes nothing to tmp_path

    with pytest.raises(DownloadError, match="No subtitles available via yt-dlp"):
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    ctx.download.assert_called_once()


def test_fetch_transcript_via_ytdlp_pins_proxy_across_probe_and_download(
    mocker, tmp_path
):
    """Test fetch_transcript_via_ytdlp resolves the proxy once and reuses it for both YoutubeDL instances."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("transcription.get_proxy", return_value="http://proxy.example:8080")

    vtt_path = tmp_path / "fake-uuid.en.vtt"
    vtt_path.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello\n",
        encoding="utf-8",
    )

    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }

    fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert mock_ydl_cls.call_count == 2
    probe_opts, download_opts = (call.args[0] for call in mock_ydl_cls.call_args_list)
    assert probe_opts["proxy"] == "http://proxy.example:8080"
    assert probe_opts["noplaylist"] is True
    assert download_opts["proxy"] == "http://proxy.example:8080"
    assert download_opts["noplaylist"] is True
    assert download_opts["subtitlesformat"] == "vtt/best"
    assert any(
        pp.get("key") == "FFmpegSubtitlesConvertor" and pp.get("format") == "vtt"
        for pp in download_opts.get("postprocessors", [])
    )


def test_transcribe_happy_path(mocker):
    """Test transcribing an audio file successfully via Replicate."""
    mock_replicate = mocker.patch("transcription.replicate_client")
    mocker.patch("transcription.Path.open", mocker.mock_open())
    mocker.patch("transcription.time.sleep")  # Don't actually wait

    # Mock the prediction object and its lifecycle
    mock_prediction = mocker.MagicMock()
    mock_prediction.status = "processing"
    # sequence of statuses: processing -> succeeded
    # status is checked twice per loop (while condition and inside if)
    type(mock_prediction).status = mocker.PropertyMock(
        side_effect=["processing", "processing", "succeeded", "succeeded"]
    )
    mock_prediction.output = {"segments": [{"text": "Hello "}, {"text": "world!"}]}

    mock_replicate.models.get.return_value.versions.list.return_value = [
        mocker.MagicMock(id="v1")
    ]
    mock_replicate.predictions.create.return_value = mock_prediction

    result = transcribe("test.ogg")

    assert result == "Hello world!"
    mock_prediction.reload.assert_called_once()


def test_transcribe_failed_prediction(mocker):
    """Test transcribe raises ModelError when prediction fails."""
    mock_replicate = mocker.patch("transcription.replicate_client")
    mocker.patch("transcription.Path.open", mocker.mock_open())

    mock_prediction = mocker.MagicMock()
    mock_prediction.status = "failed"
    mock_replicate.predictions.create.return_value = mock_prediction
    mock_replicate.models.get.return_value.versions.list.return_value = [
        mocker.MagicMock(id="v1")
    ]

    with pytest.raises(ModelError):
        transcribe("test.ogg")


def test_transcribe_null_output(mocker):
    """Test transcribe raises ModelError when prediction output is None."""
    mock_replicate = mocker.patch("transcription.replicate_client")
    mocker.patch("transcription.Path.open", mocker.mock_open())

    mock_prediction = mocker.MagicMock()
    mock_prediction.status = "succeeded"
    mock_prediction.output = None
    mock_replicate.predictions.create.return_value = mock_prediction
    mock_replicate.models.get.return_value.versions.list.return_value = [
        mocker.MagicMock(id="v1")
    ]

    with pytest.raises(ModelError):
        transcribe("test.ogg")
