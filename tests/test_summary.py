import logging
from dataclasses import replace
from textwrap import dedent
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError
from telebot.types import File
from tenacity import RetryError

from config import DEFAULT_MODEL_ID_FOR_SUMMARY
from domain import PrefixedText, SummarySettings
from exceptions import FetchTranscriptError, LimitExceededError
from prompts import PROMPTS
from summary import Summarizer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SETTINGS = SummarySettings(
    model="openai/gpt-6-luna",
    prompt_key="basic_prompt_for_transcript",
    target_language="English",
    user_id=123,
    daily_limit=10,
    thinking_level="minimal",
)


def _make_summarizer(mocker):
    """Return (summarizer, fakes) with every collaborator injected as a MagicMock."""
    fakes = SimpleNamespace(
        quota_manager=mocker.MagicMock(),
        openrouter_files=mocker.MagicMock(),
        llm_client=mocker.MagicMock(),
        downloader=mocker.MagicMock(),
        audio_transcriber=mocker.MagicMock(),
        yt_transcriber=mocker.MagicMock(),
    )
    summarizer = Summarizer(
        fakes.quota_manager,
        fakes.openrouter_files,
        fakes.llm_client,
        fakes.downloader,
        fakes.audio_transcriber,
        fakes.yt_transcriber,
    )
    return summarizer, fakes


def _api_error(status_code=400):
    """An `openai` SDK error as OpenRouter's HTTP failures surface."""
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return APIStatusError(
        "Model unavailable",
        response=httpx.Response(status_code, request=request),
        body=None,
    )


def test_only_the_public_entry_points_carry_retry():
    """Lock the retry topology: the shared helper must stay undecorated.

    The caller of _summarize_uploaded_file is itself @retry-wrapped, so a
    decorator here would nest a second layer. On a mixed failure sequence — one
    the inner predicate skips and the outer retries, then one the inner retries —
    the upload and its consuming quota check would run three times instead of
    two, and providers bill failed calls. No behavioral test catches this: for a
    single repeated exception type both topologies produce identical counts.
    """
    assert not hasattr(Summarizer._summarize_uploaded_file, "retry")
    assert not hasattr(Summarizer._summarize_via_transcription, "retry")
    assert hasattr(Summarizer.summarize_with_document, "retry")
    assert hasattr(Summarizer.summarize_text, "retry")


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
        settings=SETTINGS,
    )

    assert result == "Webpage summary."
    call_kwargs = fakes.llm_client.run.call_args.kwargs
    # Two parts, not one concatenated string: a trace has to record the prompt
    # and the summarized content as separate fields.
    prompt, content = call_kwargs["content"]
    assert content == "Parsed page content."
    assert prompt == dedent(PROMPTS["basic_prompt_for_transcript"]).strip()
    assert call_kwargs["model_id"] == "openai/gpt-6-luna"


@pytest.mark.parametrize("blank", ["", "   \n  "])
def test_summarize_text_drops_the_content_part_when_text_is_blank(mocker, blank):
    """Test summarize_text sends the prompt alone rather than an empty part.

    The Replicate transcription yields "" for audio WhisperX finds no segments
    in — silence or music — and an empty text part is not worth sending.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.llm_client.run.return_value = "Empty summary."

    summarizer.summarize_text(
        text=blank,
        settings=SETTINGS,
    )

    assert fakes.llm_client.run.call_args.kwargs["content"] == [
        dedent(PROMPTS["basic_prompt_for_transcript"]).strip(),
    ]


def test_summarize_model_api_exception(mocker):
    """Test summarize_text raises RetryError when the provider returns an error."""
    summarizer, fakes = _make_summarizer(mocker)
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.return_value = True
    fakes.llm_client.run.side_effect = _api_error()

    with pytest.raises(RetryError):
        summarizer.summarize_text(
            text="Hello",
            settings=SETTINGS,
        )


def test_summarize_with_document_uploads_summarizes_and_deletes(mocker):
    """Test a document reaches the user's model by file id and is deleted afterward."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc"
    fakes.openrouter_files.upload.return_value = "or_file_doc123"
    fakes.llm_client.build_file_part.return_value = "file-part-sentinel"
    fakes.llm_client.run.return_value = "Document summary"
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_tg_file = mocker.MagicMock()

    result = summarizer.summarize_with_document(
        file=mock_tg_file,
        mime_type="application/pdf",
        settings=SETTINGS,
    )

    assert result == "Document summary"
    fakes.downloader.download_tg.assert_called_once_with(mock_tg_file)
    fakes.openrouter_files.upload.assert_called_once_with(
        file="temp_doc",
        mime_type="application/pdf",
    )
    fakes.llm_client.build_file_part.assert_called_once_with("or_file_doc123")
    call_kwargs = fakes.llm_client.run.call_args.kwargs
    prompt, uploaded = call_kwargs["content"]
    assert "detailed summary" in prompt
    assert uploaded == "file-part-sentinel"
    assert call_kwargs["model_id"] == "openai/gpt-6-luna"
    assert call_kwargs["target_language"] == "English"
    assert call_kwargs["thinking_level"] == "minimal"
    fakes.openrouter_files.delete.assert_called_once_with("or_file_doc123")
    mock_clean_up.assert_called_once_with(file="temp_doc")


