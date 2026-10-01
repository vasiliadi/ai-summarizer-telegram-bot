import utils
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


def test_get_proxy_returns_empty_when_no_proxies(mocker):
    """Test get_proxy returns an empty string when no proxies are configured."""
    mocker.patch.object(utils, "PROXIES", [])
    assert utils.get_proxy() == ""


def test_get_proxy_returns_single_value(mocker):
    """Test get_proxy always returns the sole configured proxy."""
    mocker.patch.object(utils, "PROXIES", ["http://only:1"])
    for _ in range(5):
        assert utils.get_proxy() == "http://only:1"


def test_get_proxy_picks_from_list(mocker):
    """Test get_proxy selects a proxy from the configured pool at random."""
    pool = ["http://a:1", "http://b:2", "http://c:3"]
    mocker.patch.object(utils, "PROXIES", pool)
    mocker.patch("utils.random.choice", side_effect=pool)
    assert utils.get_proxy() == "http://a:1"
    assert utils.get_proxy() == "http://b:2"
    assert utils.get_proxy() == "http://c:3"


def test_clean_up_removes_an_unprotected_file(tmp_path, mocker):
    """Test that clean_up removes a single unprotected file."""
    file = tmp_path / "temp.mp3"
    file.touch()
    mocker.patch("utils.PROTECTED_FILES", [])

    clean_up(file=str(file))

    assert not file.exists()


def test_clean_up_keeps_a_protected_file(tmp_path, mocker):
    """Test that clean_up does not remove a file from the startup snapshot."""
    file = tmp_path / "utils.py"
    file.touch()
    mocker.patch("utils.PROTECTED_FILES", ["utils.py"])

    clean_up(file=str(file))

    assert file.exists()


def test_clean_up_no_args_is_noop(tmp_path, monkeypatch):
    """Test that clean_up() with no arguments removes nothing."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "temp.mp3").touch()

    clean_up()

    assert (tmp_path / "temp.mp3").exists()


def test_clean_up_all_downloads(tmp_path, monkeypatch, mocker):
    """Test that the sweep deletes only unprotected regular files in the CWD."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "temp.mp3").touch()
    (tmp_path / "protected.py").touch()
    (tmp_path / "dir").mkdir()
    mocker.patch("utils.PROTECTED_FILES", ["protected.py"])

    clean_up(all_downloads=True)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["dir", "protected.py"]
