import logging

import pytest
from tavily.errors import TimeoutError as TavilyTimeoutError
from tenacity import RetryError

from config import (
    BLOCK_DETECTOR_MODEL_ID,
    OPENROUTER_APP_TITLE,
    OPENROUTER_APP_URL,
    OPENROUTER_DECISIONS_URL,
)
from exceptions import WebParseError
from parsing import (
    BlockedPageDetector,
    ExaBackend,
    TavilyBackend,
    UrlResolver,
    WebParser,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parser(mocker, detector=None):
    """Return (parser, mock_exa_client, mock_tavily_client).

    Injects a stub resolver that passes the URL through unchanged, and by
    default a detector that blocks nothing, so the orchestration tests never
    touch the network.
    """
    mock_exa = mocker.MagicMock()
    mock_tavily = mocker.MagicMock()
    resolver = mocker.Mock()
    resolver.resolve.side_effect = lambda url: url
    if detector is None:
        detector = mocker.Mock()
        detector.is_blocked.return_value = False
    parser = WebParser(
        ExaBackend(mock_exa),
        TavilyBackend(mock_tavily),
        resolver,
        detector,
    )
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
        text={"verbosity": "compact"},
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
    assert mock_exa.get_contents.call_count == 2
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
    detector = mocker.Mock()
    detector.is_blocked.return_value = False
    parser = WebParser(
        ExaBackend(mock_exa),
        TavilyBackend(mock_tavily),
        resolver,
        detector,
    )
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="Hi.")],
    )

    result = parser.parse("https://example.com/start")

    assert result.text == "Hi."
    resolver.resolve.assert_called_once_with("https://example.com/start")
    mock_exa.get_contents.assert_called_once_with(
        urls=["https://example.com/final"],
        text={"verbosity": "compact"},
        max_age_hours=0,
    )


# ---------------------------------------------------------------------------
# UrlResolver._is_public tests
# ---------------------------------------------------------------------------


def test_is_public_returns_false_for_missing_hostname():
    """_is_public returns False when the URL has no hostname."""
    assert UrlResolver._is_public("https:///path") is False


@pytest.mark.parametrize(
    "url",
    ["gopher://example.com:25/_HELO", "ftp://example.com/", "file:///etc/passwd"],
)
def test_is_public_rejects_non_http_schemes(mocker, url):
    """_is_public returns False for any scheme other than http(s)."""
    mocker.patch(
        "parsing.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    )
    assert UrlResolver._is_public(url) is False


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


def _patch_get(mocker, **kwargs):
    session = mocker.patch(
        "parsing.requests.Session",
    ).return_value.__enter__.return_value
    session.get = mocker.Mock(**kwargs)
    return session.get


def _response(mocker, status_code=200, location=None):
    headers = {"location": location} if location else {}
    return mocker.Mock(status_code=status_code, headers=headers)


def test_resolve_follows_redirects_hop_by_hop(mocker):
    """Test resolve follows each hop itself, resolving relative locations."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    # proxy_rotation() reads config.PROXIES, which python-dotenv backfills from the
    # developer's real .env (conftest.py never sets PROXY) — patch it so the
    # test result does not depend on what happens to be in that file.
    mocker.patch("utils.PROXIES", [])
    responses = [
        _response(mocker, 301, "https://t.example.com/x"),
        _response(mocker, 302, "/final"),
        _response(mocker, 200),
    ]
    mock_get = _patch_get(mocker, side_effect=responses)

    result = resolver.resolve("https://example.com/start")

    assert result == "https://t.example.com/final"
    assert [c.args[0] for c in mock_get.call_args_list] == [
        "https://example.com/start",
        "https://t.example.com/x",
        "https://t.example.com/final",
    ]
    assert all(c.kwargs["allow_redirects"] is False for c in mock_get.call_args_list)
    assert all(c.kwargs["stream"] is True for c in mock_get.call_args_list)
    for response in responses:
        response.close.assert_called_once_with()


def test_resolve_returns_original_when_no_redirect(mocker):
    """Test resolve returns the input unchanged when there is no redirect."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    _patch_get(mocker, return_value=_response(mocker, 200))

    assert resolver.resolve("https://example.com/article") == (
        "https://example.com/article"
    )


def test_resolve_stops_at_a_redirect_without_location(mocker):
    """Test resolve treats a redirect status with no Location as the destination."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    _patch_get(mocker, return_value=_response(mocker, 302))

    assert resolver.resolve("https://example.com/a") == "https://example.com/a"


def test_resolve_gives_up_on_a_redirect_loop(mocker, caplog):
    """Test resolve returns the original URL once the request cap is reached."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    mock_get = _patch_get(
        mocker,
        side_effect=lambda *_a, **_k: _response(mocker, 302, "https://example.com/b"),
    )

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = resolver.resolve("https://example.com/a")

    assert result == "https://example.com/a"
    assert mock_get.call_count == UrlResolver._MAX_REQUESTS
    assert "Too many redirects" in caplog.text


