import textwrap

import pytest
from replicate.exceptions import ModelError
from tenacity import RetryError
from defusedxml.ElementTree import ParseError
from youtube_transcript_api._errors import IpBlocked, NoTranscriptFound, RequestBlocked
from yt_dlp.utils import DownloadError

from transcription import fetch_transcript_via_api, fetch_transcript_via_ytdlp, get_yt_transcript, transcribe
from utils import vtt_to_text


def test_get_yt_transcript_youtube_watch_url(mocker):
    """Test get_yt_transcript with standard YouTube watch URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    # Mocking the fetch results
    mock_ytt.return_value.fetch.return_value = [{"text": "Hello", "start": 0, "duration": 1}]
    mock_formatter.return_value.format_transcript.return_value = "Hello"

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert result == "Hello"
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")

def test_get_yt_transcript_youtu_be_url(mocker):
    """Test get_yt_transcript with short youtu.be URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    mock_ytt.return_value.fetch.return_value = []
    mock_formatter.return_value.format_transcript.return_value = "Hello short"

    url = "https://youtu.be/dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert result == "Hello short"
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")

def test_get_yt_transcript_youtube_live_url(mocker):
    """Test get_yt_transcript with YouTube live URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    mock_ytt.return_value.fetch.return_value = []
    mock_formatter.return_value.format_transcript.return_value = "Hello live"

    url = "https://www.youtube.com/live/dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert result == "Hello live"
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")

def test_get_yt_transcript_unknown_url():
    """Test get_yt_transcript raises ValueError for unknown URL formats."""
    with pytest.raises(ValueError, match="Unknown URL"):
        get_yt_transcript("https://example.com/not-youtube")

def test_get_yt_transcript_fallback_languages(mocker):
    """Test get_yt_transcript falls back to other languages if NoTranscriptFound."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    # First call to fetch raises NoTranscriptFound
    mock_ytt.return_value.fetch.side_effect = [NoTranscriptFound("vid", "en", []), [{"text": "Hola"}]]
    # Mock list to return language codes
    mock_transcript = mocker.MagicMock()
    mock_transcript.language_code = "es"
    mock_ytt.return_value.list.return_value = [mock_transcript]

    mock_formatter.return_value.format_transcript.return_value = "Hola"

    url = "https://youtu.be/vid"
    result = get_yt_transcript(url)

    assert result == "Hola"
    # Verify it was called twice, once without languages, once with languages
    calls = mock_ytt.return_value.fetch.call_args_list
    assert calls[0].args == ("vid",)
    assert calls[1].args == ("vid",)
    assert calls[1].kwargs == {"languages": ["es"]}

