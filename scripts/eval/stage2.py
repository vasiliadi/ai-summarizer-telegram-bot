"""Compare stage: rank the screening survivors, and say how sure the ranking is.

Screening only proves a model is not broken. This is where the ranking is
decided, over the 50-item set with the full scorer suite: Tier 2 per dimension
and Tier 3 pairwise with the order swapped.

    python scripts/eval/stage2.py report                    # free
    python scripts/eval/stage2.py duels [<model> ...]       # COSTS MONEY

`judge.py` holds the judge itself and runs one duel per invocation; this holds
the two things built on top of it — the aggregation `GET /experiments` does not
provide, and the driver that turns 15 manual duels into one command.

**Means do not rank models.** With 25-50 items a few points of difference
between two means is noise, so every mean printed here is paired with a test
over per-item deltas: the sign test on Tier 3 verdicts, and the same test on
per-item Tier 2 deltas between two candidates. Controlling for item difficulty
this way is worth roughly 3-4x the sample size, which is why every candidate
runs over the *same* items. Read the paired tables, not the first one.

A candidate is a model **and** a strategy, because `t1_pass` and the Tier 2
means rank models only within one strategy — comparing two strategies is Tier
3's job. So runs are keyed by `<model> / <prompt_key>` throughout, and a model
swept under both strategies appears as two candidates that can duel each other.
"""

from __future__ import annotations

import math
import random
import statistics
import sys
from datetime import datetime
from itertools import combinations

import _bootstrap
from langfuse_api import LangfuseAPI

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

import judge

COMPARE = judge.COMPARE_DATASET
RUN_PREFIX = judge.RUN_PREFIX

TIER2 = ("t2_faithfulness", "t2_coverage", "t2_no_filler")
PAIRWISE_SCORE = "t3_pairwise_win"

# The paired Tier 2 test runs on this one. Faithfulness is the metric with a
# value on every item — coverage is `None` until the key-facts checklists exist,
# and no_filler is binary, so per-item deltas are almost all zero.
PAIRED_METRIC = "t2_faithfulness"

BOOTSTRAP_SAMPLES = 2000
# Fixed, so re-reading the same banked verdicts prints the same interval. An
# unseeded bootstrap moves on every read, and the movement is indistinguishable
# from the data having changed.
BOOTSTRAP_SEED = 20260818

WIN_VALUE = {"A": 1.0, "TIE": 0.5, "B": 0.0}


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


def _value(row):
    """A score's value, whichever field this data type puts it in.

    A CATEGORICAL score carries its label in `stringValue`; a NUMERIC or
    BOOLEAN one carries a number in `value`. Nothing in this project had ever
    written a categorical score when this was written, so both are read rather
    than one being assumed — reading the wrong field returns `None` for every
    duel, which looks exactly like a judge that was never run.
    """
    return row.get("stringValue") or row.get("value")


def _duels():
    """(run A name, run B name) -> {dataset item id: 'A' | 'B' | 'TIE'}.

    Read from the score table, not from the experiment: a pairwise score is
    anchored to run A's trace and carries the pair in its metadata, so filtering
    scores by experiment id returns nothing for it.
    """
    out = {}
    for row in API.paginate(
        "v3/scores",
        {"limit": 100, "fields": "core,details", "name": PAIRWISE_SCORE},
    ):
        meta = row.get("metadata") or {}
        pair, item = (meta.get("run_a"), meta.get("run_b")), meta.get("dataset_item_id")
        if all(pair) and item:
            out.setdefault(pair, {})[item] = _value(row)
    return out


def _bootstrap_ci(values, confidence=0.95):
    """Percentile bootstrap interval for the mean of `values`."""
    if len(values) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311
    n = len(values)
    means = sorted(
        sum(rng.choice(values) for _ in range(n)) / n for _ in range(BOOTSTRAP_SAMPLES)
    )
    tail = (1 - confidence) / 2
    return means[int(tail * BOOTSTRAP_SAMPLES)], means[
        int((1 - tail) * BOOTSTRAP_SAMPLES) - 1
    ]


