from types import SimpleNamespace

import pytest
from google.genai.errors import ClientError
from tenacity import RetryError
from youtube_transcript_api._errors import TranscriptsDisabled

from services import resolve_mime_type
from summary import (
    format_prefixed_summary,
    summarize,
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
    """Test the complete summarize_with_file flow with mocked Gemini clients."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_uploaded_file = SimpleNamespace(
        name="files/mock123",
        uri="https://generativelanguage.googleapis.com/v1beta/files/mock123",
        mime_type="audio/ogg",
        state="ACTIVE",
    )
    mock_client.files.upload.return_value = mock_uploaded_file
    mock_response = mocker.MagicMock(text="This is a mocked summary of the file.")
    mock_client.models.generate_content.return_value = mock_response

    result = summarize_with_file(
        file="test_audio.ogg",
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
    )

    assert result == "This is a mocked summary of the file."
    mock_client.files.upload.assert_called_once_with(
        file="test_audio.ogg",
        config={"mime_type": "audio/ogg"},
    )
    mock_client.files.delete.assert_called_once_with(name="files/mock123")


def test_summarize_with_file_retries_on_empty_response(mocker):
    """Test summarize_with_file raises RetryError on repeated empty Gemini responses."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mock_audio_file = SimpleNamespace(
        name="files/mock123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    mocker.patch("summary.upload_and_wait_for_audio_file", return_value=mock_audio_file)
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_client.models.generate_content.return_value = mocker.MagicMock(text=None)

    with pytest.raises(RetryError):
        summarize_with_file(
            file="test_audio.ogg",
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
        )


def test_summarize_with_file_retries_on_missing_upload_metadata(mocker):
    """Test summarize_with_file raises RetryError on repeated missing upload metadata."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mock_audio_file = SimpleNamespace(name=None, uri=None, mime_type="audio/ogg")
    mocker.patch("summary.upload_and_wait_for_audio_file", return_value=mock_audio_file)

    with pytest.raises(RetryError):
        summarize_with_file(
            file="test_audio.ogg",
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
        )


def test_summarize_with_transcript(mocker):
    """Test summarize_with_transcript functionality."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_client = mocker.patch("summary.gemini_client")
    mock_client.models.generate_content.return_value = mocker.MagicMock(
        text="Transcript summary.",
    )

    result = summarize_with_transcript(
        transcript="Hello world. This is a transcript.",
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
    )

    assert result == "Transcript summary."


def test_format_prefixed_summary_preserves_blank_line():
    """Test prefixed summaries always include exactly one blank line."""
    assert format_prefixed_summary("📹", "\n- one\n- two\n") == "📹\n\n- one\n- two"


def test_summarize_webpage(mocker):
    """Test summarize_webpage functionality with URL context tools."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_client = mocker.patch("summary.gemini_client")
    mock_client.models.generate_content.return_value = mocker.MagicMock(
        text="Webpage summary.",
    )

    result = summarize_webpage(
        content="https://example.com",
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
    )

    assert result == "Webpage summary."
    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.tools is not None
    assert len(config.tools) == 1
    assert config.tools[0].url_context is not None
    assert config.system_instruction is not None
    assert "MANDATORY TOOL USAGE" in config.system_instruction
    assert "UrlContext" in config.system_instruction


def test_summarize_with_file_upload_failure(mocker):
    """Test summarize_with_file raises when file upload fails."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_services_client = mocker.patch("services.gemini_client")
    mock_services_client.files.upload.side_effect = Exception("Upload failed")

    with pytest.raises(Exception, match="Upload failed"):
        summarize_with_file(
            file="test_audio.ogg",
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
        )


def test_summarize_genai_exception(mocker):
    """Test summarize_with_transcript raises RetryError when Gemini crashes."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mock_client.models.generate_content.side_effect = ClientError(
        400,
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "GenAI unavailable",
            },
        },
    )

    with pytest.raises(RetryError):
        summarize_with_transcript(
            transcript="Hello",
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
        )


def test_summarize_with_document_polling(mocker):
    """Test summarize_with_document with PROCESSING polling loop."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("summary.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mock_file_proc = SimpleNamespace(state="PROCESSING", name="files/doc123")
    mock_file_active = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    mock_client.files.upload.return_value = mock_file_proc
    mock_client.files.get.return_value = mock_file_active
    mock_client.models.generate_content.return_value = mocker.MagicMock(
        text="Document summary",
    )
    mock_tg_file = mocker.MagicMock()

    result = summarize_with_document(
        file=mock_tg_file,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="application/pdf",
        user_id=123,
        daily_limit=10,
    )

    assert result == "Document summary"
    mock_client.files.delete.assert_called_once_with(name="files/doc123")


def test_summarize_with_document_cleans_up_on_failed_processing(mocker):
    """Test summarize_with_document cleans up the downloaded file on failure."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_client = mocker.patch("summary.gemini_client")
    mock_failed_file = SimpleNamespace(state="FAILED", name="files/doc123")
    mock_client.files.upload.return_value = mock_failed_file

    with pytest.raises(ValueError, match="FAILED"):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
        )

    mock_clean_up.assert_called_once_with(file="temp_doc.pdf")


def test_summarize_youtube_direct_transcript(mocker):
    """Test summarize() using direct YouTube transcript (📹 prefix)."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.get_yt_transcript", return_value="YT Transcript content")
    mock_sum_transcript = mocker.patch(
        "summary.summarize_with_transcript",
        return_value="- first point\n- second point",
    )

    result = summarize(
        data=url,
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        use_yt_transcription=True,
    )

    assert result.startswith("📹")
    assert result == "📹\n\n- first point\n- second point"
    mock_sum_transcript.assert_called_once()


