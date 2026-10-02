import textwrap

import pytest
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from defusedxml.ElementTree import ParseError
from requests.exceptions import ChunkedEncodingError, ProxyError, SSLError
from tenacity import RetryError
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
)
from yt_dlp.utils import DownloadError

from domain import PrefixedText
from exceptions import (
    FetchTranscriptError,
    ReplicateError,
    TranscriptDownloadError,
    TranscriptionError,
)
from transcription import (
    ApiBackend,
    AudioTranscriber,
    YouTubeTranscriber,
    YtDlpBackend,
)

URL = "https://www.youtube.com/watch?v=test"


def _install_mock_ydl(mocker, tmp_path, info, vtt_name, vtt_text, probe_errors=()):
    """Patch YoutubeDL with a stub that probes `info` and writes one vtt file.

    Each of `probe_errors` is raised by one probe before `info` is returned.

    Pins the temp basename so the fixture file can be named before the call —
    YtDlpBackend.fetch never returns it — and points Path.cwd at tmp_path so the
    production glob and the real clean_up both operate there.

    Returns:
        The list each download() call appends its requested `subtitleslangs` to.

    """
    download_calls: list[list[str]] = []
    pending_errors = list(probe_errors)
    vtt_path = tmp_path / vtt_name

    class MockYDL:
        def __init__(self, opts: dict) -> None:
            self.opts = opts

        def __enter__(self) -> MockYDL:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> dict:
            if pending_errors:
                raise pending_errors.pop(0)
            return info

        def download(self, url_list: list[str]) -> int:
            download_calls.append(self.opts.get("subtitleslangs", []))
            vtt_path.write_text(
                f"WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n{vtt_text}\n",
                encoding="utf-8",
            )
            return 0

    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    return download_calls, vtt_path


def _make_transcriber():
    """Return (transcriber, primary, fallback) wired to freshly constructed backends.

    Callers patch fetch on the returned backends
    so orchestration tests never touch the network or the module singletons.
    """
    primary = ApiBackend()
    fallback = YtDlpBackend()
    return YouTubeTranscriber(primary, fallback), primary, fallback


def test_get_yt_transcript_uses_api_primary(mocker):
    """Test get_yt_transcript uses the API first and does not touch yt-dlp on success."""
    transcriber, primary, fallback = _make_transcriber()
    mock_api = mocker.patch.object(
        primary,
        "fetch",
        return_value="from api",
    )
    mock_ytdlp = mocker.patch.object(fallback, "fetch")

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = transcriber.get_transcript(url)

    assert result == PrefixedText(text="from api", prefix="📺")
    mock_api.assert_called_once_with(url, "dQw4w9WgXcQ")
    mock_ytdlp.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
    ],
)
def test_get_yt_transcript_falls_back_to_ytdlp(mocker, url):
    """Test get_yt_transcript falls back to yt-dlp when the API fails.

    Parametrized across URL formats to confirm each resolves to the same
    video_id that is handed to the yt-dlp backend.
    """
    transcriber, primary, fallback = _make_transcriber()
    mocker.patch.object(
        primary,
        "fetch",
        side_effect=TranscriptsDisabled("dQw4w9WgXcQ"),
    )
    mock_ytdlp = mocker.patch.object(
        fallback,
        "fetch",
        return_value="from fallback",
    )

    result = transcriber.get_transcript(url)

    assert result == PrefixedText(text="from fallback", prefix="📹")
    mock_ytdlp.assert_called_once_with(url, "dQw4w9WgXcQ")


def test_get_yt_transcript_falls_back_on_unexpected_primary_error(mocker):
    """Test get_yt_transcript falls back when the primary raises an unexpected error.

    A primary failure outside the known transcript-exception types (e.g. a raw
    network error) must still trigger the fallback rather than escaping.
    """
    transcriber, primary, fallback = _make_transcriber()
    mocker.patch.object(
        primary,
        "fetch",
        side_effect=ConnectionError("network down"),
    )
    mock_ytdlp = mocker.patch.object(
        fallback,
        "fetch",
        return_value="from fallback",
    )

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = transcriber.get_transcript(url)

    assert result == PrefixedText(text="from fallback", prefix="📹")
    mock_ytdlp.assert_called_once_with(url, "dQw4w9WgXcQ")


