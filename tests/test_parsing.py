import logging

import pytest
from tavily.errors import TimeoutError as TavilyTimeoutError

from exceptions import WebParseError
from parsing import parse_url


def test_parse_url_returns_tavily_content(mocker):
    """parse_url returns Tavily's raw_content and does not call Exa on success."""
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {
        "results": [
            {"url": "https://example.com", "raw_content": "Hello world."},
        ],
        "failed_results": [],
    }
    mock_exa = mocker.patch("parsing.exa_client")

    assert parse_url("https://example.com") == "Hello world."
    mock_tavily.extract.assert_called_once_with(
        urls=["https://example.com"],
        format="markdown",
    )
    mock_exa.get_contents.assert_not_called()


def test_parse_url_falls_back_to_exa_when_tavily_has_no_results(mocker, caplog):
    """parse_url falls back to Exa when Tavily returns no successful results."""
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {
        "results": [],
        "failed_results": [{"url": "https://example.com", "error": "not found"}],
    }
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="From Exa.")],
    )

    with caplog.at_level(logging.WARNING, logger="parsing"):
        assert parse_url("https://example.com") == "From Exa."
    mock_exa.get_contents.assert_called_once_with(
        urls=["https://example.com"],
        text={"max_characters": 20000, "include_html_tags": True},
    )
    assert "Tavily parsing backend failed, falling back to Exa" in caplog.text


def test_parse_url_falls_back_to_exa_on_tavily_empty_content(mocker):
    """parse_url falls back to Exa when Tavily returns empty content."""
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "   "}],
        "failed_results": [],
    }
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="From Exa.")],
    )

    assert parse_url("https://example.com") == "From Exa."


def test_parse_url_falls_back_to_exa_when_tavily_times_out(mocker):
    """parse_url falls back to Exa when Tavily keeps timing out (RetryError)."""
    mocker.patch("time.sleep")
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.side_effect = TavilyTimeoutError(
        "Request timed out after 30 seconds.",
    )
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="From Exa.")],
    )

    assert parse_url("https://example.com") == "From Exa."
    assert mock_tavily.extract.call_count == 2
    mock_exa.get_contents.assert_called_once()


def test_parse_url_retries_tavily_timeout_then_succeeds(mocker):
    """parse_url retries a transient Tavily timeout and returns content."""
    mocker.patch("time.sleep")
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.side_effect = [
        TavilyTimeoutError("Request timed out after 30 seconds."),
        {
            "results": [
                {"url": "https://example.com", "raw_content": "Hello world."},
            ],
            "failed_results": [],
        },
    ]
    mock_exa = mocker.patch("parsing.exa_client")

    assert parse_url("https://example.com") == "Hello world."
    assert mock_tavily.extract.call_count == 2
    mock_exa.get_contents.assert_not_called()


def test_parse_url_exa_retries_empty_then_succeeds(mocker):
    """parse_url's Exa fallback retries a transient empty result then succeeds."""
    mocker.patch("time.sleep")
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {"results": [], "failed_results": []}
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.side_effect = [
        mocker.Mock(results=[]),
        mocker.Mock(results=[mocker.Mock(text="From Exa.")]),
    ]

    assert parse_url("https://example.com") == "From Exa."
    assert mock_exa.get_contents.call_count == 2


def test_parse_url_raises_when_both_backends_fail(mocker, caplog):
    """parse_url raises WebParseError when both Tavily and Exa fail."""
    mocker.patch("time.sleep")
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {"results": [], "failed_results": []}
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(results=[])

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed"),
    ):
        parse_url("https://example.com")
    assert "Tavily parsing backend failed, falling back to Exa" in caplog.text
    assert "Exa fallback backend also failed" in caplog.text
    assert mock_exa.get_contents.call_count == 2


def test_parse_url_raises_when_exa_fallback_returns_empty_text(mocker, caplog):
    """parse_url raises WebParseError when the Exa fallback returns empty text."""
    mocker.patch("time.sleep")
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.return_value = {"results": [], "failed_results": []}
    mock_exa = mocker.patch("parsing.exa_client")
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="   ")],
    )

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed"),
    ):
        parse_url("https://example.com")
    assert "Exa returned empty content for" in caplog.text
    assert mock_exa.get_contents.call_count == 2


def test_parse_url_propagates_non_retryable_tavily_error(mocker):
    """parse_url lets non-retryable Tavily errors propagate without trying Exa."""
    mock_tavily = mocker.patch("parsing.tavily_client")
    mock_tavily.extract.side_effect = RuntimeError("boom")
    mock_exa = mocker.patch("parsing.exa_client")

    with pytest.raises(RuntimeError, match="boom"):
        parse_url("https://example.com")
    mock_tavily.extract.assert_called_once()
    mock_exa.get_contents.assert_not_called()
