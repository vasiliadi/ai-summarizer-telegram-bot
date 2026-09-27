"""Compare stage: the screening survivors on the calibrated faithfulness judge.

Screening only proves a model is not broken. This runs the survivors over the
50-item set with Tier 2 and reports who to keep for the user to read live. The
harness is a filter, not a ranking: readability is the user's call, so Tier 3
pairwise was removed.

    uv run python scripts/eval/stage2.py report                    # free
    uv run python scripts/eval/stage2.py sweep <model> ...         # COSTS MONEY

**Means do not rank models.** With 25-50 items a few points of difference
between two means is noise, so the means are paired with a sign test over
per-item faithfulness deltas between two candidates, on the *same* items.

A candidate is a model **and** a strategy, because `t1_pass` and the Tier 2
means compare models only within one strategy. So runs are keyed by
`<model> / <prompt_key>` throughout.
"""

from __future__ import annotations

import math
import statistics
import sys
from datetime import datetime
from itertools import combinations

import _bootstrap
from langfuse_api import LangfuseAPI

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

import judge
import stage1

COMPARE = judge.COMPARE_DATASET
RUN_PREFIX = judge.RUN_PREFIX

TIER2 = ("t2_faithfulness",)

# The paired Tier 2 test runs on this one.
PAIRED_METRIC = "t2_faithfulness"

# A candidate whose summaries carry a material faithfulness error on more than
# 15% of items is dropped before the user reads any of it. Strong models scored
# 92-96% on 24 production sources (evals.md), so this removes models that invent
# facts without separating good ones — which is all a filter should do.
FAITHFULNESS_FLOOR = 0.85


def discover_runs(dataset_name):
    """Candidate label -> newest compare experiment for it, from Langfuse itself.

    `GET /experiments` returns seven fields and none of them is metadata, so the
    candidate has to be read back out of the run name — which is the whole
    reason `judge.cmd_run` writes the name it does.
    """
    runs = {}
    # experiments() returns newest first, so the first hit per candidate wins.
    for row in API.experiments(API.dataset_id(dataset_name), name_prefix=RUN_PREFIX):
        runs.setdefault(_candidate(row["name"]), row)
    return runs


def _candidate(run_name):
    """`stage2 / vendor/model / strategy - <timestamp>` -> `vendor/model / strategy`."""
    stem = run_name.removeprefix(RUN_PREFIX)
    return stem.split(" - ")[0]


def _split(candidate):
    model, _, strategy = candidate.partition(" / ")
    return model, strategy


def _seconds(item):
    start, end = item.get("startTime"), item.get("endTime")
    if not (start and end):
        return None
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def _item_rows(experiment):
    """Dataset item id -> ({score name: value}, latency seconds)."""
    return {
        item["experimentItemId"]: (
            {s["name"]: s.get("value") for s in (item.get("scores") or [])},
            _seconds(item),
        )
        for item in API.experiment_items(experiment["id"], fields="core,scores")
    }


def _sign_test(wins, losses):
    """Two-sided exact binomial p for `wins` against `losses` under a fair coin.

    Ties are dropped before this is called; that is what makes it a sign test
    over per-item deltas rather than a comparison of two means.
    """
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(tail + 1)) / 2**n)


def _mean_cell(values, width=9, spec=".3f"):
    if not values:
        return f"{'-':>{width}s}"
    return f"{sum(values) / len(values):{width}{spec}}"


def _tier2_table(rows_by_candidate):
    """Per-candidate means, with the caveat that they do not rank anything."""
    header = (
        f"{'model':28s} {'strategy':12s} {'n':>3s} "
        f"{'faithful':>9s} "
        f"{'t1_pass':>8s} {'compress':>9s} {'latency':>8s}"
    )
    print("\nTier 2 means - context only; the paired tests below are what rank")
    print(header)
    print("-" * len(header))
    for candidate, rows in sorted(rows_by_candidate.items()):
        model, strategy = _split(candidate)
        scores = [s for s, _ in rows.values()]
        latencies = [s for _, s in rows.values() if s is not None]
        cells = [
            _mean_cell([s[m] for s in scores if s.get(m) is not None]) for m in TIER2
        ]
        passes = [s["t1_pass"] for s in scores if "t1_pass" in s]
        comp = [s["t1_compression"] for s in scores if "t1_compression" in s]
        latency = f"{statistics.median(latencies):7.1f}s" if latencies else f"{'-':>8s}"
        print(
            f"{model:28s} {strategy.replace('_for_transcript', ''):12s} "
            f"{len(rows):3d} " + " ".join(cells) + " "
            f"{_mean_cell(passes, 8, '.0%')} {_mean_cell(comp, 9, '.4f')} {latency}",
        )