def test_get_yt_transcript_falls_back_on_empty_primary(mocker):
    """Test get_yt_transcript falls back when the primary returns an empty transcript."""
    transcriber, primary, fallback = _make_transcriber()
    mocker.patch.object(
        primary,
        "fetch",
        return_value="   \n  ",
    )
    mock_ytdlp = mocker.patch.object(
        fallback,
        "fetch",
        return_value="from fallback",
    )

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = transcriber.get_transcript(url)

    assert result == PrefixedText(text="from fallback", prefix="📹")
    mock_ytdlp.assert_called_once_with(url, "dQw4w9WgXcQ")


def test_get_yt_transcript_both_backends_fail_raises_error(mocker):
    """Test get_yt_transcript raises FetchTranscriptError chained from the fallback failure."""
    transcriber, primary, fallback = _make_transcriber()
    api_error = TranscriptsDisabled("dQw4w9WgXcQ")
    ytdlp_error = DownloadError("no subs")
    mocker.patch.object(
        primary,
        "fetch",
        side_effect=api_error,
    )
    mocker.patch.object(
        fallback,
        "fetch",
        side_effect=ytdlp_error,
    )

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with pytest.raises(FetchTranscriptError) as exc_info:
        transcriber.get_transcript(url)

    assert exc_info.value.__cause__ is ytdlp_error


def test_get_yt_transcript_both_empty_raises_error(mocker):
    """Test get_yt_transcript raises FetchTranscriptError when both backends return empty."""
    transcriber, primary, fallback = _make_transcriber()
    mocker.patch.object(primary, "fetch", return_value="")
    mocker.patch.object(
        fallback,
        "fetch",
        return_value="  ",
    )

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with pytest.raises(FetchTranscriptError, match="Both transcript backends failed"):
        transcriber.get_transcript(url)


def test_get_yt_transcript_unknown_url(mocker):
    """Test get_yt_transcript raises ValueError for unknown URL formats."""
    transcriber, primary, fallback = _make_transcriber()
    mock_api = mocker.patch.object(primary, "fetch")
    mock_ytdlp = mocker.patch.object(fallback, "fetch")

    with pytest.raises(ValueError, match="Unknown URL"):
        transcriber.get_transcript("https://example.com/not-youtube")

    mock_api.assert_not_called()
    mock_ytdlp.assert_not_called()


def test_api_fetch_falls_back_to_other_languages(mocker):
    """Test ApiBackend.fetch retries other languages on NoTranscriptFound."""
    mocker.patch("transcription.time.sleep")  # don't actually wait 60s
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

    result = ApiBackend().fetch(URL, "dQw4w9WgXcQ")

    assert result == "Hola"
    # Verify it was called twice, once without languages, once with languages
    calls = mock_ytt.return_value.fetch.call_args_list
    assert calls[0].args == ("dQw4w9WgXcQ",)
    assert calls[1].args == ("dQw4w9WgXcQ",)
    assert calls[1].kwargs == {"languages": ["es"]}


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

    result = YtDlpBackend._vtt_to_text(vtt_path)

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

    result = YtDlpBackend._vtt_to_text(vtt_path)

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

    result = YtDlpBackend._vtt_to_text(vtt_path)

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

    result = YtDlpBackend._vtt_to_text(vtt_path)

    assert result == "Hello\nWorld\nHello"


def test_api_fetch_uses_proxy_when_configured(mocker):
    """Test ApiBackend.fetch passes GenericProxyConfig when PROXY is set."""
    # get_proxy() reads config.PROXIES, which python-dotenv backfills from the
    # developer's real .env (conftest.py never sets PROXY) — patch it so the
    # test result does not depend on what happens to be in that file.
    mocker.patch("transcription.get_proxy", return_value="http://proxy:8080")
    mock_proxy_cfg = mocker.patch("transcription.GenericProxyConfig")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mocker.patch(
        "transcription.TextFormatter",
    ).return_value.format_transcript.return_value = "Hello"
    mock_ytt.return_value.fetch.return_value = []

    result = ApiBackend().fetch(URL, "vid")

    assert result == "Hello"
    mock_proxy_cfg.assert_called_once_with(https_url="http://proxy:8080")
    mock_ytt.assert_called_once_with(proxy_config=mock_proxy_cfg.return_value)


def test_ytdlp_fetch_download_error_logged_and_retried(mocker, tmp_path):
    """Test YtDlpBackend.fetch retries DownloadError from yt-dlp twice then raises RetryError."""
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
        YtDlpBackend().fetch(URL, "test")

    assert ctx.download.call_count == 2
    mock_logger.warning.assert_any_call(
        "yt-dlp subtitle fetch failed: %s: %s",
        "DownloadError",
        mocker.ANY,
    )


