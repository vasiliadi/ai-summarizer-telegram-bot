import config
from container import build_container
from transcription import ApiBackend, YtDlpBackend


def test_build_container_wires_one_shared_graph():
    """build_container shares each collaborator and keeps the primary→fallback order.

    Only what the type checker cannot see: which instance is shared, and which
    of two same-typed backends comes first.
    """
    container = build_container()
    handlers = container.handlers
    summarizer = handlers._summarizer

    assert handlers._bot is container.bot
    assert handlers._quota_manager is container.quota_manager
    assert summarizer._quota_manager is container.quota_manager
    assert summarizer._downloader is handlers._downloader

    assert handlers._web_parser._primary._client is config.exa_client
    assert handlers._web_parser._fallback._client is config.tavily_client
    assert isinstance(summarizer._yt_transcriber._primary, ApiBackend)
    assert isinstance(summarizer._yt_transcriber._fallback, YtDlpBackend)
