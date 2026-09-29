"""Regression tests for evaluation reporting and paid backfill selection."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def stage2(monkeypatch):
    """Load the CLI with a judge stub so tests cannot initialize model clients."""
    directory = Path(__file__).resolve().parents[1] / "scripts" / "eval"
    monkeypatch.syspath_prepend(str(directory))
    monkeypatch.setitem(
        sys.modules,
        "judge",
        SimpleNamespace(
            COMPARE_DATASET="test-dataset",
            RUN_PREFIX="stage2 / ",
            JEV_FLAG_BELOW=0.6,
            PROMPT_KEY="key_points_for_transcript",
            _text=str,
            generation_failed=lambda output: not output,
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "eval_stage2_test",
        directory / "stage2.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("scored", [0, 1, 49])
def test_report_marks_missing_tier1_scores_incomplete(stage2, capsys, scored):
    """Missing scores cannot produce a passing percentage or best-value marks."""
    rows = {str(i): ({"t1_pass": 1} if i < scored else {}, 1, False) for i in range(50)}
    summary = stage2._summary(rows, (1, 50))
    assert summary["t1_pass"] is None
    assert summary["incomplete"]
    stage2._table({"vendor/model / key_points_for_transcript": summary})
    output = capsys.readouterr().out
    assert "INCOMPLETE" in output
    assert f"Tier 1 scored {scored} of 50 items" in output
    assert "**" not in output


def test_report_marks_empty_run_incomplete(stage2):
    """A run with no returned items is not a qualified candidate."""
    summary = stage2._summary({}, None)
    assert summary["incomplete"]
    assert summary["t1_pass"] is None


@pytest.mark.parametrize(("failures", "dropped"), [(0, False), (2, False), (3, True)])
def test_report_applies_threshold_to_complete_runs(stage2, failures, dropped):
    """Complete runs retain the 95 percent acceptance boundary."""
    rows = {str(i): ({"t1_pass": i >= failures}, 1, False) for i in range(50)}
    summary = stage2._summary(rows, (1, 50))
    assert not summary["incomplete"]
    assert summary["drop"] is dropped
    assert summary["t1_pass"] == (50 - failures) / 50


def test_incomplete_candidate_does_not_hide_best_complete_candidate(stage2, capsys):
    """Better partial results cannot displace a fully evaluated candidate."""
    complete = stage2._summary({"1": ({"t1_pass": 1}, 2, False)}, (2, 1))
    incomplete = stage2._summary({"1": ({}, 1, False)}, (1, 1))
    stage2._table({"complete": complete, "incomplete": incomplete})
    output = capsys.readouterr().out
    assert output.index("`complete`") < output.index("`incomplete`")
    assert "**2.0 s**" in output
    assert "**1.0 s**" not in output


@pytest.mark.parametrize("score_location", ["full", "inline", "missing"])
def test_backfill_only_pays_for_missing_scores(stage2, mocker, score_location):
    """Either score source prevents a paid call, including a zero-valued score."""
    evaluator = mocker.Mock(
        return_value=SimpleNamespace(
            name="t2_fabricated",
            value=1,
            data_type="NUMERIC",
            comment="clean",
            metadata={"cost": 0.06},
        ),
    )
    evaluator.__name__ = "eval_fabricated"
    stage2.judge.JUDGES = {"opus": [evaluator]}
    client = mocker.Mock()
    client.get_dataset.return_value.items = [
        SimpleNamespace(id="source-1", input={"content": "source"}),
    ]
    mocker.patch.object(stage2, "Langfuse", return_value=client)
    mocker.patch.object(
        stage2,
        "discover_runs",
        return_value={"vendor/model / strategy": {"id": "run-1"}},
    )
    mocker.patch.object(
        stage2,
        "_tier2_scores",
        return_value={"obs-1": {"t2_fabricated": 0}}
        if score_location == "full"
        else {},
    )
    mocker.patch.object(
        stage2.API,
        "experiment_items",
        return_value=[
            {
                "id": "obs-1",
                "experimentItemId": "source-1",
                "traceId": "trace-1",
                "output": "summary",
                "scores": [
                    {"name": "t2_fabricated", "value": 1},
                ]
                if score_location == "inline"
                else [],
            },
        ],
    )
    stage2.backfill("opus", ["vendor/model"])
    if score_location == "missing":
        evaluator.assert_called_once_with(input={"content": "source"}, output="summary")
        assert client.create_score.call_args.kwargs["observation_id"] == "obs-1"
    else:
        evaluator.assert_not_called()
        client.create_score.assert_not_called()