def test_ytdlp_fetch_unexpected_error_wrapped_and_retried(
    mocker,
    tmp_path,
):
    """Test YtDlpBackend.fetch wraps non-DownloadError exceptions and retries."""
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
        YtDlpBackend().fetch(URL, "test")

    assert ctx.download.call_count == 2
    mock_logger.warning.assert_any_call(
        "yt-dlp subtitle fetch failed unexpectedly: %s: %s",
        "ConnectionError",
        mocker.ANY,
    )


def test_ytdlp_fetch_unexpected_error_preserves_cause(mocker, tmp_path):
    """Test YtDlpBackend.fetch preserves original cause through RetryError on exhaustion."""
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
        YtDlpBackend().fetch(URL, "test")

    last_exc = exc_info.value.last_attempt.exception()
    assert isinstance(last_exc, TranscriptDownloadError)
    assert last_exc.__cause__ is original_exc


def test_ytdlp_fetch_probe_download_error_logged_and_retried(
    mocker,
    tmp_path,
):
    """Test YtDlpBackend.fetch retries probe DownloadError twice then raises RetryError."""
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.side_effect = DownloadError("Private video")
    mock_logger = mocker.patch("transcription.logger")

    with pytest.raises(RetryError):
        YtDlpBackend().fetch(URL, "test")

    assert ctx.extract_info.call_count == 2
    mock_logger.warning.assert_any_call(
        "yt-dlp probe failed: %s: %s",
        "DownloadError",
        mocker.ANY,
    )
    ctx.download.assert_not_called()


def test_ytdlp_fetch_probe_unexpected_error_wrapped_and_retried(
    mocker,
    tmp_path,
):
    """Test YtDlpBackend.fetch wraps and retries unexpected errors from extract_info."""
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mocker.patch("time.sleep")
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    original_exc = ValueError("unexpected extractor failure")
    ctx.extract_info.side_effect = original_exc
    mock_logger = mocker.patch("transcription.logger")

    with pytest.raises(RetryError) as exc_info:
        YtDlpBackend().fetch(URL, "test")

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


def test_ytdlp_fetch_succeeds_on_second_attempt(mocker, tmp_path):
    """Test YtDlpBackend.fetch returns the transcript when only the first probe fails."""
    mocker.patch("time.sleep")
    download_calls, vtt_path = _install_mock_ydl(
        mocker,
        tmp_path,
        {"subtitles": {"en": [{}]}, "automatic_captions": {}},
        "fake-uuid.en.vtt",
        "Hello",
        probe_errors=[DownloadError("transient network blip")],
    )

    result = YtDlpBackend().fetch(URL, "test")

    assert result == "Hello"
    assert download_calls == [["en"]]
    # Real clean_up runs (Path.cwd is patched to tmp_path): the vtt fixture
    # should be gone rather than merely asserting clean_up was called.
    assert not vtt_path.exists()


def test_api_fetch_propagates_non_retryable_error(mocker):
    """Test ApiBackend.fetch propagates CouldNotRetrieveTranscript subclasses."""
    mocker.patch("transcription.get_proxy", return_value="")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_ytt.return_value.fetch.side_effect = TranscriptsDisabled("vid")

    with pytest.raises(TranscriptsDisabled):
        ApiBackend().fetch(URL, "vid")


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
def test_api_fetch_retries_on_retryable_exception(mocker, exc):
    """Test ApiBackend.fetch retries on each retryable exception then raises RetryError."""
    mocker.patch("time.sleep")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_ytt.return_value.fetch.side_effect = exc

    with pytest.raises(RetryError):
        ApiBackend().fetch(URL, "vid")

    assert mock_ytt.return_value.fetch.call_count == 2