def test_get_yt_transcript_falls_back_to_ytdlp_on_api_failure(mocker, tmp_path):
    """Test get_yt_transcript falls back to yt-dlp when fetch_transcript_via_api exhausts retries."""
    mocker.patch("time.sleep")
    mocker.patch(
        "transcription.fetch_transcript_via_api",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")

    vtt_content = textwrap.dedent("""\
        WEBVTT
        Kind: captions
        Language: en

        00:00:01.000 --> 00:00:03.000
        Hello world

        00:00:03.000 --> 00:00:05.000
        Hello world

        00:00:05.000 --> 00:00:07.000
        Goodbye
    """)
    vtt_file = tmp_path / "fake-uuid.en.vtt"
    vtt_file.write_text(vtt_content, encoding="utf-8")

    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    mock_ydl_inst = mock_ydl_cls.return_value.__enter__.return_value
    mocker.patch("transcription.clean_up")

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert "Hello world" in result
    assert "Goodbye" in result
    # Deduplication: "Hello world" appears twice in VTT but only once in output
    assert result.count("Hello world") == 1
    # English pass found the VTT file — only one download attempt needed
    mock_ydl_inst.download.assert_called_once_with([url])

def test_get_yt_transcript_ytdlp_no_subs_raises(mocker, tmp_path):
    """Test get_yt_transcript raises DownloadError when yt-dlp finds no subtitles."""
    mocker.patch("time.sleep")
    mocker.patch(
        "transcription.fetch_transcript_via_api",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    mock_ydl_inst = mock_ydl_cls.return_value.__enter__.return_value

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with pytest.raises(DownloadError, match="No subtitles available via yt-dlp"):
        get_yt_transcript(url)

    # Both English and all-languages passes must have been attempted
    assert mock_ydl_inst.download.call_count == 2
    mock_ydl_inst.download.assert_called_with([url])

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
    mocker.patch("transcription.PROXY", "http://proxy:8080")
    mock_proxy_cfg = mocker.patch("transcription.GenericProxyConfig")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mocker.patch("transcription.TextFormatter").return_value.format_transcript.return_value = "Hello"
    mock_ytt.return_value.fetch.return_value = []

    result = fetch_transcript_via_api("vid")

    assert result == "Hello"
    mock_proxy_cfg.assert_called_once_with(https_url="http://proxy:8080")
    mock_ytt.assert_called_once_with(proxy_config=mock_proxy_cfg.return_value)

def test_fetch_transcript_via_ytdlp_unexpected_error_wrapped_as_download_error(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp wraps non-DownloadError exceptions as DownloadError."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    mock_ydl_cls.return_value.__enter__.return_value.download.side_effect = ConnectionError("network failure")
    mock_logger = mocker.patch("transcription.logger")

    with pytest.raises(DownloadError, match="yt-dlp subtitle fetch failed"):
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    mock_logger.warning.assert_called_once_with(
        "yt-dlp subtitle fetch failed unexpectedly: %s",
        mocker.ANY,
    )

def test_fetch_transcript_via_ytdlp_unexpected_error_preserves_cause(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp sets original exception as __cause__ of raised DownloadError."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)
    mock_ydl_cls = mocker.patch("transcription.YoutubeDL")
    original_exc = ConnectionError("network failure")
    mock_ydl_cls.return_value.__enter__.return_value.download.side_effect = original_exc

    with pytest.raises(DownloadError) as exc_info:
        fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert exc_info.value.__cause__ is original_exc

@pytest.mark.parametrize("exc", [IpBlocked("vid"), RequestBlocked("vid"), ParseError()])
def test_fetch_transcript_via_api_retries_on_retryable_exception(mocker, exc):
    """Test fetch_transcript_via_api retries on each retryable exception then raises RetryError."""
    mocker.patch("time.sleep")
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_ytt.return_value.fetch.side_effect = exc

    with pytest.raises(RetryError):
        fetch_transcript_via_api("vid")

    assert mock_ytt.return_value.fetch.call_count == 2

def test_fetch_transcript_via_ytdlp_all_language_fallback(mocker, tmp_path):
    """Test fetch_transcript_via_ytdlp retries with all languages when English is unavailable."""
    mocker.patch("transcription.generate_temporary_name", return_value="fake-uuid")
    mocker.patch("transcription.clean_up")

    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nBonjour\n"
    vtt_path = tmp_path / "fake-uuid.fr.vtt"
    extract_calls: list[list[str]] = []

    class MockYDL:
        def __init__(self, opts: object) -> None:
            self.opts = opts

        def __enter__(self) -> "MockYDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def download(self, url_list: list[str]) -> int:
            langs = self.opts.get("subtitleslangs", [])
            extract_calls.append(langs)
            if "all" in langs:
                vtt_path.write_text(vtt_content, encoding="utf-8")
            return 0

    mocker.patch("transcription.YoutubeDL", MockYDL)
    mocker.patch("transcription.Path.cwd", return_value=tmp_path)

    result = fetch_transcript_via_ytdlp("https://www.youtube.com/watch?v=test")

    assert result == "Bonjour"
    assert extract_calls == [["en.*", "en"], ["all"]]

def test_transcribe_happy_path(mocker):
    """Test transcribing an audio file successfully via Replicate."""
    mock_replicate = mocker.patch("transcription.replicate_client")
    mocker.patch("transcription.Path.open", mocker.mock_open())
    mocker.patch("transcription.time.sleep") # Don't actually wait

    # Mock the prediction object and its lifecycle
    mock_prediction = mocker.MagicMock()
    mock_prediction.status = "processing"
    # sequence of statuses: processing -> succeeded
    # status is checked twice per loop (while condition and inside if)
    type(mock_prediction).status = mocker.PropertyMock(side_effect=["processing", "processing", "succeeded", "succeeded"])
    mock_prediction.output = {"segments": [{"text": "Hello "}, {"text": "world!"}]}

    mock_replicate.models.get.return_value.versions.list.return_value = [mocker.MagicMock(id="v1")]
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
    mock_replicate.models.get.return_value.versions.list.return_value = [mocker.MagicMock(id="v1")]

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
    mock_replicate.models.get.return_value.versions.list.return_value = [mocker.MagicMock(id="v1")]

    with pytest.raises(ModelError):
        transcribe("test.ogg")