def _paired_tier2_table(rows_by_candidate):
    """Sign test on per-item Tier 2 deltas, for every pair sharing items.

    It needs no judge call beyond the Tier 2 scores each run already banked,
    and it answers the question the means table cannot — whether one candidate
    beats another on the *same* item more often than not.
    """
    header = (
        f"{'pair (better/worse is for the left candidate)':52s} "
        f"{'n':>3s} {'better':>7s} {'worse':>6s} {'median d':>9s} {'p':>7s}"
    )
    print(f"\nPaired {PAIRED_METRIC} - per-item deltas, sign test")
    print(header)
    print("-" * len(header))
    printed = 0
    for left, right in combinations(sorted(rows_by_candidate), 2):
        deltas = _deltas(rows_by_candidate, left, right)
        if not deltas:
            continue
        better = sum(1 for d in deltas if d > 0)
        worse = sum(1 for d in deltas if d < 0)
        pair = f"{_short(left)} vs {_short(right)}"
        print(
            f"{pair:52s} {len(deltas):3d} {better:7d} {worse:6d} "
            f"{statistics.median(deltas):9.3f} {_sign_test(better, worse):7.3f}",
        )
        printed += 1
    if not printed:
        print(f"  no candidate pair shares an item scored on {PAIRED_METRIC}")


def _shared_items(rows_by_candidate, left, right):
    if left not in rows_by_candidate or right not in rows_by_candidate:
        return set()
    return set(rows_by_candidate[left]) & set(rows_by_candidate[right])


def _deltas(rows_by_candidate, left, right):
    """Per-item `PAIRED_METRIC` difference, left minus right, on shared items."""
    out = []
    for item in sorted(_shared_items(rows_by_candidate, left, right)):
        a = rows_by_candidate[left][item][0].get(PAIRED_METRIC)
        b = rows_by_candidate[right][item][0].get(PAIRED_METRIC)
        if a is not None and b is not None:
            out.append(a - b)
    return out


def _filter(rows_by_candidate):
    """Who goes on to be read live, and who the faithfulness floor removes."""
    keep, drop, unscored = [], [], []
    for candidate, rows in sorted(rows_by_candidate.items()):
        values = [
            s[PAIRED_METRIC]
            for s, _ in rows.values()
            if s.get(PAIRED_METRIC) is not None
        ]
        if not values:
            unscored.append(_short(candidate))
            continue
        rate = sum(values) / len(values)
        (keep if rate >= FAITHFULNESS_FLOOR else drop).append(
            f"{_short(candidate)} {rate:.0%}",
        )
    print(f"\nFilter: {PAIRED_METRIC} below {FAITHFULNESS_FLOOR:.0%} is dropped")
    print(f"KEEP     ({len(keep)}): {', '.join(keep) or 'none'}")
    print(f"DROP     ({len(drop)}): {', '.join(drop) or 'none'}")
    if unscored:
        print(f"UNSCORED ({len(unscored)}): {', '.join(unscored)}")


def _short(candidate):
    """Drop the strategy when it is the one every candidate is swept under."""
    model, strategy = _split(candidate)
    return model if strategy == judge.PROMPT_KEY else candidate


def report(dataset_name=COMPARE):
    """Aggregate every compare run on one dataset and apply the faithfulness floor."""
    runs = discover_runs(dataset_name)
    if not runs:
        sys.exit(
            f"no runs found with prefix {RUN_PREFIX!r} on {dataset_name!r}; "
            f"run `judge.py run <model> 0 {dataset_name}` first",
        )
    print(f"\nStage 2 - {dataset_name}, thinking={judge.THINKING_LEVEL}")
    print(f"{len(runs)} candidate(s), judge {judge.JUDGE_MODEL}")

    rows_by_candidate = {c: _item_rows(e) for c, e in runs.items()}
    _tier2_table(rows_by_candidate)
    _paired_tier2_table(rows_by_candidate)
    _filter(rows_by_candidate)

    # The `n` column counts a run's items, while a mean covers only the items
    # that carry the score — a judge call that failed attaches nothing. Say so
    # rather than let a mean over half a run read as that run's verdict.
    incomplete = [
        f"{c}: {sum(1 for s, _ in rows.values() if s.get(PAIRED_METRIC) is not None)}"
        f" scored of {len(rows)} items"
        for c, rows in sorted(rows_by_candidate.items())
        if sum(1 for s, _ in rows.values() if s.get(PAIRED_METRIC) is not None)
        != len(rows)
    ]
    if incomplete:
        print(f"\nINCOMPLETE COVERAGE - {PAIRED_METRIC} is missing on some items:")
        for line in incomplete:
            print(f"  {line}")
        print("      Rows above average only the items that carry it.")


def sweep(model_ids, dataset_name=COMPARE, prompt_key=None):
    """Produce a compare run for each model, over the whole dataset.

    `judge.py run` takes one model, which is six invocations for a six-model
    field and no check that the sixth id is real until the first five are paid
    for. Ids are validated against the OpenRouter catalog up front, exactly as
    the screening sweep does and for the same reason.
    """
    if not model_ids:
        sys.exit(
            "usage: stage2.py sweep <openrouter-model-id> [...]\n"
            "  ids are OpenRouter ids, e.g. vendor/model",
        )
    prompt_key = prompt_key or judge.PROMPT_KEY
    stage1._resolve(model_ids)  # noqa: SLF001
    print(f"{len(model_ids)} model(s) over {dataset_name}, {prompt_key}\n")
    for index, model_id in enumerate(model_ids, 1):
        print(f"[{index}/{len(model_ids)}] {model_id}")
        judge.cmd_run(model_id, 0, dataset_name, prompt_key)
        print()
    print("done - `stage2.py report` next")


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "report"
    if command == "report":
        report(args[1] if len(args) > 1 else COMPARE)
    elif command == "sweep":
        sweep(args[1:])
    else:
        sys.exit(f"unknown command: {command}")