def test_summarize_with_document_cleans_up_on_unretried_upload_failure(mocker):
    """Test summarize_with_document cleans up the downloaded file on failure."""
    summarizer, fakes = _make_summarizer(mocker)
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc.pdf"
    mock_clean_up = mocker.patch("summary.clean_up")
    fakes.openrouter_files.upload.side_effect = KeyError("id")

    with pytest.raises(KeyError, match="id"):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            mime_type="application/pdf",
            settings=SETTINGS,
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
        settings=SETTINGS,
    )

    assert result == f"{prefix}\n\n- first point\n- second point"
    fakes.yt_transcriber.get_transcript.assert_called_once_with(url)
    mock_sum_transcript.assert_called_once_with(
        text="YT Transcript content",
        settings=SETTINGS,
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
    mocker.patch.object(summarizer, "summarize_text", side_effect=retry_error)

    with pytest.raises(RetryError):
        summarizer.summarize(
            data=url,
            settings=SETTINGS,
        )

    fakes.downloader.download_yt.assert_not_called()
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
    mock_via_transcription = mocker.patch.object(
        summarizer,
        "_summarize_via_transcription",
        return_value="Audio summary",
    )
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_logger = mocker.patch("summary.logger")

    result = summarizer.summarize(
        data=url,
        settings=SETTINGS,
    )

    assert result == "Audio summary"
    fakes.downloader.download_yt.assert_called_once_with(url)
    mock_via_transcription.assert_called_once_with(
        data="downloaded.ogg",
        settings=SETTINGS,
    )
    mock_clean_up.assert_called_once_with(file="downloaded.ogg")
    mock_logger.warning.assert_called_once_with(
        "get_transcript failed, falling back to download: %s",
        mocker.ANY,
    )


def test_summarize_transcribes_audio_and_summarizes_with_the_users_model(mocker):
    """Test summarize() sends audio through Replicate, then to the chosen model.

    Transcription is the only route for spoken content, so every such summary
    carries the 📝 prefix.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mock_compress = mocker.patch("summary.compress_audio")
    fakes.audio_transcriber.transcribe.return_value = "Transcription text"
    mock_summarize_text = mocker.patch.object(
        summarizer,
        "summarize_text",
        return_value="- transcript point\n- follow-up point",
    )
    mock_clean_up = mocker.patch("summary.clean_up")
    settings = replace(SETTINGS, model="x-ai/grok-4.7")

    result = summarizer.summarize(
        data="local_audio.ogg",
        settings=settings,
    )

    assert result == "📝\n\n- transcript point\n- follow-up point"
    mock_compress.assert_called_once_with(
        input_file="local_audio.ogg",
        output_file="temp.ogg",
    )
    fakes.audio_transcriber.transcribe.assert_called_once_with("temp.ogg")
    mock_summarize_text.assert_called_once_with(
        text="Transcription text",
        settings=settings,
    )
    fakes.openrouter_files.upload.assert_not_called()
    mock_clean_up.assert_has_calls(
        [
            mocker.call(file="temp.ogg"),
            mocker.call(file="local_audio.ogg"),
        ],
    )


def test_summarize_with_document_routes_audio_document_to_transcription(mocker):
    """Test an audio document is transcribed, whichever model is selected.

    SUPPORTED_DOCUMENT_MIME_TYPES accepts audio/ogg, and OpenRouter refuses audio
    by file id. The chosen model has supports_files=False, so this also pins the
    precedence: transcription wins over the document failover, keeping the
    user's own model on the summary.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "voice.ogg"
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio")
    fakes.audio_transcriber.transcribe.return_value = "Transcription text"
    mock_summarize_text = mocker.patch.object(
        summarizer,
        "summarize_text",
        return_value="- transcript point",
    )
    mock_clean_up = mocker.patch("summary.clean_up")
    mock_tg_file = mocker.MagicMock()
    settings = replace(SETTINGS, model="deepseek/deepseek-v4.1-flash")

    result = summarizer.summarize_with_document(
        file=mock_tg_file,
        mime_type="audio/ogg",
        settings=settings,
    )

    assert result == "📝\n\n- transcript point"
    mock_summarize_text.assert_called_once_with(
        text="Transcription text",
        settings=settings,
    )
    fakes.openrouter_files.upload.assert_not_called()
    fakes.downloader.download_tg.assert_called_once_with(mock_tg_file, ext=".ogg")
    mock_clean_up.assert_has_calls(
        [
            mocker.call(file="temp.ogg"),
            mocker.call(file="voice.ogg"),
        ],
    )


def test_summarize_with_document_falls_back_when_model_takes_no_file(mocker, caplog):
    """Test a PDF on a model that takes no file is summarized by the default one.

    There is no text-extraction path for a PDF, so the model is substituted for
    this request alone.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc"
    fakes.openrouter_files.upload.return_value = "or_file_doc123"
    fakes.llm_client.run.return_value = "Document summary"
    mocker.patch("summary.clean_up")

    with caplog.at_level(logging.WARNING, logger="summary"):
        result = summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            mime_type="application/pdf",
            settings=replace(SETTINGS, model="deepseek/deepseek-v4.1-flash"),
        )

    assert result == "Document summary"
    assert fakes.llm_client.run.call_args.kwargs["model_id"] == (
        DEFAULT_MODEL_ID_FOR_SUMMARY
    )
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert "deepseek/deepseek-v4.1-flash" in caplog.text
    assert DEFAULT_MODEL_ID_FOR_SUMMARY in caplog.text


@pytest.mark.parametrize(
    "mime_type",
    ["application/pdf", "text/plain", "text/csv", "application/rtf"],
)
def test_summarize_with_document_keeps_a_model_that_takes_files(mocker, mime_type):
    """Test every document type stays on a file-capable model the user chose."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc"
    fakes.openrouter_files.upload.return_value = "or_file_doc123"
    fakes.llm_client.run.return_value = "Document summary"
    mocker.patch("summary.clean_up")

    summarizer.summarize_with_document(
        file=mocker.MagicMock(),
        mime_type=mime_type,
        settings=replace(SETTINGS, model="x-ai/grok-4.7"),
    )

    fakes.openrouter_files.upload.assert_called_once_with(
        file="temp_doc",
        mime_type=mime_type,
    )
    assert fakes.llm_client.run.call_args.kwargs["model_id"] == "x-ai/grok-4.7"
    fakes.openrouter_files.delete.assert_called_once_with("or_file_doc123")


def test_summarize_cleans_up_temp_file_when_compress_fails(mocker):
    """Test summarize() cleans up the temp file even if compress_audio raises."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    mocker.patch("summary.generate_temporary_name", return_value="temp.ogg")
    mocker.patch("summary.compress_audio", side_effect=RuntimeError("ffmpeg failed"))
    mock_clean_up = mocker.patch("summary.clean_up")

    with pytest.raises(RuntimeError):
        summarizer.summarize(
            data="local_audio.ogg",
            settings=SETTINGS,
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
        "_summarize_via_transcription",
        return_value="Castro summary",
    )
    mocker.patch("summary.clean_up")

    result = summarizer.summarize(
        data=url,
        settings=SETTINGS,
    )

    assert result == "Castro summary"


def test_summarize_castro_www_host(mocker):
    """Test summarize() downloads a www-prefixed Castro URL before summarizing it.

    Regression: the URL used to be re-classified with a literal
    "https://castro.fm/episode/" prefix check, so a www-prefixed link skipped
    download_castro and was passed on as a file path.
    """
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_castro.return_value = "dl.mp3"
    mock_via_transcription = mocker.patch.object(
        summarizer,
        "_summarize_via_transcription",
        return_value="Castro summary",
    )
    mocker.patch("summary.clean_up")

    result = summarizer.summarize(
        data="https://www.castro.fm/episode/123",
        settings=SETTINGS,
    )

    assert result == "Castro summary"
    fakes.downloader.download_castro.assert_called_once_with(
        "https://www.castro.fm/episode/123",
    )
    assert mock_via_transcription.call_args.kwargs["data"] == "dl.mp3"


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

    result = summarizer.summarize(
        data=url,
        settings=SETTINGS,
    )

    assert result == "📺\n\nYT summary"
    fakes.yt_transcriber.get_transcript.assert_called_once_with(url)
    fakes.downloader.download_yt.assert_not_called()


def test_summarize_preflight_blocks_before_download(mocker):
    """Test summarize() blocks zero-quota users before any network IO."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.side_effect = LimitExceededError

    with pytest.raises(LimitExceededError):
        summarizer.summarize(
            data="https://castro.fm/episode/123",
            settings=replace(SETTINGS, user_id=1, daily_limit=0),
        )

    fakes.quota_manager.check_quota.assert_called_once_with(
        user_id=1,
        daily_limit=0,
        quantity=0,
    )
    fakes.downloader.download_castro.assert_not_called()


def test_summarize_with_document_deletes_the_upload_when_quota_check_fails(mocker):
    """Test the uploaded file is deleted if the consuming quota check fails."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.downloader.download_tg.return_value = "temp_doc"
    fakes.openrouter_files.upload.return_value = "or_file_doc123"
    mocker.patch("summary.clean_up")
    fakes.quota_manager.check_quota.side_effect = [True, LimitExceededError]

    with pytest.raises(LimitExceededError):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            mime_type="application/pdf",
            settings=replace(SETTINGS, user_id=1, daily_limit=5),
        )

    assert fakes.quota_manager.check_quota.call_args_list == [
        mocker.call(user_id=1, daily_limit=5, quantity=0),
        mocker.call(user_id=1, daily_limit=5, quantity=1),
    ]
    fakes.llm_client.run.assert_not_called()
    fakes.openrouter_files.delete.assert_called_once_with("or_file_doc123")


def test_summarize_with_document_preflight_blocks_before_download(mocker):
    """Test summarize_with_document blocks zero-quota users before download or upload."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.side_effect = LimitExceededError

    with pytest.raises(LimitExceededError):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            mime_type="application/pdf",
            settings=replace(SETTINGS, user_id=1, daily_limit=0),
        )

    fakes.quota_manager.check_quota.assert_called_once_with(
        user_id=1,
        daily_limit=0,
        quantity=0,
    )
    fakes.downloader.download_tg.assert_not_called()


