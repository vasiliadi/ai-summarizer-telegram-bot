from types import SimpleNamespace

import pytest
from pydantic_ai import UploadedFile
from pydantic_ai.exceptions import ModelHTTPError
from telebot.types import File
from tenacity import RetryError

import summary as summary_module
from config import ModelSpec
from domain import PrefixedText
from exceptions import FetchTranscriptError, LimitExceededError
from summary import (
    format_prefixed_summary,
    summarize,
    summarize_text,
    summarize_with_document,
    summarize_with_file,
)


def test_summarize_with_file_upload_and_model_call(mocker):
    """Test the complete summarize_with_file flow with the file API and model mocked."""
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
    mock_run = mocker.patch(
        "summary.run_model",
        return_value="This is a mocked summary of the file.",
    )

    result = summarize_with_file(
        file="test_audio.ogg",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "This is a mocked summary of the file."
    mock_client.files.upload.assert_called_once_with(
        file="test_audio.ogg",
        config={"mime_type": "audio/ogg"},
    )
    mock_client.files.delete.assert_called_once_with(name="files/mock123")
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["model_id"] == "gemini-3.5-flash-lite"
    assert call_kwargs["target_language"] == "English"
    assert call_kwargs["thinking_level"] == "MINIMAL"
    prompt, uploaded = call_kwargs["content"]
    assert "detailed summary" in prompt
    assert isinstance(uploaded, UploadedFile)
    assert uploaded.file_id == mock_uploaded_file.uri


def test_summarize_with_file_retries_on_empty_response(mocker):
    """Test summarize_with_file raises RetryError on repeated empty model responses."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mock_audio_file = SimpleNamespace(
        name="files/mock123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    mocker.patch("summary.upload_and_wait_for_file", return_value=mock_audio_file)
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mocker.patch("summary.run_model", side_effect=AttributeError)

    with pytest.raises(RetryError):
        summarize_with_file(
            file="test_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )


def test_summarize_text_from_transcript(mocker):
    """Test summarize_text feeds a transcript to the model."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.run_model", return_value="Transcript summary.")

    result = summarize_text(
        text="Hello world. This is a transcript.",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "Transcript summary."


def test_format_prefixed_summary_preserves_blank_line():
    """Test prefixed summaries always include exactly one blank line."""
    assert format_prefixed_summary("📹", "\n- one\n- two\n") == "📹\n\n- one\n- two"


def test_summarize_text_from_webpage(mocker):
    """Test summarize_text sends pre-parsed webpage content as a plain prompt."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_run = mocker.patch("summary.run_model", return_value="Webpage summary.")

    result = summarize_text(
        text="Parsed page content.",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "Webpage summary."
    call_kwargs = mock_run.call_args.kwargs
    # A bare string, not a content list: the text path stays provider-agnostic.
    assert isinstance(call_kwargs["content"], str)
    assert "Parsed page content." in call_kwargs["content"]
    assert call_kwargs["model_id"] == "gemini-3.5-flash-lite"


def test_summarize_with_file_upload_failure(mocker):
    """Test summarize_with_file raises when file upload fails."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_services_client = mocker.patch("services.gemini_client")
    mock_services_client.files.upload.side_effect = Exception("Upload failed")

    with pytest.raises(Exception, match="Upload failed"):
        summarize_with_file(
            file="test_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )


def test_summarize_model_api_exception(mocker):
    """Test summarize_text raises RetryError when the provider returns an error."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch(
        "summary.run_model",
        side_effect=ModelHTTPError(
            status_code=400,
            model_name="gemini-3.5-flash-lite",
            body={"error": {"message": "Model unavailable"}},
        ),
    )

    with pytest.raises(RetryError):
        summarize_text(
            text="Hello",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )


def test_summarize_with_document_polling(mocker):
    """Test summarize_with_document with PROCESSING polling loop."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("services.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_file_proc = SimpleNamespace(state="PROCESSING", name="files/doc123")
    mock_file_active = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    mock_client.files.upload.return_value = mock_file_proc
    mock_client.files.get.return_value = mock_file_active
    mock_run = mocker.patch("summary.run_model", return_value="Document summary")
    mock_tg_file = mocker.MagicMock()

    result = summarize_with_document(
        file=mock_tg_file,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="application/pdf",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "Document summary"
    mock_client.files.delete.assert_called_once_with(name="files/doc123")
    _, uploaded = mock_run.call_args.kwargs["content"]
    assert isinstance(uploaded, UploadedFile)
    assert uploaded.file_id == "https://mock.uri"
    assert uploaded.media_type == "application/pdf"


def test_summarize_with_document_cleans_up_on_failed_processing(mocker):
    """Test summarize_with_document cleans up the downloaded file on failure."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch("services.time.sleep")
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_failed_file = SimpleNamespace(state="FAILED", name="files/doc123")
    mock_client.files.upload.return_value = mock_failed_file

    with pytest.raises(ValueError, match="FAILED"):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )

    mock_clean_up.assert_called_once_with(file="temp_doc.pdf")


def test_summarize_youtube_always_attempts_transcript(mocker):
    """get_yt_transcript is always called for YouTube URLs (no user toggle)."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.check_quota", return_value=True)
    mock_get_transcript = mocker.patch(
        "summary.get_yt_transcript",
        return_value=SimpleNamespace(text="YT Transcript", prefix="📹"),
    )
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        return_value="Summary",
    )

    summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    mock_get_transcript.assert_called_once_with(url)


def test_summarize_youtube_direct_transcript(mocker):
    """Test summarize() using direct YouTube transcript (📹 prefix)."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch(
        "summary.get_yt_transcript",
        return_value=SimpleNamespace(text="YT Transcript content", prefix="📹"),
    )
    mock_sum_transcript = mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        return_value="- first point\n- second point",
    )

    result = summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result.startswith("📹")
    assert result == "📹\n\n- first point\n- second point"
    mock_sum_transcript.assert_called_once_with(
        text="YT Transcript content",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )


def test_summarize_youtube_fallback_transcript_uses_fallback_prefix(mocker):
    """Test fallback YouTube transcript summaries use the 📺 prefix."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch(
        "summary.get_yt_transcript",
        return_value=SimpleNamespace(text="YT Transcript content", prefix="📺"),
    )
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        return_value="- first point\n- second point",
    )

    result = summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "📺\n\n- first point\n- second point"