# Track selection, in the order YtDlpBackend.fetch applies it: genuine manual
# subtitles win (English first, else the video's original language, else the
# first key), and only if there are none do automatic captions apply the same
# preference — with a "*-orig" key standing in for a missing info["language"],
# since auto-captions list machine translations for ~every language. yt-dlp
# also lists a "live_chat" pseudo-track that is not convertible to vtt.
@pytest.mark.parametrize(
    ("info", "vtt_name", "expected_langs", "expected_text"),
    [
        pytest.param(
            {"subtitles": {"fr": [{}]}, "automatic_captions": {}},
            "fake-uuid.fr.vtt",
            ["fr"],
            "Bonjour",
            id="manual-sole-language",
        ),
        pytest.param(
            {"subtitles": {"fr": [{}], "en": [{}]}, "automatic_captions": {}},
            "fake-uuid.en.vtt",
            ["en"],
            "Hello",
            id="manual-prefers-english",
        ),
        pytest.param(
            {
                "subtitles": {"fr": [{}], "de": [{}]},
                "automatic_captions": {},
                "language": "de",
            },
            "fake-uuid.de.vtt",
            ["de"],
            "Guten Tag",
            id="manual-prefers-original-over-first-key",
        ),
        pytest.param(
            {
                "subtitles": {},
                "automatic_captions": {"en": [{}], "fr": [{}]},
                "language": "fr",
            },
            "fake-uuid.fr.vtt",
            ["fr"],
            "Bonjour",
            id="auto-prefers-original-over-translated-english",
        ),
        pytest.param(
            {
                "subtitles": {},
                "automatic_captions": {"en": [{}], "de-orig": [{}], "fr": [{}]},
            },
            "fake-uuid.de-orig.vtt",
            ["de-orig"],
            "Hallo",
            id="auto-prefers-orig-key-when-language-missing",
        ),
        pytest.param(
            {"subtitles": {}, "automatic_captions": {"es": [{}], "fr": [{}]}},
            "fake-uuid.es.vtt",
            ["es"],
            "Hola",
            id="auto-falls-back-to-first-key",
        ),
        pytest.param(
            {
                "subtitles": {"live_chat": [{}]},
                "automatic_captions": {"fr": [{}]},
                "language": "fr",
            },
            "fake-uuid.fr.vtt",
            ["fr"],
            "Bonjour",
            id="ignores-live-chat-pseudo-track",
        ),
    ],
)
def test_ytdlp_fetch_selects_subtitle_track(
    mocker,
    tmp_path,
    info,
    vtt_name,
    expected_langs,
    expected_text,
):
    """Test YtDlpBackend.fetch requests the right subtitle track for each track mix."""
    download_calls, vtt_path = _install_mock_ydl(
        mocker,
        tmp_path,
        info,
        vtt_name,
        expected_text,
    )

    result = YtDlpBackend().fetch(URL, "test")

    assert result == expected_text
    assert download_calls == [expected_langs]
    # Real clean_up runs (Path.cwd is patched to tmp_path): the vtt fixture
    # should be gone rather than merely asserting clean_up was called.
    assert not vtt_path.exists()


def test_ytdlp_fetch_no_subtitles_skips_download(mocker, tmp_path):
    """Test YtDlpBackend.fetch raises without calling download when no subtitles exist."""
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {"subtitles": {}, "automatic_captions": {}}

    with pytest.raises(DownloadError, match="No subtitles available via yt-dlp"):
        YtDlpBackend().fetch(URL, "test")

    ctx.download.assert_not_called()


def test_ytdlp_fetch_extract_info_none_raises(mocker, tmp_path):
    """Test YtDlpBackend.fetch raises when extract_info returns None."""
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = None

    with pytest.raises(DownloadError, match="No subtitles available via yt-dlp"):
        YtDlpBackend().fetch(URL, "test")

    ctx.download.assert_not_called()


def test_ytdlp_fetch_vtt_read_error_raises_download_error(
    mocker,
    tmp_path,
):
    """Test YtDlpBackend.fetch converts vtt_to_text OSError into DownloadError."""
    # Fixed name kept: the vtt fixture below is pre-created on disk before the
    # call, so the name must be known ahead of time (see the comment on
    # test_YtDlpBackend.fetch_succeeds_on_second_attempt for why it can't be
    # obtained after the fact).
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }
    # create the vtt file so the glob finds it, but vtt_to_text raises OSError
    vtt_path = tmp_path / "fake-uuid.en.vtt"
    vtt_path.write_text("WEBVTT\n", encoding="utf-8")
    mocker.patch.object(YtDlpBackend, "_vtt_to_text", side_effect=OSError("disk full"))

    with pytest.raises(DownloadError, match="Failed to read downloaded VTT file"):
        YtDlpBackend().fetch(URL, "test")

    # Real clean_up runs (Path.cwd is patched to tmp_path above): the vtt
    # fixture should be gone rather than merely asserting clean_up was called.
    assert not vtt_path.exists()


