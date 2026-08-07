import logging
from textwrap import dedent
from types import SimpleNamespace

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from telebot.types import File
from tenacity import RetryError

from config import DEFAULT_MODEL_ID_FOR_SUMMARY
from domain import PrefixedText
from exceptions import FetchTranscriptError, LimitExceededError
from prompts import PROMPTS
from summary import Summarizer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summarizer(mocker):
    """Return (summarizer, fakes) with every collaborator injected as a MagicMock."""
    fakes = SimpleNamespace(
        quota_manager=mocker.MagicMock(),
        gemini_helper=mocker.MagicMock(),
        llm_client=mocker.MagicMock(),
        downloader=mocker.MagicMock(),
        audio_transcriber=mocker.MagicMock(),
        yt_transcriber=mocker.MagicMock(),
    )
    summarizer = Summarizer(
        fakes.quota_manager,
        fakes.gemini_helper,
        fakes.llm_client,
        fakes.downloader,
        fakes.audio_transcriber,
        fakes.yt_transcriber,
    )
    return summarizer, fakes


def test_only_the_public_entry_points_carry_retry():
    """Lock the retry topology: the shared helper must stay undecorated.

    Both callers of _summarize_uploaded_file are themselves @retry-wrapped, so a
    decorator here would nest a second layer. On a mixed failure sequence — one
    the inner predicate skips and the outer retries, then one the inner retries —
    the upload and its consuming quota check would run three times instead of
    two, and Gemini bills failed calls. No behavioral test catches this: for a
    single repeated exception type both topologies produce identical counts.
    """
    assert not hasattr(Summarizer._summarize_uploaded_file, "retry")
    assert hasattr(Summarizer.summarize_with_file, "retry")
    assert hasattr(Summarizer.summarize_with_document, "retry")
    assert hasattr(Summarizer.summarize_text, "retry")


