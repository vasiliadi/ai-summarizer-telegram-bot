

import pytest

from download import download_castro, download_tg, download_yt


def test_download_tg_happy_path(mocker):
    """Test downloading a file from Telegram successfully."""
    mocker.patch("download.TG_API_TOKEN", "TEST_TOKEN")
    mock_resp = mocker.MagicMock()
    mock_resp.iter_content.return_value = [b"test ", b"content"]
    mock_resp.status_code = 200
    mock_resp.__enter__.return_value = mock_resp
    mocker.patch("download.requests.get", return_value=mock_resp)

    # Mock generate_temporary_name to return a fixed name
    mocker.patch("download.generate_temporary_name", return_value="temp_file.ext")

    mock_file = mocker.MagicMock()
    mock_file.file_path = "path/to/file"

    # We need to mock Path.open to avoid actual file system writes
    mock_path_open = mocker.patch("pathlib.Path.open", mocker.mock_open())

    result = download_tg(mock_file, ext=".ext")

    assert result == "temp_file.ext"
    mock_resp.raise_for_status.assert_called_once()
    mock_path_open.assert_called_once_with("wb")
    mock_path_open().write.assert_any_call(b"test ")
    mock_path_open().write.assert_any_call(b"content")

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

    result = download_yt("https://youtube.com/watch?v=123")

    assert result == "temp_yt.mp3"
    mock_ydl.return_value.__enter__.return_value.download.assert_called_once_with("https://youtube.com/watch?v=123")

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
    mock_audio_resp.raise_for_status.assert_called_once()
    mock_path_open.assert_called_once_with("wb")

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
