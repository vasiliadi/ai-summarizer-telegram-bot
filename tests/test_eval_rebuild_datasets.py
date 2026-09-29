"""Regression tests for the destructive dataset wipe."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def rebuild(monkeypatch):
    """Load the script as a module without running its CLI."""
    directory = Path(__file__).resolve().parents[1] / "scripts" / "eval"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "eval_rebuild_datasets_test",
        directory / "rebuild_datasets.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pages(mocker, *pages):
    responses = []
    for page in pages:
        response = mocker.Mock()
        response.json.return_value = {"data": [{"id": i} for i in page]}
        responses.append(response)
    return responses


def test_wipe_deletes_every_page_until_empty(rebuild, mocker):
    """Pages are deleted until the listing comes back empty."""
    get = mocker.patch.object(
        rebuild.requests,
        "get",
        side_effect=_pages(mocker, ["a", "b"], ["c"], []),
    )
    delete = mocker.patch.object(rebuild.requests, "delete")
    assert rebuild.wipe("dataset") == 3
    assert get.call_count == 3
    assert delete.call_count == 3


def test_wipe_exits_when_deleted_items_are_listed_again(rebuild, mocker):
    """A deleted item listed again stops the wipe instead of looping forever."""
    mocker.patch.object(
        rebuild.requests,
        "get",
        side_effect=_pages(mocker, ["a", "b"], ["b", "c"]),
    )
    delete = mocker.patch.object(rebuild.requests, "delete")
    with pytest.raises(SystemExit, match="still listed"):
        rebuild.wipe("dataset")
    assert delete.call_count == 2
