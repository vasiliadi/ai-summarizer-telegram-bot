
import pytest

from services import (
    get_file_with_retry,
    get_gemini_config,
    reply_with_retry,
    send_answer,
    upload_and_wait_for_audio_file,
)


def test_reply_with_retry_happy_path(mocker):
    """Test reply_with_retry sends message successfully."""
    mock_bot = mocker.patch("services.bot")
    mock_msg = mocker.MagicMock()

    reply_with_retry(mock_msg, "hello")

    mock_bot.reply_to.assert_called_once_with(mock_msg, "hello")

def test_reply_with_retry_with_entities(mocker):
    """Test reply_with_retry sends message with entities."""
    mock_bot = mocker.patch("services.bot")
    mock_msg = mocker.MagicMock()
    entities = [{"type": "bold"}]

    reply_with_retry(mock_msg, "hello", entities=entities)

    mock_bot.reply_to.assert_called_once_with(mock_msg, "hello", entities=entities)

def test_get_file_with_retry_success(mocker):
    """Test get_file_with_retry retrieves file info."""
    mock_bot = mocker.patch("services.bot")
    mock_bot.get_file.return_value = "mock_file"

    result = get_file_with_retry("id123")

    assert result == "mock_file"
    mock_bot.get_file.assert_called_once_with("id123")

def test_send_answer_single_chunk(mocker):
    """Test send_answer with a short message (single chunk)."""
    mock_convert = mocker.patch("services.convert", return_value=("text", []))
    # Mock split_entities to return one chunk
    mock_entity = mocker.MagicMock()
    mock_entity.to_dict.return_value = {"type": "bold"}
    mock_split = mocker.patch("services.split_entities", return_value=[("text", [mock_entity])])

    mock_reply = mocker.patch("services.reply_with_retry")
    mock_msg = mocker.MagicMock()

    send_answer(mock_msg, "short answer")

    mock_convert.assert_called_once_with("short answer")
    mock_reply.assert_called_once_with(mock_msg, "text", entities=[{"type": "bold"}])

def test_send_answer_multi_chunk(mocker):
    """Test send_answer with a long message (multiple chunks)."""
    mocker.patch("services.convert", return_value=("text", []))
    mocker.patch("services.split_entities", return_value=[("part1", []), ("part2", [])])
    mock_reply = mocker.patch("services.reply_with_retry")
    mocker.patch("services.time.sleep")

    mock_msg = mocker.MagicMock()
    send_answer(mock_msg, "long answer")

    assert mock_reply.call_count == 2

def test_get_gemini_config_content():
    """Test get_gemini_config includes the correct language in instruction."""
    config = get_gemini_config("French")
    assert "French" in config.system_instruction

def test_upload_and_wait_for_audio_file_happy(mocker):
    """Test uploading file to Gemini when it's immediately ACTIVE."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "ACTIVE"
    mock_file.uri = "uri"
    mock_file.mime_type = "audio/ogg"

    mock_client.files.upload.return_value = mock_file

    result = upload_and_wait_for_audio_file("path", "audio/ogg", 1)

    assert result == mock_file
    mock_client.files.upload.assert_called_once()

def test_upload_and_wait_for_audio_file_polling(mocker):
    """Test uploading file to Gemini with polling (PROCESSING -> ACTIVE)."""
    mock_client = mocker.patch("services.gemini_client")
    mocker.patch("services.time.sleep")

    mock_file_proc = mocker.MagicMock()
    mock_file_proc.name = "name"
    mock_file_proc.state = "PROCESSING"

    mock_file_active = mocker.MagicMock()
    mock_file_active.name = "name"
    mock_file_active.state = "ACTIVE"
    mock_file_active.uri = "uri"
    mock_file_active.mime_type = "audio/ogg"

    mock_client.files.upload.return_value = mock_file_proc
    mock_client.files.get.return_value = mock_file_active

    result = upload_and_wait_for_audio_file("path", "audio/ogg", 1)

    assert result == mock_file_active
    mock_client.files.get.assert_called_once_with(name="name")

def test_upload_and_wait_for_audio_file_failed(mocker):
    """Test upload_and_wait_for_audio_file raises ValueError on FAILED state."""
    mock_client = mocker.patch("services.gemini_client")
    mock_file = mocker.MagicMock()
    mock_file.name = "name"
    mock_file.state = "FAILED"
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(ValueError, match="FAILED"):
        upload_and_wait_for_audio_file("path", "audio/ogg", 1)