def _sign_test(wins, losses):
    """Two-sided exact binomial p for `wins` against `losses` under a fair coin.

    Ties are dropped before this is called; that is what makes it a sign test
    over per-item deltas rather than a comparison of two means, and it is the
    guard the plan asks for at this sample size.
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
        f"{'faithful':>9s} {'coverage':>9s} {'no_filler':>9s} "
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


def _duel_table(duels, rows_by_candidate):
    """Tier 3 win rates with a bootstrap CI and a sign test."""
    header = (
        f"{'duel (win rate is the left model)':52s} "
        f"{'n':>3s} {'unres':>6s} {'win':>6s} {'95% CI':>16s} {'p':>7s}"
    )
    print(
        "\nTier 3 duels - win rate for the left candidate, both orders, "
        "consistent verdicts only",
    )
    print(header)
    print("-" * len(header))
    if not duels:
        print("  no duels banked yet - run `stage2.py duels`")
        return
    for (run_a, run_b), verdicts in sorted(duels.items()):
        left, right = _candidate(run_a), _candidate(run_b)
        values = [WIN_VALUE[v] for v in verdicts.values() if v in WIN_VALUE]
        wins = sum(1 for v in verdicts.values() if v == "A")
        losses = sum(1 for v in verdicts.values() if v == "B")
        # Everything the two runs shared that produced no banked verdict. That
        # merges the judge abstaining (the two orders contradicted each other)
        # with a call that never returned; `judge.py pairwise` prints the true
        # split at run time, and only the abstentions are a judge-quality signal.
        shared = _shared_items(rows_by_candidate, left, right)
        unresolved = max(len(shared) - len(values), 0) if shared else 0
        ci = _bootstrap_ci(values)
        interval = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "-"
        rate = f"{sum(values) / len(values):6.2f}" if values else f"{'-':>6s}"
        pair = f"{_short(left)} vs {_short(right)}"
        print(
            f"{pair:52s} {len(values):3d} {unresolved:6d} {rate} "
            f"{interval:>16s} {_sign_test(wins, losses):7.3f}",
        )


def _paired_tier2_table(rows_by_candidate):
    """Sign test on per-item Tier 2 deltas, for every pair sharing items.

    This is the cheap half of the ranking: it needs no judge call beyond the
    Tier 2 scores each run already banked, and it answers the question the means
    table cannot — whether one candidate beats another on the *same* item more
    often than not.
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


def _short(candidate):
    """Drop the strategy when it is the one every candidate is swept under."""
    model, strategy = _split(candidate)
    return model if strategy == judge.PROMPT_KEY else candidate


def report(dataset_name=COMPARE):
    """Aggregate every compare run on one dataset and rank what it can."""
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
    _duel_table(_duels(), rows_by_candidate)
    _paired_tier2_table(rows_by_candidate)

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

    scored_coverage = any(
        s.get("t2_coverage") is not None
        for rows in rows_by_candidate.values()
        for s, _ in rows.values()
    )
    if not scored_coverage:
        print(
            "\nNOTE: t2_coverage is empty on every item. The dataset carries no "
            "key-facts checklists in `expected_output`, so `eval_coverage` "
            "returns nothing rather than inventing one.",
        )


def _resolve(runs, wanted):
    """Match each argument against a candidate label by prefix.

    A candidate is `<model> / <strategy>`, but the useful thing to type is the
    model. Ambiguity is refused rather than guessed: picking one of two
    strategies silently would bank a duel that answers a different question
    than the one asked.
    """
    if not wanted:
        return sorted(runs)
    out = []
    for name in wanted:
        matches = [c for c in sorted(runs) if c == name or c.startswith(f"{name} /")]
        if not matches:
            sys.exit(f"no compare run for {name!r}; have: {', '.join(sorted(runs))}")
        if len(matches) > 1:
            sys.exit(f"{name!r} matches {len(matches)}: {', '.join(matches)}")
        out.append(matches[0])
    return out


def duels(wanted=(), dataset_name=COMPARE):
    """Duel every pair of candidates that has not been duelled yet.

    `judge.py pairwise` takes one pair per invocation, and a six-candidate
    round-robin is fifteen of them. Pairs already banked are skipped on the
    exact run names their scores carry, so re-running a candidate produces a new
    run name and the pair is duelled again — which is what re-running it means.
    """
    runs = discover_runs(dataset_name)
    if not runs:
        sys.exit(f"no runs found with prefix {RUN_PREFIX!r} on {dataset_name!r}")
    candidates = _resolve(runs, wanted)
    done = set(_duels())
    pending = [
        (a, b)
        for a, b in combinations(candidates, 2)
        if (runs[a]["name"], runs[b]["name"]) not in done
        and (runs[b]["name"], runs[a]["name"]) not in done
    ]
    total = len(list(combinations(candidates, 2)))
    print(
        f"{len(candidates)} candidates, {total} pairs, "
        f"{total - len(pending)} already banked, {len(pending)} to run",
    )
    if not pending:
        return
    items = min(runs[c]["itemCount"] for c in candidates)
    print(f"~{len(pending) * items * 2} judge calls over ~{items} shared items\n")
    for index, (left, right) in enumerate(pending, 1):
        print(f"[{index}/{len(pending)}] {_short(left)} vs {_short(right)}")
        judge.cmd_pairwise(dataset_name, runs[left]["name"], runs[right]["name"])
        print()
    print("done - `stage2.py report` now has these duels")


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "report"
    if command == "report":
        report(args[1] if len(args) > 1 else COMPARE)
    elif command == "duels":
        duels(args[1:])
    else:
        sys.exit(f"unknown command: {command}")
