

import pytest
from replicate.exceptions import ModelError
from youtube_transcript_api._errors import NoTranscriptFound

from transcription import get_yt_transcript, transcribe


def test_get_yt_transcript_youtube_watch_url(mocker):
    """Test get_yt_transcript with standard YouTube watch URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    # Mocking the fetch results
    mock_ytt.return_value.fetch.return_value = [{"text": "Hello", "start": 0, "duration": 1}]
    mock_formatter.return_value.format_transcript.return_value = "Hello"

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert result == "Hello"
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")

def test_get_yt_transcript_youtu_be_url(mocker):
    """Test get_yt_transcript with short youtu.be URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    mock_ytt.return_value.fetch.return_value = []
    mock_formatter.return_value.format_transcript.return_value = "Hello short"

    url = "https://youtu.be/dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert result == "Hello short"
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")

def test_get_yt_transcript_youtube_live_url(mocker):
    """Test get_yt_transcript with YouTube live URL."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    mock_ytt.return_value.fetch.return_value = []
    mock_formatter.return_value.format_transcript.return_value = "Hello live"

    url = "https://www.youtube.com/live/dQw4w9WgXcQ"
    result = get_yt_transcript(url)

    assert result == "Hello live"
    mock_ytt.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ")

def test_get_yt_transcript_unknown_url():
    """Test get_yt_transcript raises ValueError for unknown URL formats."""
    with pytest.raises(ValueError, match="Unknown URL"):
        get_yt_transcript("https://example.com/not-youtube")

def test_get_yt_transcript_fallback_languages(mocker):
    """Test get_yt_transcript falls back to other languages if NoTranscriptFound."""
    mock_ytt = mocker.patch("transcription.YouTubeTranscriptApi")
    mock_formatter = mocker.patch("transcription.TextFormatter")

    # First call to fetch raises NoTranscriptFound
    mock_ytt.return_value.fetch.side_effect = [NoTranscriptFound("vid", "en", []), [{"text": "Hola"}]]
    # Mock list to return language codes
    mock_transcript = mocker.MagicMock()
    mock_transcript.language_code = "es"
    mock_ytt.return_value.list.return_value = [mock_transcript]

    mock_formatter.return_value.format_transcript.return_value = "Hola"

    url = "https://youtu.be/vid"
    result = get_yt_transcript(url)

    assert result == "Hola"
    # Verify it was called twice, once without languages, once with languages
    calls = mock_ytt.return_value.fetch.call_args_list
    assert calls[0].args == ("vid",)
    assert calls[1].args == ("vid",)
    assert calls[1].kwargs == {"languages": ["es"]}

def test_transcribe_happy_path(mocker):
    """Test transcribing an audio file successfully via Replicate."""
    mock_replicate = mocker.patch("transcription.replicate_client")
    mocker.patch("transcription.Path.open", mocker.mock_open())
    mocker.patch("transcription.time.sleep") # Don't actually wait

    # Mock the prediction object and its lifecycle
    mock_prediction = mocker.MagicMock()
    mock_prediction.status = "processing"
    # sequence of statuses: processing -> succeeded
    # status is checked twice per loop (while condition and inside if)
    type(mock_prediction).status = mocker.PropertyMock(side_effect=["processing", "processing", "succeeded", "succeeded"])
    mock_prediction.output = {"segments": [{"text": "Hello "}, {"text": "world!"}]}

    mock_replicate.models.get.return_value.versions.list.return_value = [mocker.MagicMock(id="v1")]
    mock_replicate.predictions.create.return_value = mock_prediction

    result = transcribe("test.ogg")

    assert result == "Hello world!"
    mock_prediction.reload.assert_called_once()

def test_transcribe_failed_prediction(mocker):
    """Test transcribe raises ModelError when prediction fails."""
    mock_replicate = mocker.patch("transcription.replicate_client")
    mocker.patch("transcription.Path.open", mocker.mock_open())

    mock_prediction = mocker.MagicMock()
    mock_prediction.status = "failed"
    mock_replicate.predictions.create.return_value = mock_prediction
    mock_replicate.models.get.return_value.versions.list.return_value = [mocker.MagicMock(id="v1")]

    with pytest.raises(ModelError):
        transcribe("test.ogg")

def test_transcribe_null_output(mocker):
    """Test transcribe raises ModelError when prediction output is None."""
    mock_replicate = mocker.patch("transcription.replicate_client")
    mocker.patch("transcription.Path.open", mocker.mock_open())

    mock_prediction = mocker.MagicMock()
    mock_prediction.status = "succeeded"
    mock_prediction.output = None
    mock_replicate.predictions.create.return_value = mock_prediction
    mock_replicate.models.get.return_value.versions.list.return_value = [mocker.MagicMock(id="v1")]

    with pytest.raises(ModelError):
        transcribe("test.ogg")
