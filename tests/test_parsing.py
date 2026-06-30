import logging

import pytest
from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import RetryError

import parsing
from domain import PrefixedText
from exceptions import WebParseError
from parsing import ExaBackend, TavilyBackend, UrlResolver, WebParser, parse_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parser(mocker):
    """Return (parser, mock_exa_client, mock_tavily_client).

    Injects a stub resolver that passes the URL through unchanged so the
    orchestration tests never touch the network.
    """
    mock_exa = mocker.MagicMock()
    mock_tavily = mocker.MagicMock()
    resolver = mocker.Mock()
    resolver.resolve.side_effect = lambda url: url
    parser = WebParser(ExaBackend(mock_exa), TavilyBackend(mock_tavily), resolver)
    return parser, mock_exa, mock_tavily


# ---------------------------------------------------------------------------
# WebParser orchestration tests
# ---------------------------------------------------------------------------


def test_parse_url_returns_exa_content(mocker):
    """Test parse returns Exa's text and does not call Tavily on success."""
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
        max_age_hours=0,
    )
    mock_tavily.extract.assert_not_called()


def test_parse_url_falls_back_to_tavily_when_exa_has_no_results(mocker, caplog):
    """Test parse falls back to Tavily when Exa returns no results."""
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
    """Test parse falls back to Tavily when Exa returns empty content."""
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
    """Test parse falls back to Tavily after Exa exhausts its retries."""
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
    """Test parse retries a transient empty Exa result and returns content."""
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
    """Test parse's Tavily fallback retries a transient timeout then succeeds."""
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
    """Test parse raises WebParseError when both Exa and Tavily fail."""
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
    """Test parse raises WebParseError when the Tavily fallback returns empty content."""
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
    """Test parse raises combined failure when the Tavily fallback keeps timing out."""
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
    """Test parse lets non-retryable Exa errors propagate without trying Tavily."""
    parser, mock_exa, mock_tavily = _make_parser(mocker)
    mock_exa.get_contents.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        parser.parse("https://example.com")

    mock_exa.get_contents.assert_called_once()
    mock_tavily.extract.assert_not_called()


def test_parse_resolves_url_before_extracting(mocker):
    """Test parse resolves the URL via the injected resolver before calling backends."""
    mock_exa = mocker.MagicMock()
    mock_tavily = mocker.MagicMock()
    resolver = mocker.Mock()
    resolver.resolve.return_value = "https://example.com/final"
    parser = WebParser(ExaBackend(mock_exa), TavilyBackend(mock_tavily), resolver)
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="Hi.")],
    )

    result = parser.parse("https://example.com/start")

    assert result.text == "Hi."
    resolver.resolve.assert_called_once_with("https://example.com/start")
    mock_exa.get_contents.assert_called_once_with(
        urls=["https://example.com/final"],
        text={"max_characters": 20000, "include_html_tags": True},
        max_age_hours=0,
    )


def test_parse_url_delegates_to_web_parser(mocker):
    """Test parse_url routes to the module-level web_parser singleton."""
    mock_result = PrefixedText(text="hello", prefix="🌐")
    mock_parse = mocker.patch.object(
        parsing.web_parser,
        "parse",
        return_value=mock_result,
    )

    result = parse_url("https://example.com/start")

    assert result is mock_result
    mock_parse.assert_called_once_with("https://example.com/start")


# ---------------------------------------------------------------------------
# UrlResolver._is_public tests
# ---------------------------------------------------------------------------


def test_is_public_returns_false_for_missing_hostname():
    """_is_public returns False when the URL has no hostname."""
    assert UrlResolver._is_public("https:///path") is False


def test_is_public_returns_true_for_public_ip(mocker):
    """_is_public returns True when the hostname resolves to a public IP."""
    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    )
    assert UrlResolver._is_public("https://example.com/article") is True


def test_is_public_returns_false_for_private_ip(mocker):
    """_is_public returns False when the hostname resolves to a private IP."""
    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("192.168.1.1", 0))],
    )
    assert UrlResolver._is_public("https://internal.example.com/") is False


def test_is_public_returns_false_for_loopback(mocker):
    """_is_public returns False for localhost."""
    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("127.0.0.1", 0))],
    )
    assert UrlResolver._is_public("http://localhost/admin") is False


def test_is_public_returns_false_for_link_local(mocker):
    """_is_public returns False for cloud metadata endpoint."""
    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("169.254.169.254", 0))],
    )
    assert UrlResolver._is_public("http://169.254.169.254/latest/meta-data/") is False


def test_is_public_returns_false_when_dns_fails(mocker):
    """_is_public returns False when DNS resolution raises OSError."""
    mocker.patch("parsing.socket.getaddrinfo", side_effect=OSError("NXDOMAIN"))
    assert UrlResolver._is_public("https://nonexistent.invalid/") is False