def test_summarize_with_file_upload_and_model_call(mocker):
    """Test the complete summarize_with_file flow with the file API and model mocked."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.gemini_helper.resolve_mime_type.return_value = "audio/ogg"
    mock_uploaded_file = SimpleNamespace(
        name="files/mock123",
        uri="https://generativelanguage.googleapis.com/v1beta/files/mock123",
        mime_type="audio/ogg",
        state="ACTIVE",
    )
    fakes.gemini_helper.upload_and_wait_for_file.return_value = mock_uploaded_file
    fakes.llm_client.build_uploaded_file.return_value = "uploaded-file-sentinel"
    fakes.llm_client.run.return_value = "This is a mocked summary of the file."

    result = summarizer.summarize_with_file(
        file="test_audio.ogg",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "This is a mocked summary of the file."
    fakes.gemini_helper.upload_and_wait_for_file.assert_called_once_with(
        file="test_audio.ogg",
        mime_type="audio/ogg",
    )
    fakes.gemini_helper.delete_file.assert_called_once_with("files/mock123")
    fakes.llm_client.build_uploaded_file.assert_called_once_with(
        model_id="gemini-3.5-flash-lite",
        file=mock_uploaded_file,
    )
    call_kwargs = fakes.llm_client.run.call_args.kwargs
    assert call_kwargs["model_id"] == "gemini-3.5-flash-lite"
    assert call_kwargs["target_language"] == "English"
    assert call_kwargs["thinking_level"] == "minimal"
    prompt, uploaded = call_kwargs["content"]
    assert "detailed summary" in prompt
    assert uploaded == "uploaded-file-sentinel"


def test_summarize_with_file_retries_on_empty_response(mocker):
    """Test summarize_with_file raises RetryError on repeated empty model responses."""
    summarizer, fakes = _make_summarizer(mocker)
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.return_value = True
    mock_audio_file = SimpleNamespace(
        name="files/mock123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    fakes.gemini_helper.upload_and_wait_for_file.return_value = mock_audio_file
    fakes.llm_client.run.side_effect = AttributeError

    with pytest.raises(RetryError):
        summarizer.summarize_with_file(
            file="test_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )


def test_summarize_text_from_webpage(mocker):
    """Test summarize_text sends the prompt and the content as separate parts.

    The transcript paths reach the model through this same method, so this
    covers them too — only the caller differs.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.llm_client.run.return_value = "Webpage summary."

    result = summarizer.summarize_text(
        text="Parsed page content.",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "Webpage summary."
    call_kwargs = fakes.llm_client.run.call_args.kwargs
    # Two parts, not one concatenated string: a trace has to record the prompt
    # and the summarized content as separate fields.
    prompt, content = call_kwargs["content"]
    assert content == "Parsed page content."
    assert prompt == dedent(PROMPTS["basic_prompt_for_transcript"]).strip()
    assert call_kwargs["model_id"] == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("blank", ["", "   \n  "])
def test_summarize_text_drops_the_content_part_when_text_is_blank(mocker, blank):
    """Test summarize_text sends the prompt alone rather than an empty part.

    The Replicate rescue path yields "" for audio WhisperX finds no segments
    in — silence or music — and an empty text part is not worth sending.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.llm_client.run.return_value = "Empty summary."

    summarizer.summarize_text(
        text=blank,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert fakes.llm_client.run.call_args.kwargs["content"] == [
        dedent(PROMPTS["basic_prompt_for_transcript"]).strip(),
    ]


def test_summarize_with_file_upload_failure(mocker):
    """Test summarize_with_file raises when file upload fails."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.gemini_helper.upload_and_wait_for_file.side_effect = Exception(
        "Upload failed",
    )

    with pytest.raises(Exception, match="Upload failed"):
        summarizer.summarize_with_file(
            file="test_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )


def test_summarize_model_api_exception(mocker):
    """Test summarize_text raises RetryError when the provider returns an error."""
    summarizer, fakes = _make_summarizer(mocker)
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.return_value = True
    fakes.llm_client.run.side_effect = ModelHTTPError(
        status_code=400,
        model_name="gemini-3.5-flash-lite",
        body={"error": {"message": "Model unavailable"}},
    )

    with pytest.raises(RetryError):
        summarizer.summarize_text(
            text="Hello",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )


def test_summarize_with_document_polling(mocker):
    """Test summarize_with_document reaches the model with the uploaded file.

    Gemini's PROCESSING -> ACTIVE polling loop lives inside GeminiHelper (an
    injected collaborator here) and is covered by
    tests/test_services.py::test_upload_and_wait_for_file_polling; this test
    only proves Summarizer wires the uploaded file's uri/mime_type through to
    the model call and deletes it afterward.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    mock_file_active = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    fakes.gemini_helper.upload_and_wait_for_file.return_value = mock_file_active
    fakes.llm_client.build_uploaded_file.return_value = "uploaded-file-sentinel"
    fakes.llm_client.run.return_value = "Document summary"
    mock_tg_file = mocker.MagicMock()

    result = summarizer.summarize_with_document(
        file=mock_tg_file,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="application/pdf",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "Document summary"
    fakes.gemini_helper.delete_file.assert_called_once_with("files/doc123")
    _, uploaded = fakes.llm_client.run.call_args.kwargs["content"]
    assert uploaded == "uploaded-file-sentinel"
    fakes.llm_client.build_uploaded_file.assert_called_once_with(
        model_id="gemini-3.5-flash-lite",
        file=mock_file_active,
    )


def test_summarize_with_document_cleans_up_on_failed_processing(mocker):
    """Test summarize_with_document cleans up the downloaded file on failure."""
    summarizer, fakes = _make_summarizer(mocker)
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    mock_clean_up = mocker.patch("summary.clean_up")
    fakes.gemini_helper.upload_and_wait_for_file.side_effect = ValueError("FAILED")

    with pytest.raises(ValueError, match="FAILED"):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )

    mock_clean_up.assert_called_once_with(file="temp_doc.pdf")


# 📺 is the youtube_transcript_api primary, 📹 the yt-dlp fallback. Summarizer
# does not pick either — it passes through whatever the transcriber reports.
@pytest.mark.parametrize("prefix", ["📺", "📹"])
def test_summarize_youtube_transcript_carries_the_backend_prefix(mocker, prefix):
    """Test summarize() always tries the transcript and keeps its source prefix."""
    summarizer, fakes = _make_summarizer(mocker)
    url = "https://youtube.com/watch?v=123"
    fakes.quota_manager.check_quota.return_value = True
    fakes.yt_transcriber.get_transcript.return_value = SimpleNamespace(
        text="YT Transcript content",
        prefix=prefix,
    )
    mock_sum_transcript = mocker.patch.object(
        summarizer,
        "summarize_text",
        return_value="- first point\n- second point",
    )

    result = summarizer.summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == f"{prefix}\n\n- first point\n- second point"
    fakes.yt_transcriber.get_transcript.assert_called_once_with(url)
    mock_sum_transcript.assert_called_once_with(
        text="YT Transcript content",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )


def test_summarize_youtube_transcript_summary_retry_does_not_fall_back(mocker):
    """Test transcript summary retry errors do not trigger audio fallback paths."""
    summarizer, fakes = _make_summarizer(mocker)
    url = "https://youtube.com/watch?v=123"
    retry_error = RetryError(mocker.MagicMock())
    fakes.quota_manager.check_quota.return_value = True
    fakes.yt_transcriber.get_transcript.return_value = SimpleNamespace(
        text="YT Transcript content",
        prefix="📹",
    )
    mock_file_summary = mocker.patch.object(summarizer, "summarize_with_file")
    mocker.patch.object(summarizer, "summarize_text", side_effect=retry_error)

    with pytest.raises(RetryError):
        summarizer.summarize(
            data=url,
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )

    fakes.downloader.download_yt.assert_not_called()
    mock_file_summary.assert_not_called()
    fakes.audio_transcriber.transcribe.assert_not_called()


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
    summarizer, fakes = _make_summarizer(mocker)
    url = "https://youtube.com/watch?v=123"
    fakes.quota_manager.check_quota.return_value = True
    fakes.yt_transcriber.get_transcript.side_effect = transcript_error
    fakes.downloader.download_yt.return_value = "downloaded.ogg"
    mocker.patch.object(
        summarizer,
        "summarize_with_file",
        return_value="File summary",
    )
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_logger = mocker.patch("summary.logger")

    result = summarizer.summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "File summary"
    fakes.downloader.download_yt.assert_called_once_with(url)
    mock_clean_up.assert_called_once_with(file="downloaded.ogg")
    mock_logger.warning.assert_called_once_with(
        "get_transcript failed, falling back to download: %s",
        mocker.ANY,
    )


def test_summarize_fallback_to_transcription(mocker):
    """Test summarize() fallback to transcription (📝 prefix) when file summary fails."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    mocker.patch.object(
        summarizer,
        "summarize_with_file",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio")
    fakes.audio_transcriber.transcribe.return_value = "Transcription text"
    mocker.patch.object(
        summarizer,
        "summarize_text",
        return_value="- transcript point\n- follow-up point",
    )
    mock_clean_up = mocker.patch("summary.clean_up")

    result = summarizer.summarize(
        data="local_audio.ogg",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
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

    Every OpenRouter model is registered text-only, so this is the live path for
    audio whenever one of them is selected.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    mock_with_file = mocker.patch.object(summarizer, "summarize_with_file")
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mock_compress = mocker.patch("summary.compress_audio")
    fakes.audio_transcriber.transcribe.return_value = "Transcription text"
    mocker.patch.object(
        summarizer,
        "summarize_text",
        return_value="- transcript point",
    )
    mocker.patch("summary.clean_up")

    result = summarizer.summarize(
        data="local_audio.ogg",
        model="z-ai/glm-5.2",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
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
    the same modality check as summarize(). The chosen model also has
    supports_files=False, so this pins the precedence: transcription wins over
    the Gemini document fallback, keeping the user's own model on the summary.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "voice.ogg"
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio")
    fakes.audio_transcriber.transcribe.return_value = "Transcription text"
    mocker.patch.object(
        summarizer,
        "summarize_text",
        return_value="- transcript point",
    )
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_tg_file = mocker.MagicMock()

    result = summarizer.summarize_with_document(
        file=mock_tg_file,
        model="z-ai/glm-5.2",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="audio/ogg",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "📝\n\n- transcript point"
    fakes.gemini_helper.upload_and_wait_for_file.assert_not_called()
    fakes.downloader.download_tg.assert_called_once_with(mock_tg_file, ext=".ogg")
    mock_clean_up.assert_has_calls(
        [
            mocker.call(file="temp.ogg"),
            mocker.call(file="voice.ogg"),
        ],
    )


def test_summarize_with_document_falls_back_when_model_takes_no_file(mocker, caplog):
    """Test a PDF on an OpenRouter model is summarized by the default Gemini one.

    The upload only ever goes to Gemini and there is no text-extraction path for
    a PDF, so the model is substituted for this request alone.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    mock_file_active = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    fakes.gemini_helper.upload_and_wait_for_file.return_value = mock_file_active
    fakes.llm_client.run.return_value = "Document summary"
    mocker.patch("summary.clean_up")

    with caplog.at_level(logging.WARNING, logger="summary"):
        result = summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            model="openai/gpt-5.6-luna",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )

    assert result == "Document summary"
    assert fakes.llm_client.run.call_args.kwargs["model_id"] == (
        DEFAULT_MODEL_ID_FOR_SUMMARY
    )
    assert fakes.llm_client.build_uploaded_file.call_args.kwargs["model_id"] == (
        DEFAULT_MODEL_ID_FOR_SUMMARY
    )
    assert "openai/gpt-5.6-luna" in caplog.text


def test_summarize_with_document_keeps_a_model_that_takes_files(mocker):
    """Test the fallback leaves a file-capable model alone."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    fakes.gemini_helper.upload_and_wait_for_file.return_value = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    fakes.llm_client.run.return_value = "Document summary"
    mocker.patch("summary.clean_up")

    summarizer.summarize_with_document(
        file=mocker.MagicMock(),
        model="gemini-3.6-flash",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="application/pdf",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert fakes.llm_client.run.call_args.kwargs["model_id"] == "gemini-3.6-flash"


def test_summarize_fallback_cleans_up_temp_file_when_compress_fails(mocker):
    """Test summarize() cleans up the temp file even if compress_audio raises."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    mocker.patch.object(
        summarizer,
        "summarize_with_file",
        side_effect=RetryError(mocker.MagicMock()),
    )
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio", side_effect=RuntimeError("ffmpeg failed"))
    mock_clean_up = mocker.patch("summary.clean_up")

    with pytest.raises(RuntimeError):
        summarizer.summarize(
            data="local_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )

    mock_clean_up.assert_any_call(file="temp.ogg")


def test_summarize_castro(mocker):
    """Test summarize() with Castro.fm URL."""
    summarizer, fakes = _make_summarizer(mocker)
    url = "https://castro.fm/episode/123"
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_castro.return_value = "downloaded.mp3"
    mocker.patch.object(
        summarizer,
        "summarize_with_file",
        return_value="Castro summary",
    )
    mocker.patch("summary.clean_up")

    result = summarizer.summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "Castro summary"


def test_summarize_castro_www_host(mocker):
    """Test summarize() downloads a www-prefixed Castro URL instead of uploading it.

    Regression: the URL used to be re-classified with a literal
    "https://castro.fm/episode/" prefix check, so a www-prefixed link skipped
    download_castro and was passed to summarize_with_file as a file path.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_castro.return_value = "dl.mp3"
    mock_with_file = mocker.patch.object(
        summarizer,
        "summarize_with_file",
        return_value="Castro summary",
    )
    mocker.patch("summary.clean_up")

    result = summarizer.summarize(
        data="https://www.castro.fm/episode/123",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "Castro summary"
    fakes.downloader.download_castro.assert_called_once_with(
        "https://www.castro.fm/episode/123",
    )
    assert mock_with_file.call_args.kwargs["file"] == "dl.mp3"


def test_summarize_youtube_uppercase_host_uses_transcript(mocker):
    """Test summarize() routes an uppercase-host YouTube URL to the transcript path.

    Regression: the old literal prefix check was case-sensitive, so an
    uppercase host bypassed the transcript path entirely.
    """
    summarizer, fakes = _make_summarizer(mocker)
    url = "https://YouTube.com/watch?v=dQw4w9WgXcQ"
    fakes.quota_manager.check_quota.return_value = True
    fakes.yt_transcriber.get_transcript.return_value = PrefixedText(
        text="transcript text",
        prefix="📺",
    )
    mocker.patch.object(summarizer, "summarize_text", return_value="YT summary")
    mock_with_file = mocker.patch.object(summarizer, "summarize_with_file")

    result = summarizer.summarize(
        data=url,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "📺\n\nYT summary"
    fakes.yt_transcriber.get_transcript.assert_called_once_with(url)
    mock_with_file.assert_not_called()


def test_summarize_preflight_blocks_before_download(mocker):
    """Test summarize() blocks zero-quota users before any network IO."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.side_effect = LimitExceededError

    with pytest.raises(LimitExceededError):
        summarizer.summarize(
            data="https://castro.fm/episode/123",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=1,
            daily_limit=0,
            thinking_level="minimal",
        )

    fakes.quota_manager.check_quota.assert_called_once_with(
        user_id=1,
        daily_limit=0,
        quantity=0,
    )
    fakes.downloader.download_castro.assert_not_called()


def test_summarize_with_file_deletes_gemini_file_when_quota_check_fails(mocker):
    """Test summarize_with_file cleans up the uploaded Gemini file if consuming check fails."""
    summarizer, fakes = _make_summarizer(mocker)
    mock_audio_file = SimpleNamespace(
        name="files/audio123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    fakes.gemini_helper.upload_and_wait_for_file.return_value = mock_audio_file
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.side_effect = [True, LimitExceededError]

    with pytest.raises(LimitExceededError):
        summarizer.summarize_with_file(
            file="test_audio.ogg",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=1,
            daily_limit=5,
            thinking_level="minimal",
        )

    assert fakes.quota_manager.check_quota.call_count == 2
    fakes.quota_manager.check_quota.assert_any_call(
        user_id=1,
        daily_limit=5,
        quantity=0,
    )
    fakes.quota_manager.check_quota.assert_any_call(
        user_id=1,
        daily_limit=5,
        quantity=1,
    )
    fakes.gemini_helper.delete_file.assert_called_with("files/audio123")


def test_summarize_with_document_preflight_blocks_before_download(mocker):
    """Test summarize_with_document blocks zero-quota users before download or upload."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.side_effect = LimitExceededError

    with pytest.raises(LimitExceededError):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=1,
            daily_limit=0,
            thinking_level="minimal",
        )

    fakes.quota_manager.check_quota.assert_called_once_with(
        user_id=1,
        daily_limit=0,
        quantity=0,
    )
    fakes.downloader.download_tg.assert_not_called()


def test_summarize_with_file_logs_warning_on_delete_failure(mocker):
    """Test summarize_with_file logs a warning when Gemini file deletion fails but still returns the result."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    mock_audio_file = SimpleNamespace(
        name="files/audio123",
        uri="https://mock.uri",
        mime_type="audio/ogg",
    )
    fakes.gemini_helper.upload_and_wait_for_file.return_value = mock_audio_file
    fakes.llm_client.run.return_value = "summary text"
    fakes.gemini_helper.delete_file.side_effect = Exception("delete failed")
    mock_logger = mocker.patch("summary.logger")

    result = summarizer.summarize_with_file(
        file="test_audio.ogg",
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "summary text"
    fakes.gemini_helper.delete_file.assert_called_once_with("files/audio123")
    mock_logger.warning.assert_called_once()


def test_summarize_text_raises_on_empty_response(mocker):
    """Test summarize_text raises RetryError on repeated empty model responses."""
    summarizer, fakes = _make_summarizer(mocker)
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.return_value = True
    fakes.llm_client.run.side_effect = AttributeError

    with pytest.raises(RetryError):
        summarizer.summarize_text(
            text="Hello world",
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )


def test_summarize_with_document_raises_when_upload_metadata_incomplete(mocker):
    """Test summarize_with_document raises RetryError and skips delete on bad metadata.

    Which field was missing — name, uri or mime_type — is GeminiHelper's
    concern, covered by tests/test_services.py::test_upload_and_wait_for_file_*.
    All three surface here as one AttributeError, so this proves the only thing
    Summarizer decides: it becomes a RetryError, and delete_file is never called
    because document_file_name was never assigned.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    fakes.gemini_helper.upload_and_wait_for_file.side_effect = AttributeError

    with pytest.raises(RetryError):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )

    fakes.gemini_helper.delete_file.assert_not_called()


def test_summarize_with_document_raises_on_empty_response(mocker):
    """Test summarize_with_document raises RetryError when the model returns nothing."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    fakes.gemini_helper.upload_and_wait_for_file.return_value = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    fakes.llm_client.run.side_effect = AttributeError

    with pytest.raises(RetryError):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            model="gemini-3.5-flash-lite",
            prompt_key="basic_prompt_for_transcript",
            target_language="English",
            mime_type="application/pdf",
            user_id=123,
            daily_limit=10,
            thinking_level="minimal",
        )


def test_summarize_with_document_logs_warning_on_delete_failure(mocker):
    """Test summarize_with_document logs a warning when Gemini file deletion fails but still returns the result."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    mocker.patch("summary.clean_up")
    fakes.gemini_helper.upload_and_wait_for_file.return_value = SimpleNamespace(
        state="ACTIVE",
        name="files/doc123",
        uri="https://mock.uri",
        mime_type="application/pdf",
    )
    fakes.llm_client.run.return_value = "document summary"
    fakes.gemini_helper.delete_file.side_effect = Exception("delete failed")
    mock_logger = mocker.patch("summary.logger")

    result = summarizer.summarize_with_document(
        file=mocker.MagicMock(),
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        mime_type="application/pdf",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "document summary"
    fakes.gemini_helper.delete_file.assert_called_once_with("files/doc123")
    mock_logger.warning.assert_called_once()


def test_summarize_with_telegram_file(mocker):
    """Test summarize() downloads a Telegram File object before summarizing."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "downloaded.ogg"
    mocker.patch.object(
        summarizer,
        "summarize_with_file",
        return_value="Telegram file summary",
    )
    mocker.patch("summary.clean_up")
    mock_tg_file = mocker.MagicMock(spec=File)

    result = summarizer.summarize(
        data=mock_tg_file,
        model="gemini-3.5-flash-lite",
        prompt_key="basic_prompt_for_transcript",
        target_language="English",
        user_id=123,
        daily_limit=10,
        thinking_level="minimal",
    )

    assert result == "Telegram file summary"
    fakes.downloader.download_tg.assert_called_once_with(mock_tg_file, ext=".ogg")
