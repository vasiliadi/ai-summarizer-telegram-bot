from types import SimpleNamespace

import pytest
from pydantic_ai.models.google import GoogleModel

import llm as llm_module
from config import ModelSpec
from llm import build_model, build_settings, build_uploaded_file, run_model


@pytest.fixture(autouse=True)
def _clear_model_cache():
    """Keep the module-level model cache from leaking between tests."""
    llm_module._build_model.cache_clear()
    yield
    llm_module._build_model.cache_clear()


def test_build_model_returns_google_model():
    """Test build_model wires a registered Gemini id to a GoogleModel."""
    model = build_model("gemini-3.5-flash-lite")
    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-3.5-flash-lite"
    assert model.system == "google"


def test_build_model_is_cached_per_id():
    """Test build_model reuses one model object per id, so clients are shared."""
    assert build_model("gemini-3.5-flash") is build_model("gemini-3.5-flash")
    assert build_model("gemini-3.5-flash") is not build_model("gemini-3.6-flash")


def test_build_model_rejects_unregistered_model():
    """Test an id missing from MODEL_SPECS fails loudly rather than guessing."""
    with pytest.raises(KeyError):
        build_model("no-such-model")


def test_build_model_rejects_provider_without_builder(mocker):
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
        build_model("mystery-1")


@pytest.mark.parametrize(
    ("thinking_level", "expected"),
    [("MINIMAL", "minimal"), ("LOW", "low"), ("MEDIUM", "medium"), ("HIGH", "high")],
)
def test_build_settings_maps_thinking_level(thinking_level, expected):
    """Test every allowed thinking level maps to its provider-agnostic effort."""
    assert build_settings(thinking_level=thinking_level)["thinking"] == expected


def test_build_settings_carries_nothing_but_thinking():
    """Test no provider-specific option leaks into the settings.

    Safety settings used to live here; the request must now carry the model's
    defaults, so a stray google_* key would be a real behavior change.
    """
    assert build_settings(thinking_level="HIGH") == {"thinking": "high"}


def test_build_uploaded_file_uses_uri_as_file_id():
    """Test the uploaded-file part carries the uri, not the file name."""
    file = SimpleNamespace(
        name="files/mock123",
        uri="https://generativelanguage.googleapis.com/v1beta/files/mock123",
        mime_type="audio/ogg",
    )

    part = build_uploaded_file(model_id="gemini-3.5-flash", file=file)

    assert part.file_id == file.uri
    assert part.media_type == "audio/ogg"
    assert part.provider_name == "google"


def test_run_passes_model_instructions_and_settings(mocker):
    """Test run resolves the model, language instruction, and settings per call."""
    mock_run_sync = mocker.patch.object(
        llm_module._agent,
        "run_sync",
        return_value=SimpleNamespace(output="A summary."),
    )

    result = run_model(
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
    assert call.kwargs["model_settings"]["thinking"] == "medium"


def test_run_instructions_are_dedented(mocker):
    """Test the system instruction is dedented and stripped before being sent."""
    mock_run_sync = mocker.patch.object(
        llm_module._agent,
        "run_sync",
        return_value=SimpleNamespace(output="A summary."),
    )

    run_model(
        content="Summarize this.",
        model_id="gemini-3.5-flash",
        target_language="English",
        thinking_level="HIGH",
    )

    instructions = mock_run_sync.call_args.kwargs["instructions"]
    assert not instructions.startswith((" ", "\n"))
    assert "\n    " not in instructions


@pytest.mark.parametrize("output", ["", None])
def test_run_raises_on_empty_output(mocker, output):
    """Test an empty response raises AttributeError, which the retries catch."""
    mocker.patch.object(
        llm_module._agent,
        "run_sync",
        return_value=SimpleNamespace(output=output),
    )

    with pytest.raises(AttributeError):
        run_model(
            content="Summarize this.",
            model_id="gemini-3.5-flash",
            target_language="English",
            thinking_level="HIGH",
        )