def test_summarize_youtube_direct_transcript_uses_blank_line_separator(mocker):
    """Test YouTube transcript summaries keep a blank line after the prefix."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.get_yt_transcript", return_value="YT Transcript content")
    mocker.patch(
        "summary.summarize_with_transcript",
        return_value="- first point\n- second point",
    )

    result = summarize(
        data=url,
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        use_yt_transcription=True,
    )

    assert result == "📹\n\n- first point\n- second point"


def test_summarize_youtube_transcript_summary_retry_does_not_fall_back(mocker):
    """Test transcript summary retry errors do not trigger audio fallback paths."""
    url = "https://youtube.com/watch?v=123"
    retry_error = RetryError(mocker.MagicMock())
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.get_yt_transcript", return_value="YT Transcript content")
    mock_download = mocker.patch("summary.download_yt")
    mock_file_summary = mocker.patch("summary.summarize_with_file")
    mock_transcribe = mocker.patch("summary.transcribe")
    mocker.patch("summary.summarize_with_transcript", side_effect=retry_error)

    with pytest.raises(RetryError):
        summarize(
            data=url,
            use_transcription=True,
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            use_yt_transcription=True,
        )

    mock_download.assert_not_called()
    mock_file_summary.assert_not_called()
    mock_transcribe.assert_not_called()


def test_summarize_youtube_transcript_failure_falls_back_to_download(mocker):
    """Test summarize() falls back to downloading YouTube audio when transcript fetch fails."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.get_yt_transcript", side_effect=TranscriptsDisabled("123"))
    mock_download = mocker.patch("summary.download_yt", return_value="downloaded.ogg")
    mocker.patch("summary.summarize_with_file", return_value="File summary")
    mock_clean_up = mocker.patch("summary.clean_up")

    result = summarize(
        data=url,
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        use_yt_transcription=True,
    )

    assert result == "File summary"
    mock_download.assert_called_once_with(url)
    mock_clean_up.assert_called_once_with(file="downloaded.ogg")


def test_summarize_fallback_to_transcription(mocker):
    """Test summarize() fallback to transcription (📝 prefix) when file summary fails."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch(
        "summary.summarize_with_file",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio")
    mocker.patch("summary.transcribe", return_value="Transcription text")
    mocker.patch(
        "summary.summarize_with_transcript",
        return_value="- transcript point\n- follow-up point",
    )
    mock_clean_up = mocker.patch("summary.clean_up")

    result = summarize(
        data="local_audio.ogg",
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
    )

    assert result.startswith("📝")
    assert result == "📝\n\n- transcript point\n- follow-up point"
    mock_clean_up.assert_has_calls(
        [
            mocker.call(file="temp.ogg"),
            mocker.call(file="local_audio.ogg"),
        ],
    )


def test_summarize_reraises_when_transcription_fallback_disabled(mocker):
    """Test summarize() re-raises file-summary failures when transcription is disabled."""
    retry_error = RetryError(mocker.MagicMock())
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.summarize_with_file", side_effect=retry_error)
    mock_capture = mocker.patch("summary.capture_exception")
    mock_clean_up = mocker.patch("summary.clean_up")

    with pytest.raises(RetryError):
        summarize(
            data="local_audio.ogg",
            use_transcription=False,
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
        )

    mock_capture.assert_called_once_with(retry_error)
    mock_clean_up.assert_called_once_with(file="local_audio.ogg")


def test_summarize_castro(mocker):
    """Test summarize() with Castro.fm URL."""
    url = "https://castro.fm/episode/123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_castro", return_value="downloaded.mp3")
    mocker.patch("summary.summarize_with_file", return_value="Castro summary")
    mocker.patch("summary.clean_up")

    result = summarize(
        data=url,
        use_transcription=True,
        model="test-model",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
    )

    assert result == "Castro summary"


def test_summarize_preflight_blocks_before_download(mocker):
    """Test summarize() blocks zero-quota users before any network IO."""
    from exceptions import LimitExceededError

    mock_check = mocker.patch("summary.check_quota", side_effect=LimitExceededError)
    mock_download = mocker.patch("summary.download_castro")

    with pytest.raises(LimitExceededError):
        summarize(
            data="https://castro.fm/episode/123",
            use_transcription=False,
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=1,
            daily_limit=0,
        )

    mock_check.assert_called_once()
    mock_download.assert_not_called()


def test_summarize_with_file_deletes_gemini_file_when_quota_check_fails(mocker):
    """Test summarize_with_file cleans up the uploaded Gemini file if consuming check fails."""
    from exceptions import LimitExceededError
    from types import SimpleNamespace

    mock_audio_file = SimpleNamespace(
        name="files/audio123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    mocker.patch("summary.upload_and_wait_for_audio_file", return_value=mock_audio_file)
    mocker.patch("tenacity.nap.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("summary.check_quota", side_effect=[True, LimitExceededError])

    with pytest.raises(LimitExceededError):
        summarize_with_file(
            file="test_audio.ogg",
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=1,
            daily_limit=5,
        )

    mock_client.files.delete.assert_called_with(name="files/audio123")


def test_summarize_with_document_preflight_blocks_before_download(mocker):
    """Test summarize_with_document blocks zero-quota users before download or upload."""
    from exceptions import LimitExceededError

    mock_check = mocker.patch("summary.check_quota", side_effect=LimitExceededError)
    mock_download = mocker.patch("summary.download_tg")

    with pytest.raises(LimitExceededError):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="test-model",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=1,
            daily_limit=0,
        )

    mock_check.assert_called_once()
    mock_download.assert_not_called()
