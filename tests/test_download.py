import pytest
import requests

from download import download_castro, download_tg, download_yt
from services import choose_yt_audio_format


def test_download_tg_happy_path(mocker):
    """Test downloading a file from Telegram successfully."""
    mocker.patch("download.TG_API_TOKEN", "TEST_TOKEN")
    mock_resp = mocker.MagicMock()
    mock_resp.iter_content.return_value = [b"test ", b"content"]
    mock_resp.status_code = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_get = mocker.patch("download.requests.get", return_value=mock_resp)

    # Mock generate_temporary_name to return a fixed name
    mocker.patch("download.generate_temporary_name", return_value="temp_file.ext")

    mock_file = mocker.MagicMock()
    mock_file.file_path = "path/to/file"

    # We need to mock Path.open to avoid actual file system writes
    mock_path_open = mocker.patch("pathlib.Path.open", mocker.mock_open())

    result = download_tg(mock_file, ext=".ext")

    assert result == "temp_file.ext"
    mock_get.assert_called_once_with(
        "https://api.telegram.org/file/botTEST_TOKEN/path/to/file",
        stream=True,
        headers=mocker.ANY,
        verify=True,
        timeout=120,
    )
    mock_resp.iter_content.assert_called_once_with(chunk_size=8192)
    mock_resp.raise_for_status.assert_called_once()
    mock_path_open.assert_called_once_with("wb")
    mock_path_open().write.assert_has_calls(
        [
            mocker.call(b"test "),
            mocker.call(b"content"),
        ],
    )
    assert mock_path_open().write.call_count == 2


def test_download_tg_skips_empty_chunks(mocker):
    """Test download_tg skips empty chunks from iter_content."""
    mocker.patch("download.TG_API_TOKEN", "TEST_TOKEN")
    mock_resp = mocker.MagicMock()
    mock_resp.iter_content.return_value = [b"", b"data", b""]
    mock_resp.status_code = 200
    mock_resp.__enter__.return_value = mock_resp
    mocker.patch("download.requests.get", return_value=mock_resp)
    mocker.patch("download.generate_temporary_name", return_value="temp_file.ext")

    mock_file = mocker.MagicMock()
    mock_file.file_path = "path/to/file"

    mock_path_open = mocker.patch("pathlib.Path.open", mocker.mock_open())

    result = download_tg(mock_file, ext=".ext")

    assert result == "temp_file.ext"
    mock_resp.iter_content.assert_called_once_with(chunk_size=8192)
    mock_path_open().write.assert_has_calls([mocker.call(b"data")])
    assert mock_path_open().write.call_count == 1

def test_download_tg_missing_file_path(mocker):
    """Test download_tg raises ValueError when file_path is missing."""
    mock_file = mocker.MagicMock()
    mock_file.file_path = None

    with pytest.raises(ValueError, match="Telegram file path is missing."):
        download_tg(mock_file)

def test_download_yt_happy_path(mocker):
    """Test downloading a YouTube audio successfully."""
    mock_ydl = mocker.patch("download.YoutubeDL")
    mocker.patch("download.generate_temporary_name", return_value="temp_yt.mp3")

    info_ydl = mocker.MagicMock()
    info_ydl.extract_info.return_value = {
        "formats": [
            {"format_id": "251", "acodec": "opus", "vcodec": "none", "abr": 111, "tbr": 111},
            {"format_id": "139", "acodec": "mp4a.40.5", "vcodec": "none", "abr": 49, "tbr": 49},
        ],
    }
    download_ydl = mocker.MagicMock()
    mock_ydl.side_effect = [
        mocker.MagicMock(__enter__=mocker.MagicMock(return_value=info_ydl)),
        mocker.MagicMock(__enter__=mocker.MagicMock(return_value=download_ydl)),
    ]

    result = download_yt("https://youtube.com/watch?v=123")

    assert result == "temp_yt.mp3"
    info_ydl.extract_info.assert_called_once_with("https://youtube.com/watch?v=123", download=False)
    mock_ydl.assert_any_call({"proxy": mocker.ANY, "nocheckcertificate": False})
    mock_ydl.assert_any_call(
        {
            "format": "139",
            "outtmpl": "temp_yt",
            "nocheckcertificate": False,
            "proxy": mocker.ANY,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                },
            ],
        },
    )
    download_ydl.download.assert_called_once_with("https://youtube.com/watch?v=123")


def test_choose_yt_audio_format_falls_back_when_no_audio_only_formats():
    """Test selector fallback when yt-dlp has no audio-only format ids."""
    info = {
        "formats": [
            {"format_id": "18", "acodec": "mp4a.40.2", "vcodec": "avc1.42001E", "abr": 44, "tbr": 365},
        ],
    }

    result = choose_yt_audio_format(info)

    assert result == "bestaudio/worst[acodec!=none]"


