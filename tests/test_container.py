import config
import database
from container import Container, build_container
from database import UserRepository
from download import Downloader
from handlers import MessageHandlers
from llm import LLMClient
from parsing import WebParser
from services import GeminiHelper, Messenger, QuotaManager, Tracer
from summary import Summarizer
from transcription import ApiBackend, AudioTranscriber, YouTubeTranscriber, YtDlpBackend


def test_build_container_returns_wired_container():
    """build_container wires each collaborator to config's actual clients.

    The container exposes only what BotApp holds; the rest of the graph is
    reached through `handlers`, so that is what the traversal below follows.
    """
    container = build_container()

    assert isinstance(container, Container)
    assert container.bot is config.bot
    assert isinstance(container.quota_manager, QuotaManager)
    assert isinstance(container.tracer, Tracer)
    assert isinstance(container.user_repo, UserRepository)
    assert isinstance(container.handlers, MessageHandlers)

    assert container.quota_manager._rate_limiter is config.rate_limiter
    assert container.quota_manager._per_minute_rate is config.per_minute_rate
    assert container.tracer._client is config.langfuse_client
    assert container.user_repo._session_factory is database.Session

    handlers = container.handlers
    assert handlers._bot is config.bot
    assert isinstance(handlers._messenger, Messenger)
    assert handlers._messenger._bot is config.bot
    assert isinstance(handlers._web_parser, WebParser)
    assert handlers._web_parser._primary._client is config.exa_client
    assert handlers._web_parser._fallback._client is config.tavily_client
    assert isinstance(handlers._downloader, Downloader)
    assert handlers._downloader._tg_api_token is config.TG_API_TOKEN

    summarizer = handlers._summarizer
    assert isinstance(summarizer, Summarizer)
    assert isinstance(summarizer._gemini_helper, GeminiHelper)
    assert summarizer._gemini_helper._client is config.gemini_client
    assert isinstance(summarizer._llm_client, LLMClient)
    assert summarizer._llm_client._client is config.gemini_client
    assert isinstance(summarizer._audio_transcriber, AudioTranscriber)
    assert summarizer._audio_transcriber._client is config.replicate_client
    assert isinstance(summarizer._yt_transcriber, YouTubeTranscriber)
    assert isinstance(summarizer._yt_transcriber._primary, ApiBackend)
    assert isinstance(summarizer._yt_transcriber._fallback, YtDlpBackend)

    # The shared collaborators must be one instance across the graph, not
    # freshly constructed duplicates, so the object graph is genuinely one.
    assert summarizer._quota_manager is container.quota_manager
    assert summarizer._downloader is handlers._downloader
    assert handlers._quota_manager is container.quota_manager
