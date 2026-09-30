"""Tests for the Langfuse REST reader the reports are built on.

Every rule pinned here fails silently when broken — a wrong score field reads
as a judge that never ran, a missed page as a model that scored nothing.
"""

import pytest

from helpers import load_eval_script


@pytest.fixture
def api_module(monkeypatch):
    """The module, loaded fresh."""
    return load_eval_script(monkeypatch, "langfuse_api")


@pytest.fixture
def api(api_module):
    """A client against a fake host, with a trailing slash to strip."""
    return api_module.LangfuseAPI("https://langfuse.test/", ("pk", "sk"))


def _response(mocker, status, body=None, text=""):
    response = mocker.Mock(status_code=status, text=text)
    if isinstance(body, Exception):
        response.json.side_effect = body
    else:
        response.json.return_value = body
    return response


@pytest.mark.parametrize(
    ("row", "value"),
    [
        ({"dataType": "CATEGORICAL", "value": "A"}, "A"),  # what the live API sends
        ({"dataType": "CATEGORICAL", "value": 0, "stringValue": "A"}, "A"),  # the spec
        ({"dataType": "BOOLEAN", "value": True}, True),
        ({"dataType": "NUMERIC", "value": 0.4, "stringValue": "ignored"}, 0.4),
        ({}, None),
    ],
)
def test_score_value_reads_either_shape(api_module, row, value):
    """Categorical labels are found in either field; other types use `value`."""
    assert api_module.score_value(row) == value


def test_get_returns_the_body_on_200(api, api_module, mocker):
    """A success returns the JSON body from the public API path."""
    get = mocker.patch.object(
        api_module.requests,
        "get",
        return_value=_response(mocker, 200, {"ok": 1}),
    )
    assert api.get("/v2/datasets/x", {"a": 1}) == {"ok": 1}
    assert get.call_args.args == ("https://langfuse.test/api/public/v2/datasets/x",)
    assert get.call_args.kwargs["auth"] == ("pk", "sk")
    assert get.call_args.kwargs["params"] == {"a": 1}


def test_get_waits_as_long_as_a_429_says(api, api_module, mocker):
    """`retryAfterSeconds` is obeyed, with a fallback when it is unreadable."""
    sleep = mocker.patch.object(api_module.time, "sleep")
    mocker.patch.object(
        api_module.requests,
        "get",
        side_effect=[
            _response(mocker, 429, {"details": {"retryAfterSeconds": 12}}),
            _response(mocker, 503, ValueError("not json")),
            _response(mocker, 200, {"ok": 1}),
        ],
    )
    assert api.get("x") == {"ok": 1}
    assert [c.args[0] for c in sleep.call_args_list] == [13.0, 6.0]


def test_get_fails_loudly_on_a_client_error(api, api_module, mocker):
    """An unchecked error would fall through as an empty result."""
    sleep = mocker.patch.object(api_module.time, "sleep")
    mocker.patch.object(
        api_module.requests,
        "get",
        return_value=_response(mocker, 404, text="not found"),
    )
    with pytest.raises(RuntimeError, match="HTTP 404: not found"):
        api.get("x")
    sleep.assert_not_called()


def test_get_gives_up_after_its_attempts(api, api_module, mocker):
    """A persistent server error raises after the last attempt."""
    mocker.patch.object(api_module.time, "sleep")
    get = mocker.patch.object(
        api_module.requests,
        "get",
        return_value=_response(mocker, 503, {}),
    )
    with pytest.raises(RuntimeError, match="HTTP 503"):
        api.get("x", attempts=3)
    assert get.call_count == 3


def test_paginate_follows_meta_cursor(api, mocker):
    """`meta.cursor`, not `meta.nextCursor`: the wrong one stops at page one."""
    get = mocker.patch.object(
        api,
        "get",
        side_effect=[
            {"data": [1, 2], "meta": {"cursor": "c1", "nextCursor": "wrong"}},
            {"data": [3], "meta": {"cursor": "c2"}},
            {"data": [], "meta": {"cursor": "c3"}},
        ],
    )
    assert api.paginate("rows", {"limit": 2}) == [1, 2, 3]
    assert [c.args[1] for c in get.call_args_list] == [
        {"limit": 2},
        {"limit": 2, "cursor": "c1"},
        {"limit": 2, "cursor": "c2"},
    ]


def test_paginate_stops_without_a_cursor(api, mocker):
    """A page without a cursor is the last one."""
    mocker.patch.object(api, "get", return_value={"data": [1]})
    assert api.paginate("rows", {}) == [1]


def test_dataset_id_quotes_the_name(api, mocker):
    """A dataset name is one path segment, slashes included."""
    get = mocker.patch.object(api, "get", return_value={"id": "ds-1"})
    assert api.dataset_id("a/b c") == "ds-1"
    assert get.call_args.args == ("v2/datasets/a%2Fb%20c",)


def test_experiments_filters_by_prefix_newest_first(api, api_module, mocker):
    """Only prefixed runs are kept, newest first."""
    paginate = mocker.patch.object(
        api,
        "paginate",
        return_value=[
            {"name": "stage2 / old", "startTime": "2026-01-01"},
            {"name": "other run", "startTime": "2026-03-01"},
            {"name": None, "startTime": "2026-04-01"},
            {"name": "stage2 / new", "startTime": "2026-02-01"},
        ],
    )
    rows = api.experiments("ds-1", name_prefix="stage2 / ")
    assert [r["name"] for r in rows] == ["stage2 / new", "stage2 / old"]
    assert paginate.call_args.args[1]["datasetId"] == "ds-1"
    assert paginate.call_args.args[1]["fromStartTime"] == api_module.EPOCH


def test_experiment_items_requests_the_field_groups(api, mocker):
    """The requested field groups are passed through."""
    paginate = mocker.patch.object(api, "paginate", return_value=[])
    api.experiment_items("exp-1", "io,scores")
    params = paginate.call_args.args[1]
    assert paginate.call_args.args[0] == "experiment-items"
    assert params["experimentId"] == "exp-1"
    assert params["fields"] == "io,scores"