def test_is_public_returns_false_on_invalid_idna_hostname(mocker):
    """_is_public returns False when getaddrinfo raises UnicodeError (bad IDNA label)."""
    mocker.patch(
        "parsing.socket.getaddrinfo",
        side_effect=UnicodeError("label empty or too long"),
    )
    assert UrlResolver._is_public("http://" + "a" * 64 + ".com/") is False


def test_is_public_returns_false_when_any_addr_is_private(mocker):
    """_is_public returns False if any resolved address is private (dual-stack)."""
    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[
            (None, None, None, None, ("93.184.216.34", 0)),
            (None, None, None, None, ("10.0.0.1", 0)),
        ],
    )
    assert UrlResolver._is_public("https://example.com/") is False


# ---------------------------------------------------------------------------
# UrlResolver.resolve tests
# ---------------------------------------------------------------------------


def test_resolve_returns_final_url_after_redirect(mocker):
    """Test resolve returns the redirected URL and closes the response."""
    mocker.patch.object(parsing.UrlResolver, "_is_public", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="https://example.com/final")
    mock_get = mocker.patch("parsing.requests.get", return_value=mock_resp)

    result = UrlResolver().resolve("https://example.com/start")

    assert result == "https://example.com/final"
    mock_resp.close.assert_called_once_with()
    assert mock_get.call_args.args == ("https://example.com/start",)
    assert mock_get.call_args.kwargs["allow_redirects"] is True
    assert mock_get.call_args.kwargs["stream"] is True


def test_resolve_returns_original_when_no_redirect(mocker):
    """Test resolve returns the input unchanged when there is no redirect."""
    mocker.patch.object(parsing.UrlResolver, "_is_public", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="https://example.com/article")
    mocker.patch("parsing.requests.get", return_value=mock_resp)

    result = UrlResolver().resolve("https://example.com/article")

    assert result == "https://example.com/article"
    mock_resp.close.assert_called_once_with()


def test_resolve_falls_back_to_original_on_error(mocker, caplog):
    """Test resolve returns the original URL when the request raises."""
    mocker.patch.object(parsing.UrlResolver, "_is_public", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mocker.patch("parsing.requests.get", side_effect=RuntimeError("boom"))

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = UrlResolver().resolve("https://example.com/article")

    assert result == "https://example.com/article"
    assert "Could not resolve redirects" in caplog.text


def test_resolve_passes_proxy_when_configured(mocker):
    """Test resolve forwards a configured proxy to requests.get."""
    mocker.patch.object(parsing.UrlResolver, "_is_public", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="https://user:pass@proxy.com:1234")
    mock_resp = mocker.Mock(url="https://example.com/article")
    mock_get = mocker.patch("parsing.requests.get", return_value=mock_resp)

    UrlResolver().resolve("https://example.com/article")

    assert mock_get.call_args.kwargs["proxy"] == "https://user:pass@proxy.com:1234"


def test_resolve_omits_proxy_when_none_configured(mocker):
    """Test resolve passes proxy=None when no proxy is set."""
    mocker.patch.object(parsing.UrlResolver, "_is_public", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="https://example.com/article")
    mock_get = mocker.patch("parsing.requests.get", return_value=mock_resp)

    UrlResolver().resolve("https://example.com/article")

    assert mock_get.call_args.kwargs["proxy"] is None


def test_resolve_passes_configured_timeout(mocker):
    """Test resolve forwards the instance timeout to requests.get."""
    mocker.patch.object(parsing.UrlResolver, "_is_public", return_value=True)
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="https://example.com/article")
    mock_get = mocker.patch("parsing.requests.get", return_value=mock_resp)

    UrlResolver(timeout=3).resolve("https://example.com/article")

    assert mock_get.call_args.kwargs["timeout"] == 3


def test_resolve_blocks_non_public_initial_url(mocker, caplog):
    """Test resolve returns the original URL without fetching for a private host."""
    mocker.patch.object(
        parsing.UrlResolver,
        "_is_public",
        side_effect=lambda u: u != "http://192.168.1.1/",
    )
    mock_get = mocker.patch("parsing.requests.get")

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = UrlResolver().resolve("http://192.168.1.1/")

    assert result == "http://192.168.1.1/"
    mock_get.assert_not_called()
    assert "Blocked non-public URL" in caplog.text


def test_resolve_blocks_redirect_to_private_host(mocker, caplog):
    """Test resolve returns the original URL when a redirect lands on a private host."""
    mocker.patch.object(
        parsing.UrlResolver,
        "_is_public",
        side_effect=lambda u: "example.com" in u,
    )
    mocker.patch("parsing.get_proxy", return_value="")
    mock_resp = mocker.Mock(url="http://169.254.169.254/latest/meta-data/")
    mocker.patch("parsing.requests.get", return_value=mock_resp)

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = UrlResolver().resolve("https://example.com/start")

    assert result == "https://example.com/start"
    assert "Blocked redirect to non-public host" in caplog.text
