import importlib
import logging

from openai.resources.chat.completions import Completions

import config


def test_proxy_env_parsing_trims_and_drops_empty(monkeypatch):
    """Test PROXY env parsing trims whitespace and drops empty entries."""
    monkeypatch.setenv("PROXY", " http://a:1 , http://b:2 ,, ")
    importlib.reload(config)
    assert config.PROXIES == ["http://a:1", "http://b:2"]


def test_proxy_env_parsing_empty_string(monkeypatch):
    """Test PROXY env parsing yields an empty list when the variable is unset."""
    monkeypatch.delenv("PROXY", raising=False)
    importlib.reload(config)
    assert config.PROXIES == []


def test_dotenv_skipped_in_prod(monkeypatch, mocker):
    """Test load_dotenv is not invoked when ENV=PROD (production).

    Every other test runs with ENV=TEST, so the dotenv-skip branch
    (ENV=PROD, as in the real container) is otherwise never exercised.
    Set the literal "PROD" rather than delenv: an absent ENV is not "PROD",
    so it would trigger the opposite branch. Patch dotenv.load_dotenv at the
    source — the name is only bound into config's namespace when the import
    inside the skipped block runs, so config.load_dotenv does not exist here.

    Reloading mutates the process-global config module, so a finally block
    restores ENV and reloads it back to the TEST baseline even if the
    assertion fails, preventing later tests from observing PROD settings.
    """
    monkeypatch.setenv("ENV", "PROD")
    mock_load_dotenv = mocker.patch("dotenv.load_dotenv")
    try:
        importlib.reload(config)
        mock_load_dotenv.assert_not_called()
    finally:
        monkeypatch.setenv("ENV", "TEST")
        importlib.reload(config)


def test_log_level_falls_back_on_non_level_attribute(monkeypatch):
    """Test NUMERIC_LOG_LEVEL falls back to ERROR for non-level logging names.

    Resolving LOG_LEVEL through logging.getLevelNamesMapping() (not a bare
    getattr on the logging module) keeps names like BASIC_FORMAT — a real but
    non-int module attribute — from reaching basicConfig, where they would
    raise ValueError at import.

    The setenv lives in a nested monkeypatch context so LOG_LEVEL is restored to
    its true original value (set or unset) before the final reload, leaving the
    config module consistent with the real environment for later tests.
    """
    with monkeypatch.context() as m:
        m.setenv("LOG_LEVEL", "BASIC_FORMAT")
        importlib.reload(config)
        assert config.NUMERIC_LOG_LEVEL == logging.ERROR
    importlib.reload(config)


def test_sentry_opts_into_log_collection(mocker):
    """Test Sentry is initialized with log auto-collection switched on.

    sentry-sdk 2.68.0 made `enable_logs` a no-op and left LoggingIntegration's
    `capture_sentry_logs` off by default, so the opt-in is the only thing
    sending this project's log records to Sentry. Dropping it breaks nothing
    loudly — the logs just stop arriving — which is what this pins.

    Asserts on the constructor call, not on the instance: the flag is stored on
    the class, so reading it back off an instance reports whichever
    LoggingIntegration was built last anywhere in the process — including the
    default one a real sentry_sdk.init() builds with the flag off.
    """
    mock_init = mocker.patch("sentry_sdk.init")
    mock_integration = mocker.patch(
        "sentry_sdk.integrations.logging.LoggingIntegration",
    )
    importlib.reload(config)
    assert mock_init.call_args.kwargs["integrations"] == [mock_integration.return_value]
    assert mock_integration.call_args.kwargs == {"capture_sentry_logs": True}


def test_langfuse_disabled_when_keys_blank(monkeypatch):
    """Test langfuse_client stays None when either Langfuse key is blank.

    Covers both-blank and each single-blank combination: partial config
    (only one of the two keys set) must stay disabled as a fail-safe.

    Uses blank values rather than delenv: reload() re-runs load_dotenv(),
    which backfills any *absent* var from the real .env file, masking this
    branch. python-dotenv never overrides a var already present (even blank).
    """
    for public, secret in [("", ""), ("", "sk-real"), ("pk-real", "")]:
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", public)
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", secret)
        importlib.reload(config)
        assert config.langfuse_client is None, (public, secret)


def test_model_registry_labels_are_unique():
    """Test no two models share a label.

    The /set_summarizing_model keyboard sends labels, and
    MODEL_LABELS_REVERSE maps the reply back to an id — a duplicate would make
    one of the two models unreachable.
    """
    assert len(config.MODEL_LABELS_REVERSE) == len(config.MODEL_SPECS)
    assert set(config.ALLOWED_MODELS_FOR_SUMMARY) == set(config.MODEL_SPECS)


def test_default_summarizing_model_accepts_files():
    """Test the default model can serve the document fallback.

    summarize_with_document substitutes DEFAULT_MODEL_ID_FOR_SUMMARY for any
    model with supports_files=False, so pointing the default at one of those
    would send the upload nowhere.
    """
    default = config.MODEL_SPECS[config.DEFAULT_MODEL_ID_FOR_SUMMARY]
    assert default.supports_files


def test_no_model_claims_audio_before_a_native_route_exists():
    """Test supports_audio stays False while spoken content is always transcribed.

    Nothing reads the flag, so a True here would promise native audio and
    silently change nothing.
    """
    assert not any(spec.supports_audio for spec in config.MODEL_SPECS.values())


def test_default_thinking_level_is_selectable():
    """Test the default survives the allow-list every writer validates against.

    register_user seeds it directly, bypassing set_thinking_level, so a default
    outside the allow-list would give every new user an unusable level.
    """
    assert config.DEFAULT_THINKING_LEVEL in config.ALLOWED_THINKING_LEVELS


def test_openrouter_client_identifies_the_app():
    """Test OpenRouter calls carry app attribution instead of landing under "Unknown"."""
    headers = config.openrouter_client.default_headers
    assert headers["HTTP-Referer"] == config.OPENROUTER_APP_URL
    assert headers["X-Title"] == config.OPENROUTER_APP_TITLE


def test_openrouter_client_uses_the_global_endpoint():
    """Test the client stays off the regional hosts, where the Files API is 403."""
    assert config.openrouter_client.base_url == "https://openrouter.ai/api/v1/"


def test_langfuse_patches_the_openai_sdk_when_enabled():
    """Test enabling Langfuse wraps chat completions, the only source of traces.

    Nothing else instruments a model call, so dropping the drop-in's import
    breaks nothing loudly — the traces just stop arriving.

    Reloads first: the blank-key test above leaves `config` with tracing off.
    """
    importlib.reload(config)
    assert config.langfuse_client is not None
    assert hasattr(Completions.create, "__wrapped__")