def test_summarize_youtube_transcript_summary_retry_does_not_fall_back(mocker):
    """Test transcript summary retry errors do not trigger audio fallback paths."""
    url = "https://youtube.com/watch?v=123"
    retry_error = RetryError(mocker.MagicMock())
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch(
        "summary.get_yt_transcript",
        return_value=SimpleNamespace(text="YT Transcript content", prefix="📹"),
    )
    mock_download = mocker.patch("summary.download_yt")
    mock_file_summary = mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
    )
    mock_transcribe = mocker.patch("summary.transcribe")
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        side_effect=retry_error,
    )

    with pytest.raises(RetryError):
        summarize(
            data=url,
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )

    mock_download.assert_not_called()
    mock_file_summary.assert_not_called()
    mock_transcribe.assert_not_called()


@pytest.mark.parametrize(
    "transcript_error",
    [
        FetchTranscriptError("transcript failed"),
        ValueError("no transcript"),
    ],
)
def test_summarize_youtube_transcript_failure_falls_back_to_download(
    mocker,
    transcript_error,
):
    """Test summarize() falls back to downloading YouTube audio when transcript fetch fails."""
    url = "https://youtube.com/watch?v=123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.get_yt_transcript", side_effect=transcript_error)
    mock_download = mocker.patch("summary.download_yt", return_value="downloaded.ogg")
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
        return_value="File summary",
    )
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_logger = mocker.patch("summary.logger")

    result = summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "File summary"
    mock_download.assert_called_once_with(url)
    mock_clean_up.assert_called_once_with(file="downloaded.ogg")
    mock_logger.warning.assert_called_once_with(
        "get_yt_transcript failed, falling back to download: %s",
        mocker.ANY,
    )


