import asyncio
from types import SimpleNamespace
from typing import get_args

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ThinkingEffort

import llm as llm_module
from config import ALLOWED_THINKING_LEVELS, ModelSpec
from llm import LLMClient, OpenRouterCostReporter


@pytest.fixture
def llm_client(mocker):
    """LLMClient wired to mock providers; unused by most of these tests."""
    return LLMClient(mocker.MagicMock(), mocker.MagicMock())


def test_build_model_returns_google_model(llm_client):
    """Test build_model wires a registered Gemini id to a GoogleModel."""
    model = llm_client.build_model("gemini-3.7-flash")
    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-3.7-flash"
    assert model.system == "google"


def test_build_model_returns_openrouter_model(mocker):
    """Test build_model wires a registered OpenRouter id to an OpenRouterModel."""
    provider = OpenRouterProvider(api_key="mock_openrouter_key")
    client = LLMClient(mocker.MagicMock(), provider)

    model = client.build_model("openai/gpt-5.6-luna")

    assert isinstance(model, OpenRouterCostReporter)
    assert isinstance(model.wrapped, OpenRouterModel)
    assert model.model_name == "openai/gpt-5.6-luna"
    assert model.system == "openrouter"


def test_build_model_asks_openrouter_for_usage_accounting(mocker):
    """Test the OpenRouter model requests the usage that carries the cost."""
    client = LLMClient(mocker.MagicMock(), OpenRouterProvider(api_key="mock_key"))

    model = client.build_model("minimax/minimax-m3")

    assert model.settings == {"openrouter_usage": {"include": True}}


def test_build_model_leaves_gemini_unwrapped(llm_client):
    """Test Langfuse prices Gemini itself, so it needs no cost reporter."""
    model = llm_client.build_model("gemini-3.7-flash")

    assert not isinstance(model, OpenRouterCostReporter)
    assert model.settings is None


def _report_cost_for(response, mocker):
    """Drive one request through the reporter, returning the span it wrote to."""
    span = mocker.MagicMock()
    mocker.patch.object(llm_module, "get_current_span", return_value=span)
    model = OpenRouterCostReporter(FunctionModel(lambda messages, info: response))

    asyncio.run(
        model.request(
            [ModelRequest(parts=[UserPromptPart(content="hello")])],
            None,
            ModelRequestParameters(),
        ),
    )
    return span


def test_cost_reporter_publishes_the_cost_openrouter_charged(mocker):
    """Test the reported cost reaches the span under the name Langfuse reads.

    The literal attribute is the contract with Langfuse: pydantic-ai's own
    estimate is already on the span as operation.cost and goes uningested.
    """
    span = _report_cost_for(
        ModelResponse(
            parts=[TextPart(content="A summary.")],
            provider_details={"cost": 0.0123},
        ),
        mocker,
    )

    span.set_attribute.assert_called_once_with("gen_ai.usage.cost", 0.0123)


@pytest.mark.parametrize(
    "provider_details",
    [None, {"downstream_provider": "novita"}],
)
def test_cost_reporter_publishes_nothing_without_a_reported_cost(
    mocker,
    provider_details,
):
    """Test a response without a cost leaves the span alone rather than zeroing it."""
    span = _report_cost_for(
        ModelResponse(
            parts=[TextPart(content="A summary.")],
            provider_details=provider_details,
        ),
        mocker,
    )

    span.set_attribute.assert_not_called()


