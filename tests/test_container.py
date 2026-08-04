import config
from container import Container, build_container
from download import Downloader
from llm import LLMClient
from services import GeminiHelper, Messenger, QuotaManager, Tracer


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

    assert container.messenger._bot is config.bot
    assert container.quota_manager._rate_limiter is config.rate_limiter
    assert container.quota_manager._per_minute_rate is config.per_minute_rate
    assert container.gemini_helper._client is config.gemini_client
    assert container.tracer._client is config.langfuse_client
    assert container.llm_client._client is config.gemini_client
    assert container.downloader._tg_api_token is config.TG_API_TOKEN
