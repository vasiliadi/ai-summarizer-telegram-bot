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


def test_parse_url_resolves_then_delegates_to_web_parser(mocker):
    """parse_url resolves redirects, then routes the final URL to web_parser."""
    from domain import PrefixedText

    mocker.patch.object(
        parsing.WebParser,
        "resolve_url",
        return_value="https://example.com/final",
    )
    mock_result = PrefixedText(text="hello", prefix="🌐")
    mock_parse = mocker.patch.object(parsing.web_parser, "parse", return_value=mock_result)

    result = parse_url("https://example.com/start")

    assert result is mock_result
    mock_parse.assert_called_once_with("https://example.com/final")


# ---------------------------------------------------------------------------
# _is_public_url tests
# ---------------------------------------------------------------------------

def test_is_public_url_returns_false_for_missing_hostname():
    """_is_public_url returns False when the URL has no hostname."""
    from parsing import _is_public_url

    assert _is_public_url("https:///path") is False


def test_is_public_url_returns_true_for_public_ip(mocker):
    """_is_public_url returns True when the hostname resolves to a public IP."""
    from parsing import _is_public_url

    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    )
    assert _is_public_url("https://example.com/article") is True


def test_is_public_url_returns_false_for_private_ip(mocker):
    """_is_public_url returns False when the hostname resolves to a private IP."""
    from parsing import _is_public_url

    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("192.168.1.1", 0))],
    )
    assert _is_public_url("https://internal.example.com/") is False


def test_is_public_url_returns_false_for_loopback(mocker):
    """_is_public_url returns False for localhost."""
    from parsing import _is_public_url

    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("127.0.0.1", 0))],
    )
    assert _is_public_url("http://localhost/admin") is False


def test_is_public_url_returns_false_for_link_local(mocker):
    """_is_public_url returns False for cloud metadata endpoint."""
    from parsing import _is_public_url

    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("169.254.169.254", 0))],
    )
    assert _is_public_url("http://169.254.169.254/latest/meta-data/") is False


def test_is_public_url_returns_false_when_dns_fails(mocker):
    """_is_public_url returns False when DNS resolution raises OSError."""
    from parsing import _is_public_url

    mocker.patch("parsing.socket.getaddrinfo", side_effect=OSError("NXDOMAIN"))
    assert _is_public_url("https://nonexistent.invalid/") is False


def test_is_public_url_returns_false_when_any_addr_is_private(mocker):
    """_is_public_url returns False if any resolved address is private (dual-stack)."""
    from parsing import _is_public_url

    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[
            (None, None, None, None, ("93.184.216.34", 0)),
            (None, None, None, None, ("10.0.0.1", 0)),
        ],
    )
    assert _is_public_url("https://example.com/") is False


# ---------------------------------------------------------------------------
# WebParser.resolve_url tests
# ---------------------------------------------------------------------------

def test_resolve_url_returns_final_url_after_redirect(mocker):
    """resolve_url returns the redirected URL and closes the response."""
    mocker.patch("parsing._is_public_url", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="https://example.com/final")
    mock_get = mocker.patch("parsing.requests.get", return_value=mock_resp)

    result = WebParser.resolve_url("https://example.com/start")

    assert result == "https://example.com/final"
    mock_resp.close.assert_called_once_with()
    assert mock_get.call_args.args == ("https://example.com/start",)
    assert mock_get.call_args.kwargs["allow_redirects"] is True
    assert mock_get.call_args.kwargs["stream"] is True


def test_resolve_url_returns_original_when_no_redirect(mocker):
    """resolve_url returns the input unchanged when there is no redirect."""
    mocker.patch("parsing._is_public_url", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="https://example.com/article")
    mocker.patch("parsing.requests.get", return_value=mock_resp)

    result = WebParser.resolve_url("https://example.com/article")

    assert result == "https://example.com/article"


def test_resolve_url_falls_back_to_original_on_error(mocker, caplog):
    """resolve_url returns the original URL when the request raises."""
    mocker.patch("parsing._is_public_url", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mocker.patch("parsing.requests.get", side_effect=RuntimeError("boom"))

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = WebParser.resolve_url("https://example.com/article")

    assert result == "https://example.com/article"
    assert "Could not resolve redirects" in caplog.text


def test_resolve_url_passes_proxy_when_configured(mocker):
    """resolve_url forwards a configured proxy to requests.get."""
    mocker.patch("parsing._is_public_url", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="https://user:pass@proxy.com:1234")
    mock_resp = mocker.Mock(url="https://example.com/article")
    mock_get = mocker.patch("parsing.requests.get", return_value=mock_resp)

    WebParser.resolve_url("https://example.com/article")

    assert mock_get.call_args.kwargs["proxy"] == "https://user:pass@proxy.com:1234"


def test_resolve_url_omits_proxy_when_none_configured(mocker):
    """resolve_url passes proxy=None when no proxy is set."""
    mocker.patch("parsing._is_public_url", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="https://example.com/article")
    mock_get = mocker.patch("parsing.requests.get", return_value=mock_resp)

    WebParser.resolve_url("https://example.com/article")

    assert mock_get.call_args.kwargs["proxy"] is None


def test_resolve_url_blocks_non_public_initial_url(mocker, caplog):
    """resolve_url returns the original URL without fetching for a private host."""
    mocker.patch("parsing._is_public_url", side_effect=lambda u: u != "http://192.168.1.1/")
    mock_get = mocker.patch("parsing.requests.get")

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = WebParser.resolve_url("http://192.168.1.1/")

    assert result == "http://192.168.1.1/"
    mock_get.assert_not_called()
    assert "Blocked non-public URL" in caplog.text


def test_resolve_url_blocks_redirect_to_private_host(mocker, caplog):
    """resolve_url returns the original URL when a redirect lands on a private host."""
    mocker.patch(
        "parsing._is_public_url",
        side_effect=lambda u: "example.com" in u,
    )
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="http://169.254.169.254/latest/meta-data/")
    mocker.patch("parsing.requests.get", return_value=mock_resp)

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = WebParser.resolve_url("https://example.com/start")

    assert result == "https://example.com/start"
    assert "Blocked redirect to non-public host" in caplog.text