def test_summarize_fallback_to_transcription(mocker):
    """Test summarize() fallback to transcription (📝 prefix) when file summary fails."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio")
    mocker.patch("summary.transcribe", return_value="Transcription text")
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        return_value="- transcript point\n- follow-up point",
    )
    mock_clean_up = mocker.patch("summary.clean_up")

    result = summarize(
        data="local_audio.ogg",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result.startswith("📝")
    assert result == "📝\n\n- transcript point\n- follow-up point"
    mock_clean_up.assert_has_calls(
        [
            mocker.call(file="temp.ogg"),
            mocker.call(file="local_audio.ogg"),
        ],
    )


def test_summarize_routes_audio_around_a_model_that_cannot_read_it(mocker):
    """Test a text-only model transcribes audio instead of uploading it.

    No model in MODEL_SPECS is text-only today, so the registry is patched with a
    synthetic spec — this is the branch a non-audio provider would light up.
    """
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch.dict(
        summary_module.MODEL_SPECS,
        {
            "text-only-1": ModelSpec(
                label="Text Only 1",
                provider="google",
                supports_audio=False,
            ),
        },
    )
    mock_with_file = mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
    )
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mock_compress = mocker.patch("summary.compress_audio")
    mocker.patch("summary.transcribe", return_value="Transcription text")
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        return_value="- transcript point",
    )
    mocker.patch("summary.clean_up")

    result = summarize(
        data="local_audio.ogg",
        model="text-only-1",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "📝\n\n- transcript point"
    mock_with_file.assert_not_called()
    mock_compress.assert_called_once_with(
        input_file="local_audio.ogg",
        output_file="temp.ogg",
    )


def test_summarize_with_document_routes_audio_document_to_transcription(mocker):
    """Test an audio document reaches the transcription path on a text-only model.

    SUPPORTED_DOCUMENT_MIME_TYPES accepts audio/ogg, so the document path needs
    the same modality check as summarize().
    """
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch.dict(
        summary_module.MODEL_SPECS,
        {
            "text-only-1": ModelSpec(
                label="Text Only 1",
                provider="google",
                supports_audio=False,
            ),
        },
    )
    mock_download = mocker.patch("summary.download_tg", return_value="voice.ogg")
    mock_upload = mocker.patch("summary.upload_and_wait_for_file")
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio")
    mocker.patch("summary.transcribe", return_value="Transcription text")
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        return_value="- transcript point",
    )
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_tg_file = mocker.MagicMock()

    result = summarize_with_document(
        file=mock_tg_file,
        model="text-only-1",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="audio/ogg",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "📝\n\n- transcript point"
    mock_upload.assert_not_called()
    mock_download.assert_called_once_with(mock_tg_file, ext=".ogg")
    mock_clean_up.assert_has_calls(
        [
            mocker.call(file="temp.ogg"),
            mocker.call(file="voice.ogg"),
        ],
    )


def test_summarize_fallback_cleans_up_temp_file_when_compress_fails(mocker):
    """Test summarize() cleans up the temp file even if compress_audio raises."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio", side_effect=RuntimeError("ffmpeg failed"))
    mock_clean_up = mocker.patch("summary.clean_up")

    with pytest.raises(RuntimeError):
        summarize(
            data="local_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )

    mock_clean_up.assert_any_call(file="temp.ogg")


def test_summarize_castro(mocker):
    """Test summarize() with Castro.fm URL."""
    url = "https://castro.fm/episode/123"
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_castro", return_value="downloaded.mp3")
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
        return_value="Castro summary",
    )
    mocker.patch("summary.clean_up")

    result = summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "Castro summary"


def test_summarize_castro_www_host(mocker):
    """Test summarize() downloads a www-prefixed Castro URL instead of uploading it.

    Regression: the URL used to be re-classified with a literal
    "https://castro.fm/episode/" prefix check, so a www-prefixed link skipped
    download_castro and was passed to summarize_with_file as a file path.
    """
    mocker.patch("summary.check_quota", return_value=True)
    mock_download = mocker.patch("summary.download_castro", return_value="dl.mp3")
    mock_with_file = mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
        return_value="Castro summary",
    )
    mocker.patch("summary.clean_up")

    result = summarize(
        data="https://www.castro.fm/episode/123",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "Castro summary"
    mock_download.assert_called_once_with("https://www.castro.fm/episode/123")
    assert mock_with_file.call_args.kwargs["file"] == "dl.mp3"


def test_summarize_youtube_uppercase_host_uses_transcript(mocker):
    """Test summarize() routes an uppercase-host YouTube URL to the transcript path.

    Regression: the old literal prefix check was case-sensitive, so an
    uppercase host bypassed the transcript path entirely.
    """
    url = "https://YouTube.com/watch?v=dQw4w9WgXcQ"
    mocker.patch("summary.check_quota", return_value=True)
    mock_transcript = mocker.patch(
        "summary.get_yt_transcript",
        return_value=PrefixedText(text="transcript text", prefix="📺"),
    )
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_text",
        return_value="YT summary",
    )
    mock_with_file = mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
    )

    result = summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "📺\n\nYT summary"
    mock_transcript.assert_called_once_with(url)
    mock_with_file.assert_not_called()


def test_summarize_preflight_blocks_before_download(mocker):
    """Test summarize() blocks zero-quota users before any network IO."""
    mock_check = mocker.patch("summary.check_quota", side_effect=LimitExceededError)
    mock_download = mocker.patch("summary.download_castro")

    with pytest.raises(LimitExceededError):
        summarize(
            data="https://castro.fm/episode/123",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=1,
            daily_limit=0,
            thinking_level="MINIMAL",
        )

    mock_check.assert_called_once_with(user_id=1, daily_limit=0, quantity=0)
    mock_download.assert_not_called()


