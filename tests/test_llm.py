import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.google import GoogleModel

import llm as llm_module
from config import ModelSpec
from llm import LLMClient


@pytest.fixture
def llm_client(mocker):
    """LLMClient wired to a mock Gemini client; unused by most of these tests."""
    return LLMClient(mocker.MagicMock())


def test_build_model_returns_google_model(llm_client):
    """Test build_model wires a registered Gemini id to a GoogleModel."""
    model = llm_client.build_model("gemini-3.5-flash-lite")
    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-3.5-flash-lite"
    assert model.system == "google"


def test_build_model_is_cached_per_id(llm_client):
    """Test build_model reuses one model object per id, so clients are shared."""
    assert llm_client.build_model("gemini-3.5-flash") is llm_client.build_model(
        "gemini-3.5-flash",
    )
    assert llm_client.build_model("gemini-3.5-flash") is not llm_client.build_model(
        "gemini-3.6-flash",
    )


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
            ),
        },
    )

    with pytest.raises(ValueError, match="No model builder for provider: mystery"):
        llm_client.build_model("mystery-1")


@pytest.mark.parametrize("thinking_level", ["MINIMAL", "LOW", "MEDIUM", "HIGH"])
def test_build_settings_passes_google_thinking_level_through(
    llm_client,
    thinking_level,
):
    """Test Google gets the level verbatim, not the agnostic effort mapping."""
    settings = llm_client.build_settings(
        "gemini-3.5-flash",
        thinking_level=thinking_level,
    )
    assert settings == {"google_thinking_config": {"thinking_level": thinking_level}}


def test_build_settings_uses_agnostic_effort_for_other_providers(llm_client, mocker):
    """Test a non-Google provider gets the portable `thinking` effort instead."""
    mocker.patch.dict(
        llm_module.MODEL_SPECS,
        {
            "mystery-1": ModelSpec(
                label="Mystery 1",
                provider="mystery",
                supports_audio=True,
            ),
        },
    )

    assert llm_client.build_settings("mystery-1", thinking_level="LOW") == {
        "thinking": "low",
    }


def test_build_settings_does_not_reject_unknown_thinking_level(llm_client):
    """Lock the lenient handling of a thinking level outside the allow-list.

    A stale `users.thinking_level` must not blow up before the request is even
    built — the provider decides what to do with an unrecognized level, exactly
    as it did when the level went through `types.ThinkingLevel`. The agnostic
    `thinking` effort would raise KeyError here.
    """
    settings = llm_client.build_settings("gemini-3.5-flash", thinking_level="INVALID")
    assert settings["google_thinking_config"] == {"thinking_level": "INVALID"}


def test_build_uploaded_file_uses_uri_as_file_id(llm_client):
    """Test the uploaded-file part carries the uri, not the file name."""
    file = SimpleNamespace(
        name="files/mock123",
        uri="https://generativelanguage.googleapis.com/v1beta/files/mock123",
        mime_type="audio/ogg",
    )

    part = llm_client.build_uploaded_file(model_id="gemini-3.5-flash", file=file)

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
            ),
        },
    )
    file = SimpleNamespace(name="files/x", uri="https://x", mime_type="audio/ogg")

    with pytest.raises(ValueError, match="Cannot reference a Gemini file"):
        llm_client.build_uploaded_file(model_id="mystery-1", file=file)


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
        seen["settings"] = info.model_settings
        return ModelResponse(parts=[TextPart(content="A summary.")])

    mocker.patch.object(
        llm_client,
        "build_model",
        return_value=FunctionModel(capture),
    )

    result = llm_client.run(
        content="Summarize this.",
        model_id="gemini-3.6-flash",
        target_language="Ukrainian",
        thinking_level="MEDIUM",
    )

    assert result == "A summary."
    assert seen["prompt"] == "Summarize this."
    assert "Ukrainian" in seen["instructions"]
    assert seen["settings"]["google_thinking_config"] == {"thinking_level": "MEDIUM"}


def test_run_builds_the_expected_gemini_request_config(llm_client):
    """Test the settings reach GenerateContentConfig in the pre-seam shape.

    include_thoughts must stay unset: pydantic-ai's agnostic thinking effort
    turns it on, which makes Gemini emit thought summaries that run() discards.
    """
    model = llm_client.build_model("gemini-3.5-flash-lite")
    settings = llm_client.build_settings("gemini-3.5-flash-lite", thinking_level="HIGH")
    messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]

    # Reaches into a GoogleModel private: it is the only way to see the real
    # GenerateContentConfig without a live call. Re-verify on a pydantic-ai bump.
    _, config = asyncio.run(
        model._build_content_and_config(
            messages,
            settings,
            ModelRequestParameters(),
        ),
    )

    assert config["thinking_config"] == {"thinking_level": "HIGH"}
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
        model_id="gemini-3.6-flash",
        target_language="Ukrainian",
        thinking_level="MEDIUM",
    )

    assert result == "A summary."
    call = mock_run_sync.call_args
    assert call.args[0] == "Summarize this."
    assert call.kwargs["model"].model_name == "gemini-3.6-flash"
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
        model_id="gemini-3.5-flash",
        target_language="English",
        thinking_level="HIGH",
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
            model_id="gemini-3.5-flash",
            target_language="English",
            thinking_level="HIGH",
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
        model_id="gemini-3.5-flash",
        target_language="English",
        thinking_level="HIGH",
    )

    assert result == "A summary."
    # Unset, so the agent inherits the instrument_all() default. Pinned here
    # because switching it off would silently stop every trace.
    assert llm_client._agent.instrument is None
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
        model_id="gemini-3.5-flash",
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
        model_id="gemini-3.5-flash",
        target_language="English",
        thinking_level="HIGH",
    )

    assert result == "A summary."
    assert llm_client._untraced_agent.instrument is False
    mock_untraced_run_sync.assert_called_once()
    mock_run_sync.assert_not_called()