def test_choose_yt_audio_format_ranks_missing_bitrates_last():
    """Test choose_yt_audio_format keeps numeric 0 bitrates ahead of missing values."""
    info = {
        "formats": [
            {"format_id": "unknown", "acodec": "opus", "vcodec": "none"},
            {"format_id": "zero", "acodec": "mp4a.40.5", "vcodec": "none", "abr": 0, "tbr": 0},
            {"format_id": "known", "acodec": "mp4a.40.5", "vcodec": "none", "abr": 49, "tbr": 49},
        ],
    }

    result = choose_yt_audio_format(info)

    assert result == "zero"

def test_download_castro_happy_path(mocker):
    """Test downloading a Castro podcast successfully."""
    mocker.patch("download.generate_temporary_name", return_value="temp_castro.mp3")

    # Mock requests.get for the page content
    mock_page_resp = mocker.MagicMock()
    mock_page_resp.content = b'<html><source src="https://audio.link/file.mp3"></html>'

    # Mock requests.get for the audio download
    mock_audio_resp = mocker.MagicMock()
    mock_audio_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
    mock_audio_resp.status_code = 200

    # Side effect for the two requests.get calls
    mock_audio_resp.__enter__.return_value = mock_audio_resp
    mocker.patch("download.requests.get", side_effect=[mock_page_resp, mock_audio_resp])
    mocker.patch("download.requests.utils.requote_uri", side_effect=lambda x: x)

    # Mock Path.open
    mock_path_open = mocker.patch("pathlib.Path.open", mocker.mock_open())

    result = download_castro("https://castro.fm/episode/123")

    assert result == "temp_castro.mp3"
    mock_audio_resp.iter_content.assert_called_once_with(chunk_size=8192)
    mock_audio_resp.raise_for_status.assert_called_once()
    mock_path_open.assert_called_once_with("wb")
    mock_path_open().write.assert_has_calls(
        [
            mocker.call(b"chunk1"),
            mocker.call(b"chunk2"),
        ],
    )
    assert mock_path_open().write.call_count == 2

def test_download_castro_missing_source_tag(mocker):
    """Test download_castro raises ValueError when <source> tag is missing."""
    mock_page_resp = mocker.MagicMock()
    mock_page_resp.content = b"<html><body>No source here</body></html>"
    mocker.patch("download.requests.get", return_value=mock_page_resp)
    mocker.patch("download.requests.utils.requote_uri", side_effect=lambda x: x)

    with pytest.raises(ValueError, match="Audio source tag not found in Castro page."):
        download_castro("https://castro.fm/episode/123")

def test_download_castro_missing_audio_url(mocker):
    """Test download_castro raises ValueError when source tag has no src."""
    mock_page_resp = mocker.MagicMock()
    mock_page_resp.content = b"<html><source></html>"
    mocker.patch("download.requests.get", return_value=mock_page_resp)
    mocker.patch("download.requests.utils.requote_uri", side_effect=lambda x: x)

    with pytest.raises(ValueError, match="Audio URL not found in Castro page."):
        download_castro("https://castro.fm/episode/123")


def test_download_castro_http_error(mocker):
    """Test download_castro logs status code and re-raises HTTPError."""
    mocker.patch("download.generate_temporary_name", return_value="temp_castro.mp3")

    mock_page_resp = mocker.MagicMock()
    mock_page_resp.content = b'<html><source src="https://audio.link/file.mp3"></html>'

    mock_audio_resp = mocker.MagicMock()
    mock_audio_resp.status_code = 500
    mock_audio_resp.__enter__.return_value = mock_audio_resp
    mock_audio_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

    mocker.patch("download.requests.get", side_effect=[mock_page_resp, mock_audio_resp])
    mocker.patch("download.requests.utils.requote_uri", side_effect=lambda x: x)
    mock_logger = mocker.patch("download.logger")

    with pytest.raises(requests.exceptions.HTTPError):
        download_castro("https://castro.fm/episode/123")

    mock_logger.exception.assert_called_once_with("%s: status code", 500)


def test_download_tg_http_error(mocker):
    """Test download_tg logs status code and re-raises HTTPError."""
    mocker.patch("download.TG_API_TOKEN", "TEST_TOKEN")
    mocker.patch("download.generate_temporary_name", return_value="temp_file.ext")

    mock_file = mocker.MagicMock()
    mock_file.file_path = "path/to/file"

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 403
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
    mocker.patch("download.requests.get", return_value=mock_resp)
    mock_logger = mocker.patch("download.logger")

    with pytest.raises(requests.exceptions.HTTPError):
        download_tg(mock_file, ext=".ext")

    mock_logger.exception.assert_called_once_with("%s: status code", 403)