def test_summarize_with_file_deletes_gemini_file_when_quota_check_fails(mocker):
    """Test summarize_with_file cleans up the uploaded Gemini file if consuming check fails."""
    mock_audio_file = SimpleNamespace(
        name="files/audio123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    mocker.patch("summary.upload_and_wait_for_file", return_value=mock_audio_file)
    mocker.patch("tenacity.nap.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mock_check = mocker.patch(
        "summary.check_quota",
        side_effect=[True, LimitExceededError],
    )

    with pytest.raises(LimitExceededError):
        summarize_with_file(
            file="test_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=1,
            daily_limit=5,
            thinking_level="MINIMAL",
        )

    assert mock_check.call_count == 2
    mock_check.assert_any_call(user_id=1, daily_limit=5, quantity=0)
    mock_check.assert_any_call(user_id=1, daily_limit=5, quantity=1)
    mock_client.files.delete.assert_called_with(name="files/audio123")


def test_summarize_with_document_preflight_blocks_before_download(mocker):
    """Test summarize_with_document blocks zero-quota users before download or upload."""
    mock_check = mocker.patch("summary.check_quota", side_effect=LimitExceededError)
    mock_download = mocker.patch("summary.download_tg")

    with pytest.raises(LimitExceededError):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=1,
            daily_limit=0,
            thinking_level="MINIMAL",
        )

    mock_check.assert_called_once_with(user_id=1, daily_limit=0, quantity=0)
    mock_download.assert_not_called()


def test_summarize_with_file_logs_warning_on_delete_failure(mocker):
    """Test summarize_with_file logs a warning when Gemini file deletion fails but still returns the result."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_audio_file = SimpleNamespace(
        name="files/audio123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    mocker.patch("summary.upload_and_wait_for_file", return_value=mock_audio_file)
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("summary.run_model", return_value="summary text")
    mock_client.files.delete.side_effect = Exception("delete failed")
    mock_logger = mocker.patch("summary.logger")

    result = summarize_with_file(
        file="test_audio.ogg",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "summary text"
    mock_client.files.delete.assert_called_once_with(name="files/audio123")
    mock_logger.warning.assert_called_once()


def test_summarize_text_raises_on_empty_response(mocker):
    """Test summarize_text raises RetryError on repeated empty model responses."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch("summary.run_model", side_effect=AttributeError)

    with pytest.raises(RetryError):
        summarize_text(
            text="Hello world",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )


def test_summarize_with_document_raises_when_upload_name_none(mocker):
    """Test summarize_with_document raises RetryError and skips file delete when upload name is None."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch("services.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_file = mocker.MagicMock()
    mock_file.name = None
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(RetryError):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )

    mock_client.files.delete.assert_not_called()


def test_summarize_with_document_raises_when_uri_none(mocker):
    """Test summarize_with_document raises RetryError when uri is None."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch("services.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_file = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri=None,
        mime_type="application/pdf",
    )
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(RetryError):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )


def test_summarize_with_document_raises_when_mime_type_none(mocker):
    """Test summarize_with_document raises RetryError when mime_type is None."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch("services.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_file = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type=None,
    )
    mock_client.files.upload.return_value = mock_file

    with pytest.raises(RetryError):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )


def test_summarize_with_document_raises_on_empty_response(mocker):
    """Test summarize_with_document raises RetryError when the model returns nothing."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    mocker.patch("services.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_file = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    mock_client.files.upload.return_value = mock_file
    mocker.patch("summary.run_model", side_effect=AttributeError)

    with pytest.raises(RetryError):
        summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="MINIMAL",
        )


def test_summarize_with_document_logs_warning_on_delete_failure(mocker):
    """Test summarize_with_document logs a warning when Gemini file deletion fails but still returns the result."""
    mocker.patch("summary.check_quota", return_value=True)
    mocker.patch("summary.download_tg", return_value="temp_doc.pdf")
    mocker.patch("summary.clean_up")
    mocker.patch("services.time.sleep")
    mock_client = mocker.patch("summary.gemini_client")
    mocker.patch("services.gemini_client", mock_client)
    mock_file = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    mock_client.files.upload.return_value = mock_file
    mocker.patch("summary.run_model", return_value="document summary")
    mock_client.files.delete.side_effect = Exception("delete failed")
    mock_logger = mocker.patch("summary.logger")

    result = summarize_with_document(
        file=mocker.MagicMock(),
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="application/pdf",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "document summary"
    mock_client.files.delete.assert_called_once_with(name="files/doc123")
    mock_logger.warning.assert_called_once()


def test_summarize_with_telegram_file(mocker):
    """Test summarize() downloads a Telegram File object before summarizing."""
    mocker.patch("summary.check_quota", return_value=True)
    mock_download_tg = mocker.patch(
        "summary.download_tg",
        return_value="downloaded.ogg",
    )
    mocker.patch.object(
        summary_module.summarizer,
        "summarize_with_file",
        return_value="Telegram file summary",
    )
    mocker.patch("summary.clean_up")
    mock_tg_file = mocker.MagicMock(spec=File)

    result = summarize(
        data=mock_tg_file,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="MINIMAL",
    )

    assert result == "Telegram file summary"
    mock_download_tg.assert_called_once_with(mock_tg_file, ext=".ogg")
