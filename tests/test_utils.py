from pathlib import Path

from config import PROTECTED_FILES
from utils import classify_url, clean_up, compress_audio, generate_temporary_name


def test_classify_url_uppercase_youtube_host():
    """Test classify_url normalises uppercase YouTube hostnames to 'youtube'."""
    assert classify_url("https://YOUTU.BE/dQw4w9WgXcQ") == "youtube"
    assert classify_url("https://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ") == "youtube"


def test_classify_url_strips_www_prefix():
    """Test classify_url routes www-prefixed media hosts to their media kind.

    Regression: routing used to be duplicated, and the second classifier matched
    three literal lowercase prefixes. A www-prefixed Castro or youtu.be link was
    classified as media in handlers, then failed the second check and reached the
    Gemini file upload with the URL string as its file path.
    """
    assert classify_url("https://www.castro.fm/episode/123") == "castro"
    assert classify_url("https://www.youtu.be/dQw4w9WgXcQ") == "youtube"


def test_classify_url_castro_non_episode_path_is_web():
    """Test classify_url only treats Castro /episode/ paths as media."""
    assert classify_url("https://castro.fm/about") == "web"


def test_classify_url_malformed_no_host():
    """Test classify_url returns None for URLs with no parseable hostname."""
    assert classify_url("https://") is None


def test_classify_url_rejects_non_http_scheme():
    """Test classify_url returns None for non-http(s) schemes."""
    assert classify_url("ftp://example.com/file.txt") is None


def test_classify_url_returns_none_for_unparseable_authority():
    """Test classify_url returns None when urlsplit rejects the authority.

    urlsplit raises ValueError on bracket-malformed hosts. Left uncaught it
    escapes handle_url's kind check and reaches handle_message's catch-all, so
    the user sees "Unexpected: ValueError" instead of "No data to proceed.".
    """
    assert classify_url("https://[") is None
    assert classify_url("http://[::1") is None


def test_classify_url_http_youtube_is_web():
    """Test classify_url only treats https media hosts as media."""
    assert classify_url("http://youtube.com/watch?v=dQw4w9WgXcQ") == "web"


def test_generate_temporary_name_no_ext():
    """Test generating a temporary name without an extension."""
    name = generate_temporary_name()
    assert isinstance(name, str)
    assert len(name) > 0
    # Should be 36 characters long (standard UUID format)
    assert len(name) == 36


def test_generate_temporary_name_with_ext():
    """Test generating a temporary name with an extension."""
    name = generate_temporary_name(".ogg")
    assert isinstance(name, str)
    assert name.endswith(".ogg")
    assert len(name) == 40  # 36 chars UUID + 4 chars extension


def test_compress_audio_calls_ffmpeg(mocker):
    """Test that compress_audio calls subprocess.run with correct arguments."""
    mock_run = mocker.patch("subprocess.run")

    input_file = "test_input.mp3"
    output_file = "test_output.ogg"

    compress_audio(input_file, output_file)

    expected_args = [
        "ffmpeg",
        "-y",
        "-i",
        input_file,
        "-vn",
        "-ac",
        "1",
        "-c:a",
        "libopus",
        "-b:a",
        "16k",
        output_file,
    ]

    mock_run.assert_called_once_with(
        expected_args,
        check=True,
        capture_output=False,
    )


def test_clean_up_single_file_unprotected(mocker):
    """Test that clean_up removes a single unprotected file."""
    mock_path = mocker.MagicMock(spec=Path)
    mock_path.is_file.return_value = True
    mock_path.name = "unprotected_temp.mp3"

    # We patch Path instantiation to return our mock path
    mocker.patch("utils.Path", return_value=mock_path)
    # We also need to patch Path.unlink since it's called on the class/instance
    mock_unlink = mocker.patch("utils.Path.unlink")

    clean_up(file="unprotected_temp.mp3")

    # It should have unlinked our mock_path object
    mock_unlink.assert_called_once_with(mock_path)


def test_clean_up_single_file_protected(mocker):
    """Test that clean_up does not remove a protected file."""
    mock_path = mocker.MagicMock(spec=Path)
    mock_path.is_file.return_value = True
    # Choose a file that is typically in PROTECTED_FILES
    if PROTECTED_FILES:
        mock_path.name = PROTECTED_FILES[0]
    else:
        # Fallback if list is empty in test environment
        mock_path.name = "utils.py"

    mocker.patch("utils.Path", return_value=mock_path)
    mock_unlink = mocker.patch("utils.Path.unlink")

    # We force PROTECTED_FILES to have our mock_path.name so the check fails
    mocker.patch("utils.PROTECTED_FILES", [mock_path.name])

    clean_up(file=mock_path.name)

    # It should NOT have unlinked
    mock_unlink.assert_not_called()


def test_clean_up_no_args_is_noop(mocker):
    """Test that clean_up() with no arguments does nothing."""
    mock_unlink = mocker.patch("utils.Path.unlink")

    clean_up()

    mock_unlink.assert_not_called()


def test_clean_up_all_downloads(mocker):
    """Test that clean_up(all_downloads=True) only deletes unprotected files."""
    # Create mock paths
    file1 = mocker.MagicMock(spec=Path)
    file1.is_file.return_value = True
    file1.name = "unprotected1.mp3"

    file2 = mocker.MagicMock(spec=Path)
    file2.is_file.return_value = True
    file2.name = "protected.py"

    file3 = mocker.MagicMock(spec=Path)
    file3.is_file.return_value = False  # Not a file (e.g. directory)
    file3.name = "dir"

    mock_cwd = mocker.patch("utils.Path.cwd")
    mock_cwd.return_value.iterdir.return_value = [file1, file2, file3]

    mocker.patch("utils.PROTECTED_FILES", ["protected.py"])
    mock_unlink = mocker.patch("utils.Path.unlink")

    clean_up(all_downloads=True)

    # Only file1 should have been unlinked
    mock_unlink.assert_called_once_with(file1)
