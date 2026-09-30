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
        return_value={
            "vendor/model / strategy": {
                "id": "run-1",
                "startTime": "2026-09-28T00:00:00Z",
            },
        },
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


@pytest.mark.parametrize(
    ("runs", "since"),
    [
        (
            {
                "a": {"startTime": "2026-09-28T00:00:00Z"},
                "b": {"startTime": "2026-09-27T00:00:00Z"},
            },
            "2026-09-27T00:00:00Z",
        ),
        ({}, "2020-01-01T00:00:00Z"),
    ],
)
def test_tier2_scores_start_at_earliest_run(stage2, mocker, runs, since):
    """The score read is bounded by the oldest run it has to cover."""
    paginate = mocker.patch.object(stage2.API, "paginate", return_value=[])
    stage2._tier2_scores(runs)
    assert {c.args[1]["fromTimestamp"] for c in paginate.call_args_list} == {since}


# --- reading runs back ----------------------------------------------------------


def test_candidate_is_read_back_from_the_run_name(stage2):
    """The candidate is the run name between prefix and timestamp."""
    name = "stage2 / vendor/model / key_points_for_transcript - 2026-09-28T10:00:00Z"
    assert stage2._candidate(name) == "vendor/model / key_points_for_transcript"
    assert stage2._split("vendor/model / other") == ("vendor/model", "other")
    assert stage2._short("vendor/model / key_points_for_transcript") == "vendor/model"
    assert stage2._short("vendor/model / other") == "vendor/model / other"


def test_discover_runs_keeps_the_newest_run_per_candidate(stage2, mocker):
    """The report reads each candidate's newest run only."""
    mocker.patch.object(stage2.API, "dataset_id", return_value="ds-1")
    experiments = mocker.patch.object(
        stage2.API,
        "experiments",
        return_value=[
            {"name": "stage2 / a / s - 2026-09-29", "id": "new"},
            {"name": "stage2 / b / s - 2026-09-28", "id": "b"},
            {"name": "stage2 / a / s - 2026-09-27", "id": "old"},
        ],
    )
    runs = stage2.discover_runs("dataset")
    assert {k: v["id"] for k, v in runs.items()} == {"a / s": "new", "b / s": "b"}
    experiments.assert_called_once_with("ds-1", name_prefix=stage2.RUN_PREFIX)


@pytest.mark.parametrize(
    ("item", "seconds"),
    [
        (
            {
                "startTime": "2026-09-28T10:00:00+00:00",
                "endTime": "2026-09-28T10:00:21.5+00:00",
            },
            21.5,
        ),
        ({"startTime": "2026-09-28T10:00:00+00:00"}, None),
        ({}, None),
    ],
)
def test_seconds(stage2, item, seconds):
    """Latency is end minus start, or unknown without both."""
    assert stage2._seconds(item) == seconds


def test_item_rows_merge_tier2_scores_and_flag_failures(stage2):
    """Inline and Tier 2 scores merge per item; a failed generation is flagged."""
    items = [
        {
            "id": "obs-1",
            "experimentItemId": "src-1",
            "output": "- summary",
            "scores": [{"name": "t1_pass", "value": True}],
        },
        {"id": "obs-2", "experimentItemId": "src-2", "output": "", "scores": None},
    ]
    rows = stage2._item_rows(items, {"obs-1": {stage2.JEV: 0.8}})
    assert rows["src-1"] == ({"t1_pass": True, stage2.JEV: 0.8}, None, False)
    assert rows["src-2"] == ({}, None, True)


def test_tier2_scores_keep_observation_scores_only(stage2, mocker):
    """Scores on anything but an observation are ignored."""
    mocker.patch.object(
        stage2.API,
        "paginate",
        side_effect=[
            [
                {"subject": {"kind": "observation", "id": "obs-1"}, "value": 0.7},
                {"subject": {"kind": "trace", "id": "t-1"}, "value": 0.1},
                {"value": 0.2},
            ],
            [{"subject": {"kind": "observation", "id": "obs-1"}, "value": 1}],
        ],
    )
    assert stage2._tier2_scores({}) == {
        "obs-1": {stage2.JEV: 0.7, stage2.FABRICATED: 1},
    }


def test_run_cost_counts_only_the_runs_own_traces(stage2, mocker):
    """The bot's own traffic in the same window is not the candidate's bill."""
    paginate = mocker.patch.object(
        stage2.API,
        "paginate",
        return_value=[
            {"traceId": "t1", "totalCost": 0.01},
            {"traceId": "t1", "totalCost": 0.02},
            {"traceId": "t2", "totalCost": None},
            {"traceId": "bot", "totalCost": 5.0},
        ],
    )
    items = [
        {
            "traceId": "t1",
            "startTime": "2026-09-28T10:00",
            "endTime": "2026-09-28T10:05",
        },
        {
            "traceId": "t2",
            "startTime": "2026-09-28T09:00",
            "endTime": "2026-09-28T11:00",
        },
    ]
    cost, priced = stage2._run_cost(items)
    assert cost == pytest.approx(0.03)
    assert priced == 1
    params = paginate.call_args.args[1]
    assert params["fields"] == "core,usage"  # without it totalCost is absent
    assert params["fromStartTime"] == "2026-09-28T09:00"
    assert params["toStartTime"] == "2026-09-28T11:00"


def test_run_cost_without_items_is_unknown(stage2, mocker):
    """No items means no cost read at all."""
    paginate = mocker.patch.object(stage2.API, "paginate")
    assert stage2._run_cost([]) == (None, 0)
    paginate.assert_not_called()


# --- paired comparison ----------------------------------------------------------


@pytest.mark.parametrize(
    ("wins", "losses", "p"),
    [(0, 0, 1.0), (3, 3, 1.0), (5, 0, 0.0625), (0, 5, 0.0625), (9, 1, 0.021484375)],
)
def test_sign_test_is_the_exact_two_sided_binomial(stage2, wins, losses, p):
    """Known p-values, ties excluded by the caller."""
    assert stage2._sign_test(wins, losses) == pytest.approx(p)


def test_deltas_use_shared_items_scored_on_both_sides(stage2):
    """Only items both candidates were scored on are compared."""
    rows = {
        "a": {"1": ({"m": 0.9},), "2": ({"m": 0.5},), "3": ({},), "4": ({"m": 1},)},
        "b": {"1": ({"m": 0.4},), "2": ({"m": 0.7},), "3": ({"m": 0.1},)},
    }
    assert stage2._deltas(rows, "a", "b", "m") == pytest.approx([0.5, -0.2])
    assert stage2._deltas(rows, "a", "missing", "m") == []


def test_paired_table_prints_each_pair_sharing_items(stage2, capsys):
    """Pairs with shared items get a row; the rest are skipped."""
    rows = {
        "a / key_points_for_transcript": {str(i): ({"m": 1.0},) for i in range(5)},
        "b / other": {str(i): ({"m": 0.5},) for i in range(5)},
        "c / other": {"x": ({"m": 0.5},)},
    }
    stage2._paired_tier2_table(rows, "m")
    lines = capsys.readouterr().out.splitlines()
    pair = next(line for line in lines if line.startswith("a vs b / other"))
    assert pair.split()[-5:] == ["5", "5", "0", "0.500", "0.062"]
    assert not any(line.startswith("a vs c") for line in lines)


def test_paired_table_says_when_no_pair_shares_an_item(stage2, capsys):
    """An empty table says why it is empty."""
    stage2._paired_tier2_table({"a / s": {"1": ({"m": 1},)}, "b / s": {}}, "m")
    assert "no candidate pair shares an item scored on m" in capsys.readouterr().out
