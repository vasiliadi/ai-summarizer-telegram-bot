import importlib

import config
import utils


def test_get_proxy_returns_empty_when_no_proxies(mocker):
    mocker.patch.object(utils, "PROXIES", [])
    assert utils.get_proxy() == ""


def test_get_proxy_returns_single_value(mocker):
    mocker.patch.object(utils, "PROXIES", ["http://only:1"])
    for _ in range(5):
        assert utils.get_proxy() == "http://only:1"


def test_get_proxy_picks_from_list(mocker):
    pool = ["http://a:1", "http://b:2", "http://c:3"]
    mocker.patch.object(utils, "PROXIES", pool)
    mocker.patch("utils.random.choice", side_effect=pool)
    assert utils.get_proxy() == "http://a:1"
    assert utils.get_proxy() == "http://b:2"
    assert utils.get_proxy() == "http://c:3"


def test_proxy_env_parsing_trims_and_drops_empty(monkeypatch):
    monkeypatch.setenv("PROXY", " http://a:1 , http://b:2 ,, ")
    importlib.reload(config)
    assert config.PROXIES == ["http://a:1", "http://b:2"]


def test_proxy_env_parsing_empty_string(monkeypatch):
    monkeypatch.delenv("PROXY", raising=False)
    importlib.reload(config)
    assert config.PROXIES == []
