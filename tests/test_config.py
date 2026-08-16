import importlib
import logging
from typing import get_args

from pydantic_ai.settings import ThinkingEffort
from sentry_sdk.integrations.logging import LoggingIntegration

import config
import utils


def test_get_proxy_returns_empty_when_no_proxies(mocker):
    """Test get_proxy returns an empty string when no proxies are configured."""
    mocker.patch.object(utils, "PROXIES", [])
    assert utils.get_proxy() == ""


def test_get_proxy_returns_single_value(mocker):
    """Test get_proxy always returns the sole configured proxy."""
    mocker.patch.object(utils, "PROXIES", ["http://only:1"])
    for _ in range(5):
        assert utils.get_proxy() == "http://only:1"


def test_get_proxy_picks_from_list(mocker):
    """Test get_proxy selects a proxy from the configured pool at random."""
    pool = ["http://a:1", "http://b:2", "http://c:3"]
    mocker.patch.object(utils, "PROXIES", pool)
    mocker.patch("utils.random.choice", side_effect=pool)
    assert utils.get_proxy() == "http://a:1"
    assert utils.get_proxy() == "http://b:2"
    assert utils.get_proxy() == "http://c:3"


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
    """
    mock_init = mocker.patch("sentry_sdk.init")
    importlib.reload(config)
    integrations = mock_init.call_args.kwargs["integrations"]
    assert [type(i) for i in integrations] == [LoggingIntegration]
    assert integrations[0].capture_sentry_logs is True


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


def test_no_model_takes_audio_without_taking_files():
    """Test supports_audio implies supports_files across the whole registry.

    Native audio is delivered by the same Gemini upload as documents, but only
    summarize_with_document falls back when a model cannot take a file —
    summarize() checks supports_audio alone. A spec with audio but not files
    would upload, then raise from build_uploaded_file: unretried, unmapped, and
    already paid for. The ModelSpec docstring warns against flipping the flags
    to match a provider catalog; this is what makes that warning fail loudly.
    """
    broken = [
        model_id
        for model_id, spec in config.MODEL_SPECS.items()
        if spec.supports_audio and not spec.supports_files
    ]
    assert not broken


def test_thinking_levels_are_pydantic_ais_vocabulary():
    """Test the allow-list is exactly pydantic-ai's ThinkingEffort.

    Nothing in this codebase translates a thinking level — each provider's model
    does. That only holds while the offered levels are the ones pydantic-ai
    knows: a level it does not recognize raises KeyError as the request is
    built. Set equality, so a pydantic-ai bump that adds or drops an effort
    fails here rather than silently leaving the keyboard out of date.
    """
    assert set(config.ALLOWED_THINKING_LEVELS) == set(get_args(ThinkingEffort))


def test_default_thinking_level_is_selectable():
    """Test the default survives the allow-list every writer validates against.

    register_user seeds it directly, bypassing set_thinking_level, so a default
    outside the allow-list would give every new user an unusable level.
    """
    assert config.DEFAULT_THINKING_LEVEL in config.ALLOWED_THINKING_LEVELS
