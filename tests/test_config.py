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
    seen = {utils.get_proxy() for _ in range(50)}
    assert seen
    assert seen.issubset(set(pool))


def test_proxy_env_parsing_trims_and_drops_empty():
    raw = " http://a:1 , http://b:2 ,, "
    parsed = [p.strip() for p in raw.split(",") if p.strip()]
    assert parsed == ["http://a:1", "http://b:2"]


def test_proxy_env_parsing_empty_string():
    raw = ""
    parsed = [p.strip() for p in raw.split(",") if p.strip()]
    assert parsed == []