def test_cost_reporter_writes_to_the_live_generation_span():
    """Test the cost survives a real run, on the span the exporter ships.

    The tests above stub the span away, so they would keep passing if the
    wrapper landed outside the instrumented model (leaving `get_current_span`
    to return the non-recording invalid span), if a pydantic-ai bump had
    `finish` overwrite the attribute alongside the token counts it already
    writes there, or if `run_sync` started streaming — the wrapper overrides
    only `request`. Each of those silently returns OpenRouter generations to
    tokens with no cost, which is what this whole path exists to prevent.

    The provider is passed to `instrument`, not installed globally: importing
    `config` lets Sentry claim the global one first, and OTel refuses to
    override it.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    agent = Agent()
    agent.instrument = InstrumentationSettings(tracer_provider=provider)
    model = OpenRouterCostReporter(
        FunctionModel(
            lambda messages, info: ModelResponse(
                parts=[TextPart(content="A summary.")],
                provider_details={"cost": 0.0123},
            ),
        ),
    )

    agent.run_sync("Summarize this.", model=model)

    generation = next(
        (
            span
            for span in exporter.get_finished_spans()
            if span.name.startswith("chat ")
        ),
        None,
    )
    assert generation is not None, "the run exported no generation span"
    assert generation.attributes["gen_ai.usage.cost"] == 0.0123
    assert "gen_ai.usage.output_tokens" in generation.attributes


def test_build_model_caches_across_providers(mocker):
    """Test the cache is keyed by id alone, so both providers share one dict.

    Also the whole of the caching contract: one object per id, and distinct
    ids never collide. There is a single Gemini id left in the registry, so a
    same-provider version of the second half has nothing to compare against.
    """
    client = LLMClient(mocker.MagicMock(), OpenRouterProvider(api_key="mock_key"))

    google = client.build_model("gemini-3.7-flash")
    openrouter = client.build_model("minimax/minimax-m3")

    assert client.build_model("gemini-3.7-flash") is google
    assert client.build_model("minimax/minimax-m3") is openrouter
    assert google is not openrouter


def test_build_model_rejects_unregistered_model(llm_client):
    """Test an id missing from MODEL_SPECS fails loudly rather than guessing."""
    with pytest.raises(KeyError):
        llm_client.build_model("no-such-model")


def test_build_model_rejects_provider_without_builder(llm_client, mocker):
    """Test a registered provider with no builder raises instead of defaulting."""
    mocker.patch.dict(
        llm_module.MODEL_SPECS,
        {
            "mystery-1": ModelSpec(
                label="Mystery 1",
                provider="mystery",
                supports_audio=True,
                supports_files=True,
            ),
        },
    )

    with pytest.raises(ValueError, match="No model builder for provider: mystery"):
        llm_client.build_model("mystery-1")


@pytest.mark.parametrize("thinking_level", ALLOWED_THINKING_LEVELS)
def test_build_settings_passes_every_allowed_level_as_agnostic_effort(
    llm_client,
    thinking_level,
):
    """Test every allowed level becomes a valid pydantic-ai ThinkingEffort.

    There is no per-provider branch to test: build_settings owns no mapping, so
    the only thing it can get wrong is emitting a level pydantic-ai does not
    know, which each provider's model looks up in a dict on the way out.
    """
    settings = llm_client.build_settings(thinking_level=thinking_level)

    assert settings == {"thinking": thinking_level}
    assert settings["thinking"] in get_args(ThinkingEffort)


def test_build_settings_does_not_reject_unknown_thinking_level(llm_client):
    """Test a level outside the allow-list survives build_settings itself.

    It no longer survives the request: see the KeyError test below. This pins
    where the failure is *not*, so the two together locate it exactly.
    """
    assert llm_client.build_settings(thinking_level="INVALID") == {
        "thinking": "INVALID",
    }


def test_unknown_thinking_level_raises_when_the_request_is_built(llm_client):
    """Lock where a stale `users.thinking_level` now fails, and how loudly.

    Passing the level through `google_thinking_config` used to leave the ruling
    to the provider. The agnostic effort is looked up in a dict instead, so an
    unrecognized level raises KeyError while the request is assembled — inside
    agent.run_sync, but *not* caught by summary.py's typed @retry decorators, so
    it surfaces to Sentry on the first attempt rather than being retried.
    """
    model = llm_client.build_model("gemini-3.7-flash")
    settings = llm_client.build_settings(thinking_level="INVALID")
    messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
    settings, params = model.prepare_request(settings, ModelRequestParameters())

    with pytest.raises(KeyError, match="INVALID"):
        asyncio.run(
            model._build_content_and_config(messages, settings or {}, params),
        )


def test_build_uploaded_file_uses_uri_as_file_id(llm_client):
    """Test the uploaded-file part carries the uri, not the file name."""
    file = SimpleNamespace(
        name="files/mock123",
        uri="https://generativelanguage.googleapis.com/v1beta/files/mock123",
        mime_type="audio/ogg",
    )

    part = llm_client.build_uploaded_file(model_id="gemini-3.7-flash", file=file)

    assert part.file_id == file.uri
    assert part.media_type == "audio/ogg"
    assert part.provider_name == "google"


def test_build_uploaded_file_rejects_non_google_model(llm_client, mocker):
    """Test a Gemini-stored file is never handed to another provider's model.

    upload_and_wait_for_file always uploads to Gemini, so a non-Google model
    would receive a file id it cannot resolve.
    """
    mocker.patch.dict(
        llm_module.MODEL_SPECS,
        {
            "mystery-1": ModelSpec(
                label="Mystery 1",
                provider="mystery",
                supports_audio=True,
                supports_files=True,
            ),
        },
    )
    file = SimpleNamespace(name="files/x", uri="https://x", mime_type="audio/ogg")

    with pytest.raises(ValueError, match="Cannot reference a Gemini file"):
        llm_client.build_uploaded_file(model_id="mystery-1", file=file)


def test_build_uploaded_file_rejects_registered_openrouter_model(mocker):
    """Test the guard holds for a real registry row, not just a fabricated spec.

    OpenRouter has no file API, so `summarize_with_document` is expected to
    substitute a Gemini model before reaching here; this is the backstop if it
    ever stops doing so.
    """
    client = LLMClient(mocker.MagicMock(), OpenRouterProvider(api_key="mock_key"))
    file = SimpleNamespace(name="files/x", uri="https://x", mime_type="application/pdf")

    with pytest.raises(ValueError, match="Cannot reference a Gemini file"):
        client.build_uploaded_file(model_id="openai/gpt-5.6-luna", file=file)


def test_run_drives_a_real_agent_run(llm_client, mocker):
    """Test run against the real Agent, with only the model itself substituted.

    The other run tests stub `_agent.run_sync`, so they would keep passing if a
    keyword were renamed or pydantic-ai changed the signature. This one goes
    through the real call and asserts on what the model actually received.
    """
    seen = {}

    def capture(messages, info):
        seen["instructions"] = messages[0].instructions
        seen["prompt"] = messages[0].parts[-1].content
        # Not info.model_settings: prepare_request lifts `thinking` out of the
        # settings into the request parameters, leaving the settings empty.
        seen["thinking"] = info.model_request_parameters.thinking
        return ModelResponse(parts=[TextPart(content="A summary.")])

    mocker.patch.object(
        llm_client,
        "build_model",
        # supports_thinking, or pydantic-ai drops the level before the model
        # sees it — FunctionModel's default profile does not claim it.
        return_value=FunctionModel(
            capture,
            profile=ModelProfile(supports_thinking=True),
        ),
    )

    result = llm_client.run(
        content="Summarize this.",
        model_id="gemini-3.7-flash",
        target_language="Ukrainian",
        thinking_level="medium",
    )

    assert result == "A summary."
    assert seen["prompt"] == "Summarize this."
    assert "Ukrainian" in seen["instructions"]
    assert seen["thinking"] == "medium"


@pytest.mark.parametrize(
    ("thinking_level", "expected_level"),
    [("high", "HIGH"), ("minimal", "MINIMAL"), ("xhigh", "HIGH")],
)
def test_run_builds_the_expected_gemini_request_config(
    llm_client,
    thinking_level,
    expected_level,
):
    """Test pydantic-ai, not this codebase, translates the level for Gemini.

    Gemini has no XHIGH, so xhigh collapses onto HIGH here — the reason the
    fifth level is offered for a future provider rather than for today.

    include_thoughts arrives True and cannot be turned off on this path: it is
    hard-coded beside the level in pydantic-ai's Google translation. Gemini
    therefore generates thought summaries that run() drops, which is the price
    of owning no mapping. If a bump ever separates the two, this test says so.
    """
    model = llm_client.build_model("gemini-3.7-flash")
    settings = llm_client.build_settings(thinking_level=thinking_level)
    messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
    settings, params = model.prepare_request(settings, ModelRequestParameters())

    # Reaches into a GoogleModel private: it is the only way to see the real
    # GenerateContentConfig without a live call. Re-verify on a pydantic-ai bump.
    _, config = asyncio.run(
        model._build_content_and_config(messages, settings or {}, params),
    )

    assert config["thinking_config"] == {
        "include_thoughts": True,
        "thinking_level": expected_level,
    }
    assert config["tools"] is None
    assert config["response_json_schema"] is None


def test_run_passes_model_and_instructions(llm_client, mocker):
    """Test run resolves the model and the language instruction per call."""
    mock_run_sync = mocker.patch.object(
        llm_client._agent,
        "run_sync",
        return_value=SimpleNamespace(output="A summary."),
    )

    result = llm_client.run(
        content="Summarize this.",
        model_id="gemini-3.7-flash",
        target_language="Ukrainian",
        thinking_level="medium",
    )

    assert result == "A summary."
    call = mock_run_sync.call_args
    assert call.args[0] == "Summarize this."
    assert call.kwargs["model"].model_name == "gemini-3.7-flash"
    assert "Ukrainian" in call.kwargs["instructions"]


def test_run_instructions_are_dedented(llm_client, mocker):
    """Test the system instruction is dedented and stripped before being sent."""
    mock_run_sync = mocker.patch.object(
        llm_client._agent,
        "run_sync",
        return_value=SimpleNamespace(output="A summary."),
    )

    llm_client.run(
        content="Summarize this.",
        model_id="gemini-3.7-flash",
        target_language="English",
        thinking_level="high",
    )

    instructions = mock_run_sync.call_args.kwargs["instructions"]
    assert not instructions.startswith((" ", "\n"))
    assert "\n    " not in instructions


@pytest.mark.parametrize("output", ["", None])
def test_run_raises_on_empty_output(llm_client, mocker, output):
    """Test an empty response raises AttributeError, which the retries catch."""
    mocker.patch.object(
        llm_client._agent,
        "run_sync",
        return_value=SimpleNamespace(output=output),
    )

    with pytest.raises(AttributeError):
        llm_client.run(
            content="Summarize this.",
            model_id="gemini-3.7-flash",
            target_language="English",
            thinking_level="high",
        )


def test_run_uses_traced_agent_for_text_content(llm_client, mocker):
    """Test a plain-text run goes through the traced agent, not the untraced one."""
    mock_run_sync = mocker.patch.object(
        llm_client._agent,
        "run_sync",
        return_value=SimpleNamespace(output="A summary."),
    )
    mock_untraced_run_sync = mocker.patch.object(
        llm_client._untraced_agent,
        "run_sync",
    )

    result = llm_client.run(
        content="Summarize this.",
        model_id="gemini-3.7-flash",
        target_language="English",
        thinking_level="high",
    )

    assert result == "A summary."
    # Unset, so the agent inherits the instrument_all() default. Pinned here
    # because switching it off would silently stop every trace.
    assert llm_client._agent.instrument is None
    mock_run_sync.assert_called_once()
    mock_untraced_run_sync.assert_not_called()


def test_run_uses_traced_agent_for_multipart_text_content(llm_client, mocker):
    """Test an all-text multi-part prompt is traced, not just a bare string."""
    mock_run_sync = mocker.patch.object(
        llm_client._agent,
        "run_sync",
        return_value=SimpleNamespace(output="A summary."),
    )
    mock_untraced_run_sync = mocker.patch.object(
        llm_client._untraced_agent,
        "run_sync",
    )

    result = llm_client.run(
        content=["Summarize this.", "Use short bullets."],
        model_id="gemini-3.7-flash",
        target_language="English",
        thinking_level="high",
    )

    assert result == "A summary."
    mock_run_sync.assert_called_once()
    mock_untraced_run_sync.assert_not_called()


def test_run_uses_untraced_agent_for_uploaded_file_content(llm_client, mocker):
    """Test a run carrying an UploadedFile skips Langfuse via the untraced agent.

    pydantic-ai would otherwise serialize the file pointer, not the bytes behind
    it, giving Langfuse a generation with token usage but no real content.
    """
    file = SimpleNamespace(
        name="files/mock123",
        uri="https://generativelanguage.googleapis.com/v1beta/files/mock123",
        mime_type="audio/ogg",
    )
    uploaded_file = llm_client.build_uploaded_file(
        model_id="gemini-3.7-flash",
        file=file,
    )
    mock_run_sync = mocker.patch.object(
        llm_client._agent,
        "run_sync",
    )
    mock_untraced_run_sync = mocker.patch.object(
        llm_client._untraced_agent,
        "run_sync",
        return_value=SimpleNamespace(output="A summary."),
    )

    result = llm_client.run(
        content=["Summarize this.", uploaded_file],
        model_id="gemini-3.7-flash",
        target_language="English",
        thinking_level="high",
    )

    assert result == "A summary."
    assert llm_client._untraced_agent.instrument is False
    mock_untraced_run_sync.assert_called_once()
    mock_run_sync.assert_not_called()
