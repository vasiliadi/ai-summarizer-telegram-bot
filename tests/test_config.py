import importlib

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
    """
    monkeypatch.setenv("ENV", "PROD")
    mock_load_dotenv = mocker.patch("dotenv.load_dotenv")
    importlib.reload(config)
    mock_load_dotenv.assert_not_called()


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