def test_resolve_falls_back_to_original_on_error(mocker, caplog):
    """Test resolve returns the original URL when the request raises."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    _patch_get(mocker, side_effect=RuntimeError("boom"))

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = resolver.resolve("https://example.com/article")

    assert result == "https://example.com/article"
    assert "Could not resolve redirects" in caplog.text


def test_resolve_passes_proxy_when_configured(mocker):
    """Test resolve forwards a configured proxy to requests.get."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", ["https://user:pass@proxy.com:1234"])
    mock_get = _patch_get(mocker, return_value=_response(mocker))

    resolver.resolve("https://example.com/article")

    assert mock_get.call_args.kwargs["proxy"] == "https://user:pass@proxy.com:1234"


def test_resolve_omits_proxy_when_none_configured(mocker):
    """Test resolve passes proxy=None when no proxy is set."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    mock_get = _patch_get(mocker, return_value=_response(mocker))

    resolver.resolve("https://example.com/article")

    assert mock_get.call_args.kwargs["proxy"] is None


def test_resolve_passes_its_timeout(mocker):
    """Test resolve bounds the request with a timeout."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    mock_get = _patch_get(mocker, return_value=_response(mocker))

    resolver.resolve("https://example.com/article")

    assert mock_get.call_args.kwargs["timeout"] == 10


def test_resolve_blocks_non_public_initial_url(mocker, caplog):
    """Test resolve returns the original URL without fetching for a private host."""
    resolver = UrlResolver()
    mocker.patch.object(
        resolver,
        "_is_public",
        side_effect=lambda u: u != "http://192.168.1.1/",
    )
    mock_get = _patch_get(mocker)

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = resolver.resolve("http://192.168.1.1/")

    assert result == "http://192.168.1.1/"
    mock_get.assert_not_called()
    assert "Blocked non-public URL" in caplog.text


def test_resolve_never_requests_a_private_redirect_hop(mocker, caplog):
    """Test a redirect to a private host is refused before that host is requested."""
    resolver = UrlResolver()
    metadata = "http://169.254.169.254/latest/meta-data/"
    mocker.patch.object(resolver, "_is_public", side_effect=lambda u: u != metadata)
    mocker.patch("utils.PROXIES", [])
    mock_get = _patch_get(
        mocker,
        return_value=_response(mocker, 302, metadata),
    )

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = resolver.resolve("https://example.com/start")

    assert result == "https://example.com/start"
    assert [c.args[0] for c in mock_get.call_args_list] == ["https://example.com/start"]
    assert "Blocked redirect to non-public host" in caplog.text


def test_resolve_keeps_the_last_good_hop_when_a_later_one_fails(mocker, caplog):
    """Test a failing hop returns the last target that passed the guard."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    _patch_get(
        mocker,
        side_effect=[
            _response(mocker, 301, "https://news.example.com/article"),
            RuntimeError("timeout"),
        ],
    )

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = resolver.resolve("https://t.example.com/abc")

    assert result == "https://news.example.com/article"
    assert "Could not resolve redirects" in caplog.text


def test_resolve_requotes_a_non_ascii_location(mocker):
    """Test a Location with raw non-ASCII characters and spaces is percent-encoded."""
    resolver = UrlResolver()
    mocker.patch.object(resolver, "_is_public", return_value=True)
    mocker.patch("utils.PROXIES", [])
    mock_get = _patch_get(
        mocker,
        side_effect=[_response(mocker, 302, "/статья/my article"), _response(mocker)],
    )

    result = resolver.resolve("https://example.com/start")

    assert (
        result
        == "https://example.com/%D1%81%D1%82%D0%B0%D1%82%D1%8C%D1%8F/my%20article"
    )
    assert mock_get.call_args.args == (result,)


# ---------------------------------------------------------------------------
# Block-page detection
# ---------------------------------------------------------------------------


def test_parse_url_keeps_exa_content_when_not_blocked(mocker):
    """Test parse returns Exa's text when the detector passes it."""
    detector = mocker.Mock()
    detector.is_blocked.return_value = False
    parser, mock_exa, mock_tavily = _make_parser(mocker, detector)
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="Hello world.")],
    )

    result = parser.parse("https://example.com")

    assert result.text == "Hello world."
    assert result.prefix == "🌐"
    detector.is_blocked.assert_called_once_with("Hello world.", "https://example.com")
    mock_tavily.extract.assert_not_called()


def test_parse_url_falls_back_to_tavily_on_block_page(mocker, caplog):
    """Test a block page falls back to Tavily without re-running Exa."""
    mock_sleep = mocker.patch("time.sleep")
    detector = mocker.Mock()
    detector.is_blocked.side_effect = [True, False]
    parser, mock_exa, mock_tavily = _make_parser(mocker, detector)
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="App unavailable in your region.")],
    )
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "From Tavily."}],
        "failed_results": [],
    }

    with caplog.at_level(logging.WARNING, logger="parsing"):
        result = parser.parse("https://example.com")

    assert result.text == "From Tavily."
    assert result.prefix == "🕸️"
    mock_exa.get_contents.assert_called_once()
    mock_sleep.assert_not_called()
    assert "Exa returned a block page for https://example.com" in caplog.text
    assert detector.is_blocked.call_args_list == [
        mocker.call("App unavailable in your region.", "https://example.com"),
        mocker.call("From Tavily.", "https://example.com"),
    ]