def test_summarize_text_raises_on_empty_response(mocker):
    """Test summarize_text raises RetryError on repeated empty model responses."""
    summarizer, fakes = _make_summarizer(mocker)
    mocker.patch("tenacity.nap.time.sleep")
    fakes.quota_manager.check_quota.return_value = True
    fakes.llm_client.run.side_effect = AttributeError

    with pytest.raises(RetryError):
        summarizer.summarize_text(
            text="Hello world",
            settings=SETTINGS,
        )


def test_summarize_with_document_retries_a_failing_upload(mocker):
    """Test a refused upload is retried once, then wrapped, with nothing to delete."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc"
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    fakes.openrouter_files.upload.side_effect = _api_error(413)

    with pytest.raises(RetryError):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            mime_type="application/pdf",
            settings=SETTINGS,
        )

    assert fakes.openrouter_files.upload.call_count == 2
    fakes.llm_client.run.assert_not_called()
    fakes.openrouter_files.delete.assert_not_called()


def test_summarize_with_document_raises_on_empty_response(mocker):
    """Test an empty model response is retried, and each attempt's upload deleted."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc"
    mocker.patch("summary.clean_up")
    mocker.patch("tenacity.nap.time.sleep")
    fakes.openrouter_files.upload.side_effect = ["or_file_first", "or_file_second"]
    fakes.llm_client.run.side_effect = AttributeError

    with pytest.raises(RetryError):
        summarizer.summarize_with_document(
            file=mocker.MagicMock(),
            mime_type="application/pdf",
            settings=SETTINGS,
        )

    assert fakes.openrouter_files.delete.call_args_list == [
        mocker.call("or_file_first"),
        mocker.call("or_file_second"),
    ]


