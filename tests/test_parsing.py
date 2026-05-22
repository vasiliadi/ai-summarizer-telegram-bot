import pytest

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


def test_parse_url_propagates_tavily_exception(mocker):
    """parse_url lets Tavily exceptions propagate (no retry wrapper)."""
    mock_client = mocker.patch("parsing.tavily_client")
    mock_client.extract.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        parse_url("https://example.com")
