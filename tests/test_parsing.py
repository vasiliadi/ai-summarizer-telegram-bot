import logging

import pytest
from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import RetryError

import parsing
from exceptions import WebParseError
from parsing import ExaBackend, TavilyBackend, WebParser, parse_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parser(mocker):
    """Return (parser, mock_exa_client, mock_tavily_client)."""
    mock_exa = mocker.MagicMock()
    mock_tavily = mocker.MagicMock()
    parser = WebParser(ExaBackend(mock_exa), TavilyBackend(mock_tavily))
    return parser, mock_exa, mock_tavily


# ---------------------------------------------------------------------------
# WebParser orchestration tests
# ---------------------------------------------------------------------------

def test_parse_url_returns_exa_content(mocker):
    """parse returns Exa's text and does not call Tavily on success."""
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="Hello world.")],
    )

    result = parser.parse("https://example.com")

    assert result.text == "Hello world."
    assert result.prefix == "🌐"
    mock_exa.get_contents.assert_called_once_with(
        urls=["https://example.com"],
        text={"max_characters": 20000, "include_html_tags": True},
    )
    mock_tavily.extract.assert_not_called()


def test_parse_url_falls_back_to_tavily_when_exa_has_no_results(mocker, caplog):
    """parse falls back to Tavily when Exa returns no results."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "From Tavily."}],
        "failed_results": [],
    }

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = parser.parse("https://example.com")

    assert result.text == "From Tavily."
    assert result.prefix == "🕸️"
    mock_tavily.extract.assert_called_once_with(
        urls=["https://example.com"],
        format="markdown",
    )
    assert "Exa parsing backend failed, falling back to Tavily" in caplog.text


def test_parse_url_falls_back_to_tavily_on_exa_empty_content(mocker):
    """parse falls back to Tavily when Exa returns empty content."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="   ")],
    )
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "From Tavily."}],
        "failed_results": [],
    }

    result = parser.parse("https://example.com")

    assert result.text == "From Tavily."
    assert result.prefix == "🕸️"


def test_parse_url_falls_back_to_tavily_when_exa_retries_exhausted(mocker):
    """parse falls back to Tavily after Exa exhausts its retries."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "From Tavily."}],
        "failed_results": [],
    }

    result = parser.parse("https://example.com")

    assert result.text == "From Tavily."
    assert result.prefix == "🕸️"
    assert mock_exa.get_contents.call_count == 2
    mock_tavily.extract.assert_called_once()


def test_parse_url_retries_exa_empty_then_succeeds(mocker):
    """parse retries a transient empty Exa result and returns content."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.side_effect = [
        mocker.Mock(results=[]),
        mocker.Mock(results=[mocker.Mock(text="Hello world.")]),
    ]

    result = parser.parse("https://example.com")

    assert result.text == "Hello world."
    assert result.prefix == "🌐"
    assert mock_exa.get_contents.call_count == 2
    mock_tavily.extract.assert_not_called()


def test_parse_url_tavily_fallback_retries_timeout_then_succeeds(mocker):
    """parse's Tavily fallback retries a transient timeout then succeeds."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily.extract.side_effect = [
        TavilyTimeoutError("Request timed out after 30 seconds."),
        {
            "results": [{"url": "https://example.com", "raw_content": "From Tavily."}],
            "failed_results": [],
        },
    ]

    result = parser.parse("https://example.com")

    assert result.text == "From Tavily."
    assert result.prefix == "🕸️"
    assert mock_tavily.extract.call_count == 2


def test_parse_url_raises_when_both_backends_fail(mocker, caplog):
    """parse raises WebParseError when both Exa and Tavily fail."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily.extract.return_value = {"results": [], "failed_results": []}

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed") as exc_info,
    ):
        parser.parse("https://example.com")

    assert "Exa parsing backend failed, falling back to Tavily" in caplog.text
    assert "Tavily fallback backend also failed" in caplog.text
    assert mock_exa.get_contents.call_count == 2
    assert isinstance(exc_info.value.__cause__, WebParseError)


def test_parse_url_raises_when_tavily_fallback_returns_empty_content(mocker, caplog):
    """parse raises WebParseError when the Tavily fallback returns empty content."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "   "}],
        "failed_results": [],
    }

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed") as exc_info,
    ):
        parser.parse("https://example.com")

    assert "Tavily returned empty content for" in caplog.text
    mock_tavily.extract.assert_called_once()
    assert isinstance(exc_info.value.__cause__, WebParseError)


def test_parse_url_falls_back_when_tavily_times_out(mocker, caplog):
    """parse raises combined failure when the Tavily fallback keeps timing out."""
    mocker.patch("time.sleep")
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily.extract.side_effect = TavilyTimeoutError(
        "Request timed out after 30 seconds.",
    )

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed") as exc_info,
    ):
        parser.parse("https://example.com")

    assert mock_tavily.extract.call_count == 2
    assert "Tavily fallback backend also failed" in caplog.text
    assert isinstance(exc_info.value.__cause__, RetryError)


def test_parse_url_propagates_non_retryable_exa_error(mocker):
    """parse lets non-retryable Exa errors propagate without trying Tavily."""
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        parser.parse("https://example.com")

    mock_exa.get_contents.assert_called_once()
    mock_tavily.extract.assert_not_called()


def test_parse_url_delegates_to_web_parser(mocker):
    """parse_url routes to the module-level web_parser singleton."""
    from domain import PrefixedText

    mock_result = PrefixedText(text="hello", prefix="🌐")
    mock_parse = mocker.patch.object(parsing.web_parser, "parse", return_value=mock_result)

    result = parse_url("https://example.com")

    assert result is mock_result
    mock_parse.assert_called_once_with("https://example.com")
