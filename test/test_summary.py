
import pytest
from google.genai.errors import ClientError
from tenacity import RetryError

from services import resolve_mime_type
from summary import (
    summarize_webpage,
    summarize_with_document,
    summarize_with_file,
    summarize_with_transcript,
)


def test_resolve_mime_type():
    """Test that resolve_mime_type correctly maps file extensions to MIME types."""
    assert resolve_mime_type("document.pdf") == "application/pdf"
    assert resolve_mime_type("data.csv") == "text/csv"
    assert resolve_mime_type("text.rtf") == "application/rtf"
    assert resolve_mime_type("audio.ogg") == "audio/ogg"
    assert resolve_mime_type("audio.mp3") == "audio/mpeg"
    assert resolve_mime_type("video.mp4") == "video/mp4"
    assert resolve_mime_type("unknown.bin") == "application/octet-stream"


def test_summarize_with_file_upload_and_genai_call(mocker):
    """Test the complete summarize_with_file flow with mocked google-genai client."""
    # Mock quota checker to avoid hitting Redis or real limits
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("services.check_quota", return_value=True)

    # Mock Gemini Client and its nested attributes
    mock_client = mocker.patch("summary.gemini_client")
    mock_services_client = mocker.patch("services.gemini_client")

    # Mock the uploaded file object
    mock_uploaded_file = mocker.MagicMock()
    mock_uploaded_file.name = "files/mock123"
    mock_uploaded_file.uri = "https://generativelanguage.googleapis.com/v1beta/files/mock123"
    mock_uploaded_file.mime_type = "audio/ogg"
    mock_uploaded_file.state = "ACTIVE"  # Skips polling loop

    mock_services_client.files.upload.return_value = mock_uploaded_file

    # Mock the generated content response
    mock_response = mocker.MagicMock()
    mock_response.text = "This is a mocked summary of the file."
    mock_client.models.generate_content.return_value = mock_response

    # Call the function
    result = summarize_with_file(
        file="test_audio.ogg",
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
    )

    # Asserts
    assert result == "This is a mocked summary of the file."

    # Assert upload was called with correct mime type resolved
    mock_services_client.files.upload.assert_called_once_with(
        file="test_audio.ogg",
        config={"mime_type": "audio/ogg"},
    )

    # Assert generate_content was called
    mock_client.models.generate_content.assert_called_once()

    # Assert cleanup was called
    mock_client.files.delete.assert_called_once_with(name="files/mock123")


def test_summarize_with_transcript(mocker):
    """Test summarize_with_transcript functionality."""
    mocker.patch("summary.check_quota", return_value=True)

    mock_client = mocker.patch("summary.gemini_client")
    mock_response = mocker.MagicMock()
    mock_response.text = "Transcript summary."
    mock_client.models.generate_content.return_value = mock_response

    result = summarize_with_transcript(
        transcript="Hello world. This is a transcript.",
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
    )

    assert result == "Transcript summary."
    mock_client.models.generate_content.assert_called_once()


def test_summarize_webpage(mocker):
    """Test summarize_webpage functionality with URL context tools."""
    mocker.patch("summary.check_quota", return_value=True)

    mock_client = mocker.patch("summary.gemini_client")
    mock_response = mocker.MagicMock()
    mock_response.text = "Webpage summary."
    mock_client.models.generate_content.return_value = mock_response

    result = summarize_webpage(
        content="https://example.com",
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
    )

    assert result == "Webpage summary."

    # Verify generate_content was called
    mock_client.models.generate_content.assert_called_once()

    # Extract the passed config and verify tools were set
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert "config" in call_kwargs


def test_summarize_with_file_upload_failure(mocker):
    """Test summarize_with_file raises when file upload fails."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("services.check_quota", return_value=True)

    # Mock Gemini Client and its nested attributes
    mock_services_client = mocker.patch("services.gemini_client")
    mock_services_client.files.upload.side_effect = Exception("Upload failed")

    with pytest.raises(Exception, match="Upload failed"):
        summarize_with_file(
            file="test_audio.ogg",
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
        )


def test_summarize_genai_exception(mocker):
    """Test summarize_with_transcript raises RetryError when GenAI crashes."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_client = mocker.patch("summary.gemini_client")
    # Patch tenacity's sleep to avoid hanging during retries
    mocker.patch("tenacity.nap.time.sleep")

    # Tenacity `retry` block raises RetryError when all attempts are exhausted. To test the bare
    # generate_content raises this, we'll patch generate_content.
    mock_client.models.generate_content.side_effect = ClientError("GenAI unavailable", 400, {})

    with pytest.raises(RetryError):
        summarize_with_transcript(
            transcript="Hello",
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
        )


def test_summarize_with_document_polling(mocker):
    """Test summarize_with_document with PROCESSING polling loop."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("time.sleep")  # Skip actual sleeping

    mock_client = mocker.patch("summary.gemini_client")

    # First call: PROCESSING, Second call: ACTIVE
    mock_file_proc = mocker.MagicMock()
    mock_file_proc.state = "PROCESSING"
    mock_file_proc.name = "files/doc123"

    mock_file_active = mocker.MagicMock()
    mock_file_active.state = "ACTIVE"
    mock_file_active.name = "files/doc123"
    mock_file_active.uri = "https://mock.uri"
    mock_file_active.mime_type = "application/pdf"

    mock_client.files.upload.return_value = mock_file_proc
    mock_client.files.get.return_value = mock_file_active

    mock_response = mocker.MagicMock()
    mock_response.text = "Document summary"
    mock_client.models.generate_content.return_value = mock_response

    from telebot.types import File
    mock_tg_file = mocker.MagicMock(spec=File)

    result = summarize_with_document(
        file=mock_tg_file,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="application/pdf",
    )

    assert result == "Document summary"
    assert mock_client.files.get.call_count == 1
    mock_client.files.delete.assert_called_once_with(name="files/doc123")


def test_summarize_youtube_direct_transcript(mocker):
    """Test summarize() using direct YouTube transcript (📹 prefix)."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.get_yt_transcript", return_value="YT Transcript content")
    mock_sum_transcript = mocker.patch("summary.summarize_with_transcript", return_value="Summary Result")

    from summary import summarize
    result = summarize(
        data=url,
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        use_yt_transcription=True,
    )

    assert result.startswith("📹")
    assert "Summary Result" in result
    mock_sum_transcript.assert_called_once()


def test_summarize_fallback_to_transcription(mocker):
    """Test summarize() fallback to transcription (📝 prefix) when file summary fails."""
    # Data is a local file (or downloaded)
    mocker.patch("summary.summarize_with_file", side_effect=RetryError("File summary failed"))
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio")
    mocker.patch("summary.transcribe", return_value="Transcription text")
    mocker.patch("summary.summarize_with_transcript", return_value="Transcript Summary")
    mocker.patch("summary.clean_up")

    from summary import summarize
    result = summarize(
        data="local_audio.ogg",
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
    )

    assert result.startswith("📝")
    assert "Transcript Summary" in result


def test_summarize_castro(mocker):
    """Test summarize() with Castro.fm URL."""
    url = "https://castro.fm/episode/123"
    mocker.patch("summary.download_castro", return_value="downloaded.mp3")
    mocker.patch("summary.summarize_with_file", return_value="Castro summary")
    mocker.patch("summary.clean_up")

    from summary import summarize
    result = summarize(
        data=url,
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
    )

    assert result == "Castro summary"