def test_ytdlp_fetch_no_vtt_after_download_raises(mocker, tmp_path):
    """Test YtDlpBackend.fetch raises when download writes no vtt file."""
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    ctx = mock_ydl_cls.return_value.__enter__.return_value
    ctx.extract_info.return_value = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }
    # download() succeeds but writes nothing to tmp_path

    with pytest.raises(DownloadError, match="No subtitles available via yt-dlp"):
        YtDlpBackend().fetch(URL, "test")

    ctx.download.assert_called_once()


def test_ytdlp_fetch_pins_proxy_across_probe_and_download(
    mocker,
    tmp_path,
):
    """Test YtDlpBackend.fetch resolves the proxy once and reuses it for both YoutubeDL instances."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
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

    YtDlpBackend().fetch(URL, "test")

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
    # Real clean_up runs (Path.cwd is patched to tmp_path above): the vtt
    # fixture should be gone rather than merely asserting clean_up was called.
    assert not vtt_path.exists()


def _replicate_response(mocker, body, status=200):
    """Build a stand-in for one curl-cffi response from the Replicate API."""
    return mocker.MagicMock(
        ok=status < 400,
        status_code=status,
        text=str(body),
        json=mocker.MagicMock(return_value=body),
    )


def _install_mock_replicate(mocker, tmp_path, predictions):
    """Patch the HTTP layer to serve the model, the upload, then `predictions`.

    Each of `predictions` is a response body, a `(body, status)` pair, or an
    exception to raise; the first answers the create call, the rest the polls.

    Returns:
        The patched `request` mock and the path of a real audio fixture file.

    """
    audio = tmp_path / "test.ogg"
    audio.write_bytes(b"OggS")
    mocker.patch("transcription.time.sleep")  # Don't actually wait
    mocker.patch("tenacity.nap.time.sleep")
    responses = [
        _replicate_response(mocker, {"latest_version": {"id": "v1"}}),
        _replicate_response(mocker, {"urls": {"get": "https://files.test/audio"}}),
    ]
    for prediction in predictions:
        if isinstance(prediction, Exception):
            responses.append(prediction)
        elif isinstance(prediction, tuple):
            responses.append(_replicate_response(mocker, *prediction))
        else:
            responses.append(_replicate_response(mocker, prediction))
    request = mocker.patch(
        "transcription.curl_requests.request",
        side_effect=responses,
    )
    return request, str(audio)


def test_transcribe_happy_path(mocker, tmp_path):
    """Test transcribing an audio file successfully via Replicate."""
    request, audio = _install_mock_replicate(
        mocker,
        tmp_path,
        [
            {"id": "p1", "status": "starting"},
            {"id": "p1", "status": "processing"},
            {
                "id": "p1",
                "status": "succeeded",
                "output": {"segments": [{"text": "Hello "}, {"text": "world!"}]},
            },
        ],
    )

    result = AudioTranscriber("token").transcribe(audio)

    assert result == "Hello world!"
    calls = [(c.args[0], c.args[1]) for c in request.call_args_list]
    api = "https://api.replicate.com/v1"
    assert calls == [
        ("GET", f"{api}/models/victor-upmeet/whisperx"),
        ("POST", f"{api}/files"),
        ("POST", f"{api}/predictions"),
        ("GET", f"{api}/predictions/p1"),
        ("GET", f"{api}/predictions/p1"),
    ]
    assert all(
        c.kwargs["headers"] == {"Authorization": "Bearer token"}
        for c in request.call_args_list
    )
    assert request.call_args_list[1].kwargs["multipart"] is not None
    assert request.call_args_list[2].kwargs["json"] == {
        "version": "v1",
        "input": {"audio_file": "https://files.test/audio"},
    }


@pytest.mark.parametrize("status", ["failed", "canceled", "aborted"])
def test_transcribe_failed_prediction(mocker, tmp_path, status):
    """Test transcribe raises TranscriptionError when the prediction does not finish."""
    request, audio = _install_mock_replicate(
        mocker,
        tmp_path,
        [{"id": "p1", "status": status, "error": "boom"}],
    )

    with pytest.raises(TranscriptionError, match=f"{status}: boom"):
        AudioTranscriber("token").transcribe(audio)

    assert request.call_count == 3


def test_transcribe_null_output(mocker, tmp_path):
    """Test transcribe raises TranscriptionError when prediction output is None."""
    _, audio = _install_mock_replicate(
        mocker,
        tmp_path,
        [{"id": "p1", "status": "succeeded", "output": None}],
    )

    with pytest.raises(TranscriptionError):
        AudioTranscriber("token").transcribe(audio)


def test_transcribe_invalid_segments_raises_transcription_error(mocker, tmp_path):
    """Test transcribe raises TranscriptionError when output segments is not a list."""
    _, audio = _install_mock_replicate(
        mocker,
        tmp_path,
        [{"id": "p1", "status": "succeeded", "output": {"segments": "not-a-list"}}],
    )

    with pytest.raises(TranscriptionError):
        AudioTranscriber("token").transcribe(audio)


def test_transcribe_retries_http_errors_then_raises_retry_error(mocker):
    """Test transcribe reruns on an HTTP error and ends in RetryError."""
    mocker.patch("tenacity.nap.time.sleep")
    request = mocker.patch(
        "transcription.curl_requests.request",
        return_value=_replicate_response(mocker, {"detail": "bad token"}, 401),
    )

    with pytest.raises(RetryError) as exc_info:
        AudioTranscriber("token").transcribe("test.ogg")

    assert request.call_count == 3
    error = exc_info.value.last_attempt.exception()
    assert isinstance(error, ReplicateError)
    assert error.status == 401


@pytest.mark.parametrize(
    "blip",
    [
        ({"detail": "throttled"}, 429),
        ({"detail": "unavailable"}, 503),
        CurlConnectionError("connection reset"),
    ],
)
def test_transcribe_poll_survives_transient_failure(mocker, tmp_path, blip):
    """Test a transient poll failure is repeated without a second upload."""
    request, audio = _install_mock_replicate(
        mocker,
        tmp_path,
        [
            {"id": "p1", "status": "starting"},
            blip,
            {"id": "p1", "status": "succeeded", "output": {"segments": []}},
        ],
    )

    assert AudioTranscriber("token").transcribe(audio) == ""

    methods = [c.args[0] for c in request.call_args_list]
    assert methods == ["GET", "POST", "POST", "GET", "GET"]


def test_transcribe_poll_does_not_repeat_permanent_error(mocker, tmp_path):
    """Test a non-transient poll error skips the poll retry and reruns transcribe."""
    request, audio = _install_mock_replicate(
        mocker,
        tmp_path,
        [
            {"id": "p1", "status": "starting"},
            ({"detail": "not found"}, 404),
        ],
    )
    # The second attempt of the whole transcribe.
    request.side_effect = [
        *request.side_effect,
        _replicate_response(mocker, {"latest_version": {"id": "v1"}}),
        _replicate_response(mocker, {"urls": {"get": "https://files.test/audio"}}),
        _replicate_response(
            mocker,
            {"id": "p2", "status": "succeeded", "output": {"segments": []}},
        ),
    ]

    assert AudioTranscriber("token").transcribe(audio) == ""

    assert request.call_count == 7


def test_transcribe_network_error_outside_poll_propagates(mocker):
    """Test a network error on a non-poll request is raised as is, not retried."""
    request = mocker.patch(
        "transcription.curl_requests.request",
        side_effect=CurlConnectionError("connection reset"),
    )

    with pytest.raises(CurlConnectionError):
        AudioTranscriber("token").transcribe("test.ogg")

    request.assert_called_once()


def test_extract_video_id_uppercase_host():
    """_extract_video_id handles uppercase and mixed-case hostnames."""
    assert (
        YouTubeTranscriber._extract_video_id("https://YOUTU.BE/dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )
    assert (
        YouTubeTranscriber._extract_video_id(
            "https://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ",
        )
        == "dQw4w9WgXcQ"
    )


def test_extract_video_id_malformed_url():
    """_extract_video_id returns None for malformed URLs with no hostname."""
    assert YouTubeTranscriber._extract_video_id("not-a-url") is None
    assert YouTubeTranscriber._extract_video_id("https://") is None


def test_extract_video_id_empty_path():
    """_extract_video_id returns None for youtu.be with no video ID and watch with no v param."""
    assert YouTubeTranscriber._extract_video_id("https://youtu.be/") is None
    assert YouTubeTranscriber._extract_video_id("https://www.youtube.com/watch") is None


def test_extract_video_id_unrecognized_path():
    """_extract_video_id returns None for youtube.com URLs with unrecognized paths."""
    assert (
        YouTubeTranscriber._extract_video_id("https://youtube.com/playlist?list=PLxxx")
        is None
    )
    assert YouTubeTranscriber._extract_video_id("https://youtube.com/") is None