def test_parse_url_rejects_tavily_block_page(mocker, caplog):
    """Test a block page from the fallback fails the parse, not summarized."""
    detector = mocker.Mock()
    detector.is_blocked.return_value = True
    parser, mock_exa, mock_tavily = _make_parser(mocker, detector)
    mock_exa.get_contents.return_value = mocker.Mock(results=[])
    mocker.patch("time.sleep")
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "Just a moment..."}],
        "failed_results": [],
    }

    with (
        caplog.at_level(logging.WARNING, logger="parsing"),
        pytest.raises(WebParseError, match="Both parsing backends failed"),
    ):
        parser.parse("https://example.com")

    assert "Tavily returned a block page for https://example.com" in caplog.text


def test_parse_url_fails_when_both_backends_return_block_pages(mocker):
    """Test block pages from both backends fail the parse with one fetch each."""
    mock_sleep = mocker.patch("time.sleep")
    detector = mocker.Mock()
    detector.is_blocked.return_value = True
    parser, mock_exa, mock_tavily = _make_parser(mocker, detector)
    mock_exa.get_contents.return_value = mocker.Mock(
        results=[mocker.Mock(text="Access Denied")],
    )
    mock_tavily.extract.return_value = {
        "results": [{"url": "https://example.com", "raw_content": "Access Denied"}],
        "failed_results": [],
    }

    with pytest.raises(WebParseError, match="Both parsing backends failed"):
        parser.parse("https://example.com")

    mock_exa.get_contents.assert_called_once()
    mock_tavily.extract.assert_called_once()
    mock_sleep.assert_not_called()


def _decisions_response(mocker, noul):
    response = mocker.Mock()
    response.json.return_value = {
        "model": "typesafe/jev-1.13-20260917",
        "answers": {"blocked": {"type": "noul", "noul": noul}},
    }
    return response


def test_is_blocked_asks_jev_with_the_page_as_state(mocker):
    """Test is_blocked posts one noul question over the whole page."""
    mock_post = mocker.patch(
        "parsing.requests.post",
        return_value=_decisions_response(mocker, 0.02),
    )

    assert not BlockedPageDetector("key").is_blocked("Page.", "https://e.com")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args == (OPENROUTER_DECISIONS_URL,)
    assert kwargs["timeout"] == 30
    assert kwargs["headers"] == {
        "Authorization": "Bearer key",
        "HTTP-Referer": OPENROUTER_APP_URL,
        "X-Title": OPENROUTER_APP_TITLE,
    }
    body = kwargs["json"]
    assert body["model"] == BLOCK_DETECTOR_MODEL_ID
    assert body["state"] == "Page."
    question = body["questions"]["blocked"]
    assert question["type"] == "noul"
    assert question["instructions"]
    assert set(question["criteria"]) == {"true", "false"}


def test_is_blocked_true_at_threshold_logs_probability(mocker, caplog):
    """Test is_blocked flags a probability at the threshold and logs it."""
    mocker.patch(
        "parsing.requests.post",
        return_value=_decisions_response(mocker, 0.5),
    )
    detector = BlockedPageDetector("key")

    with caplog.at_level(logging.WARNING, logger="parsing"):
        assert detector.is_blocked("Access Denied", "https://e.com")

    assert "JEV flagged https://e.com as a block page (p=0.50)" in caplog.text


def _http_error(mocker):
    response = mocker.Mock()
    response.raise_for_status.side_effect = RuntimeError("502 Bad Gateway")
    return {"return_value": response}


def _malformed(mocker):
    response = mocker.Mock()
    response.json.return_value = {"error": "no answers"}
    return {"return_value": response}


@pytest.mark.parametrize(
    "failure",
    [
        lambda mocker: {"side_effect": RuntimeError("boom")},
        _http_error,
        _malformed,
    ],
    ids=["network", "http_error", "malformed"],
)
def test_is_blocked_fails_open(mocker, caplog, failure):
    """Test any detector failure is logged and treated as not blocked."""
    mocker.patch("parsing.requests.post", **failure(mocker))

    with caplog.at_level(logging.WARNING, logger="parsing"):
        assert not BlockedPageDetector("key").is_blocked("Page.", "https://e.com")

    assert "Block-page check failed for https://e.com" in caplog.text


def test_is_blocked_caps_state_at_max_chars(mocker):
    """Test is_blocked sends only the first 20 000 characters of the page to JEV."""
    mock_post = mocker.patch(
        "parsing.requests.post",
        return_value=_decisions_response(mocker, 0.02),
    )

    BlockedPageDetector("key").is_blocked("a" * 20000 + "tail", "https://e.com")

    assert mock_post.call_args.kwargs["json"]["state"] == "a" * 20000