def test_summarize_with_document_logs_warning_on_delete_failure(mocker):
    """Test a failed delete is logged at WARNING and the summary still returned."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "temp_doc"
    mocker.patch("summary.clean_up")
    fakes.openrouter_files.upload.return_value = "or_file_doc123"
    fakes.llm_client.run.return_value = "document summary"
    fakes.openrouter_files.delete.side_effect = Exception("delete failed")
    mock_logger = mocker.patch("summary.logger")

    result = summarizer.summarize_with_document(
        file=mocker.MagicMock(),
        mime_type="application/pdf",
        settings=SETTINGS,
    )

    assert result == "document summary"
    fakes.openrouter_files.delete.assert_called_once_with("or_file_doc123")
    mock_logger.warning.assert_called_once()


def test_summarize_with_telegram_file(mocker):
    """Test summarize() downloads a Telegram File object before summarizing."""
    summarizer, fakes = _make_summarizer(mocker)
    fakes.quota_manager.check_quota.return_value = True
    fakes.downloader.download_tg.return_value = "downloaded.ogg"
    mocker.patch.object(
        summarizer,
        "_summarize_via_transcription",
        return_value="Telegram file summary",
    )
    mocker.patch("summary.clean_up")
    mock_tg_file = mocker.MagicMock(spec=File)

    result = summarizer.summarize(
        data=mock_tg_file,
        settings=SETTINGS,
    )

    assert result == "Telegram file summary"
    fakes.downloader.download_tg.assert_called_once_with(mock_tg_file, ext=".ogg")
