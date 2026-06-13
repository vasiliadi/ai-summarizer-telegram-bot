import logging

import pytest
from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import RetryError

from exceptions import WebParseError
from parsing import parse_url


def test_parse_url_returns_exa_content(mocker):
    """parse_url returns Exa's text and does not call Tavily on success."""
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="Hello world.")],
    )
    mock_tavily = mocker.patch("parsing.tavily_client")

    assert parse_url("https://example.com") == "Hello world."
    mock_exa.get_contents.assert_called_once_with(
        urls=["https://example.com"],
        text={"max_characters": 20000, "include_html_tags": True},
    )
    mock_tavily.extract.assert_not_called()


def test_parse_url_falls_back_to_tavily_when_exa_has_no_results(mocker, caplog):
    """parse_url falls back to Tavily when Exa returns no results."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {
        "results": [
            {"url": "https://example.com", "raw_content": "From Tavily."},
        ],
        "failed_results": [],
    }

    with caplog.at_level(logging.WARNING, logger="parsing"):
        assert parse_url("https://example.com") == "From Tavily."
    mock_tavily.extract.assert_called_once_with(
        urls=["https://example.com"],
        format="markdown",
    )
    assert "Exa parsing backend failed, falling back to Tavily" in caplog.text


def test_parse_url_falls_back_to_tavily_on_exa_empty_content(mocker):
    """parse_url falls back to Tavily when Exa returns empty content."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="   ")],
    )
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "From Tavily."}],
        "failed_results": [],
    }

    assert parse_url("https://example.com") == "From Tavily."


def test_parse_url_falls_back_to_tavily_when_exa_retries_exhausted(mocker):
    """parse_url falls back to Tavily after Exa exhausts its retries."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "From Tavily."}],
        "failed_results": [],
    }

    assert parse_url("https://example.com") == "From Tavily."
    assert mock_exa.get_contents.call_count == 2
    mock_tavily.extract.assert_called_once()


def test_parse_url_retries_exa_empty_then_succeeds(mocker):
    """parse_url retries a transient empty Exa result and returns content."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.side_effect = [
        mocker.Mock(results=[]),
        mocker.Mock(results=[mocker.Mock(text="Hello world.")]),
    ]
    mock_tavily = mocker.patch("parsing.tavily_client")

    assert parse_url("https://example.com") == "Hello world."
    assert mock_exa.get_contents.call_count == 2
    mock_tavily.extract.assert_not_called()


def test_parse_url_tavily_fallback_retries_timeout_then_succeeds(mocker):
    """parse_url's Tavily fallback retries a transient timeout then succeeds."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.side_effect = [
        TavilyTimeoutError("Request timed out after 30 seconds."),
        {
            "results": [
                {"url": "https://example.com", "raw_content": "From Tavily."},
            ],
            "failed_results": [],
        },
    ]

    assert parse_url("https://example.com") == "From Tavily."
    assert mock_tavily.extract.call_count == 2


def test_parse_url_raises_when_both_backends_fail(mocker, caplog):
    """parse_url raises WebParseError when both Exa and Tavily fail."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {"results": [], "failed_results": []}

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed") as exc_info,
    ):
        parse_url("https://example.com")
    assert "Exa parsing backend failed, falling back to Tavily" in caplog.text
    assert "Tavily fallback backend also failed" in caplog.text
    assert mock_exa.get_contents.call_count == 2
    assert isinstance(exc_info.value.__cause__, WebParseError)


def test_parse_url_raises_when_tavily_fallback_returns_empty_content(mocker, caplog):
    """parse_url raises WebParseError when the Tavily fallback returns empty."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "   "}],
        "failed_results": [],
    }

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed") as exc_info,
    ):
        parse_url("https://example.com")
    assert "Tavily returned empty content for" in caplog.text
    mock_tavily.extract.assert_called_once()
    assert isinstance(exc_info.value.__cause__, WebParseError)


def test_parse_url_falls_back_when_tavily_times_out(mocker, caplog):
    """parse_url raises combined failure when the Tavily fallback keeps timing out."""
    mocker.patch("time.sleep")
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.side_effect = TavilyTimeoutError(
        "Request timed out after 30 seconds.",
    )

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed") as exc_info,
    ):
        parse_url("https://example.com")
    assert mock_tavily.extract.call_count == 2
    assert "Tavily fallback backend also failed" in caplog.text
    assert isinstance(exc_info.value.__cause__, RetryError)


def test_parse_url_propagates_non_retryable_exa_error(mocker):
    """parse_url lets non-retryable Exa errors propagate without trying Tavily."""
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.side_effect = RuntimeError("boom")
    mock_tavily = mocker.patch("parsing.tavily_client")

    with pytest.raises(RuntimeError, match="boom"):
        parse_url("https://example.com")
    mock_exa.get_contents.assert_called_once()
    mock_tavily.extract.assert_not_called()
