from pathlib import Path

from config import PROTECTED_FILES
from utils import clean_up, compress_audio, generate_temporary_name


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
        text=True,
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
