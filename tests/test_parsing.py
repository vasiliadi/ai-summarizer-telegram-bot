import pytest
from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import RetryError

from exceptions import WebParseError
from parsing import parse_url


def test_parse_url_returns_raw_content(mocker):
    """parse_url returns the raw_content from the first Tavily result."""
    mock_client = mocker.patch("parsing.tavily_client")
    mock_client.extract.return_value = {
        "results": [
            {"url": "https://example.com", "raw_content": "Hello world."},
        ],
        "failed_results": [],
    }

    assert parse_url("https://example.com") == "Hello world."
    mock_client.extract.assert_called_once_with(
        urls=["https://example.com"],
        format="markdown",
    )


def test_parse_url_raises_when_no_results(mocker):
    """parse_url raises WebParseError when Tavily returns no successful results."""
    mock_client = mocker.patch("parsing.tavily_client")
    mock_client.extract.return_value = {
        "results": [],
        "failed_results": [{"url": "https://example.com", "error": "not found"}],
    }

    with pytest.raises(WebParseError):
        parse_url("https://example.com")


def test_parse_url_raises_on_empty_raw_content(mocker):
    """parse_url raises WebParseError when raw_content is empty/whitespace."""
    mock_client = mocker.patch("parsing.tavily_client")
    mock_client.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "   "}],
        "failed_results": [],
    }

    with pytest.raises(WebParseError):
        parse_url("https://example.com")


def test_parse_url_propagates_non_retryable_exception(mocker):
    """parse_url lets non-retryable Tavily exceptions propagate immediately.

    Only TavilyTimeoutError is retried; other exceptions are not.
    """
    mock_client = mocker.patch("parsing.tavily_client")
    mock_client.extract.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        parse_url("https://example.com")

    mock_client.extract.assert_called_once()


def test_parse_url_retries_on_timeout_then_succeeds(mocker):
    """parse_url retries a TavilyTimeoutError and returns content on success."""
    mocker.patch("time.sleep")
    mock_client = mocker.patch("parsing.tavily_client")
    mock_client.extract.side_effect = [
        TavilyTimeoutError("Request timed out after 30 seconds."),
        {
            "results": [
                {"url": "https://example.com", "raw_content": "Hello world."},
            ],
            "failed_results": [],
        },
    ]

    assert parse_url("https://example.com") == "Hello world."
    assert mock_client.extract.call_count == 2


def test_parse_url_raises_retry_error_when_timeout_persists(mocker):
    """parse_url raises RetryError when TavilyTimeoutError keeps occurring."""
    mocker.patch("time.sleep")
    mock_client = mocker.patch("parsing.tavily_client")
    mock_client.extract.side_effect = TavilyTimeoutError(
        "Request timed out after 30 seconds.",
    )

    with pytest.raises(RetryError):
        parse_url("https://example.com")

    assert mock_client.extract.call_count == 3
