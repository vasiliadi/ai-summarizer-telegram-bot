import config
from container import Container, build_container
from download import Downloader
from handlers import MessageHandlers
from llm import LLMClient
from parsing import WebParser
from services import GeminiHelper, Messenger, QuotaManager, Tracer
from summary import Summarizer
from transcription import ApiBackend, AudioTranscriber, YouTubeTranscriber, YtDlpBackend


def test_build_container_returns_wired_container():
    """build_container wires each collaborator to config's actual clients."""
    container = build_container()

    assert isinstance(container, Container)
    assert isinstance(container.messenger, Messenger)
    assert isinstance(container.quota_manager, QuotaManager)
    assert isinstance(container.gemini_helper, GeminiHelper)
    assert isinstance(container.tracer, Tracer)
    assert isinstance(container.llm_client, LLMClient)
    assert isinstance(container.downloader, Downloader)
    assert isinstance(container.web_parser, WebParser)
    assert isinstance(container.audio_transcriber, AudioTranscriber)
    assert isinstance(container.yt_transcriber, YouTubeTranscriber)
    assert isinstance(container.summarizer, Summarizer)
    assert isinstance(container.handlers, MessageHandlers)

    assert container.messenger._bot is config.bot
    assert container.quota_manager._rate_limiter is config.rate_limiter
    assert container.quota_manager._per_minute_rate is config.per_minute_rate
    assert container.gemini_helper._client is config.gemini_client
    assert container.tracer._client is config.langfuse_client
    assert container.llm_client._client is config.gemini_client
    assert container.downloader._tg_api_token is config.TG_API_TOKEN
    assert container.web_parser._primary._client is config.exa_client
    assert container.web_parser._fallback._client is config.tavily_client
    assert container.audio_transcriber._client is config.replicate_client
    assert isinstance(container.yt_transcriber._primary, ApiBackend)
    assert isinstance(container.yt_transcriber._fallback, YtDlpBackend)

    # The summarizer's collaborators must be the container's own instances,
    # not freshly constructed duplicates, so the object graph is genuinely one.
    assert container.summarizer._quota_manager is container.quota_manager
    assert container.summarizer._gemini_helper is container.gemini_helper
    assert container.summarizer._llm_client is container.llm_client
    assert container.summarizer._downloader is container.downloader
    assert container.summarizer._audio_transcriber is container.audio_transcriber
    assert container.summarizer._yt_transcriber is container.yt_transcriber

    # The handlers' collaborators must be the container's own instances too.
    assert container.handlers._bot is config.bot
    assert container.handlers._messenger is container.messenger
    assert container.handlers._summarizer is container.summarizer
    assert container.handlers._web_parser is container.web_parser
    assert container.handlers._quota_manager is container.quota_manager
    assert container.handlers._downloader is container.downloader
