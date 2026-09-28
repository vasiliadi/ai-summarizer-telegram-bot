"""Compare stage: a candidate over the 50-item set, with Tier 1 and JEV.

One run per candidate: the Langfuse rule scores Tier 1 on every compare run for
free, and JEV is the default Tier 2 judge. Tier 1 is the only hard gate. JEV's weakest-
bullet probability is a signal of plain fabrication, read against the other
candidates — above all the production model — and never against a floor. The
harness is a filter, not a ranking: the user reads the survivors.

    uv run python scripts/eval/stage2.py report                         # free
    uv run python scripts/eval/stage2.py sweep <model> ... [--judge=jev|opus|none]  # COSTS MONEY
    uv run python scripts/eval/stage2.py judge jev [<model> ...]        # ~2 cents a run: add JEV to runs
    uv run python scripts/eval/stage2.py judge opus <model> ...         # ~$3 a run: Opus FABRICATED on finalists

Models are named by their OpenRouter id and passed as arguments; there is no
default list and the registry is not consulted, because the point is to decide
whether a model belongs in `config.MODEL_SPECS` at all.

**Means do not rank models.** With 25-50 items a few points of difference
between two means is noise, so the means are paired with a sign test over
per-item Tier 2 deltas between two candidates, on the *same* items.

A candidate is a model **and** a strategy, because `t1_pass` and the Tier 2
means compare models only within one strategy. So runs are keyed by
`<model> / <prompt_key>` throughout.
"""

from __future__ import annotations

import math
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from itertools import combinations

import _bootstrap
import requests
from langfuse import Langfuse
from langfuse_api import LangfuseAPI, score_value

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

import judge

COMPARE = judge.COMPARE_DATASET
RUN_PREFIX = judge.RUN_PREFIX
CATALOG_URL = "https://openrouter.ai/api/v1/models"

# Two failures in 50 are forgiven; a systematic defect is not. 70% suited checks
# that only caught outright breakage, but `t1_script_clean` fails an item on a
# single stray character, and hy3 leaked CJK into ~6% of summaries — enough to
# be unusable, and well inside a 70% floor. Strong models score 100%.
PASS_THRESHOLD = 0.95

JEV = "t2_jev_weakest"
FABRICATED = "t2_fabricated"

# The paired Tier 2 tests run on these, whichever a run carries.
PAIRED_METRICS = (JEV, FABRICATED)


def discover_runs(dataset_name):
    """Candidate label -> newest compare experiment for it, from Langfuse itself.

    `GET /experiments` returns seven fields and none of them is metadata, so the
    candidate has to be read back out of the run name — which is the whole
    reason `judge.run` writes the name it does.
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


def _tier2_scores():
    """Observation id -> {Tier 2 score name: value}, read from the score table.

    **The experiment-items read returns at most seven scores per item.** An item
    carrying five Tier 1 scores, a retired Tier 2 score, JEV and then
    `t2_fabricated` came back with seven and the eighth silently missing, so the
    report showed "-" for a judge that had scored every item (found 2026-09-28).
    Tier 2 scores are therefore read by name from `v3/scores` and merged in; the
    inline scores still serve Tier 1.
    """
    out: dict[str, dict] = {}
    for name in PAIRED_METRICS:
        rows = API.paginate(
            "v3/scores",
            {"name": name, "limit": 100, "fields": "core,subject"},
        )
        for row in rows:
            subject = row.get("subject") or {}
            if subject.get("kind") == "observation":
                out.setdefault(subject["id"], {})[name] = score_value(row)
    return out


def _item_rows(experiment, tier2):
    """Dataset item id -> ({score name: value}, latency seconds)."""
    return {
        item["experimentItemId"]: (
            {s["name"]: s.get("value") for s in (item.get("scores") or [])}
            | tier2.get(item["id"], {}),
            _seconds(item),
        )
        for item in API.experiment_items(experiment["id"], fields="core,scores")
    }


def _run_cost(experiment):
    """(dollars, items priced) OpenRouter charged for a run's summaries.

    The cost wrapper in `src/llm.py` puts what OpenRouter charged on each
    generation as `gen_ai.usage.cost`, which Langfuse returns as `totalCost` —
    but only when the `usage` field group is requested; without it the field
    is simply absent. One paginated read over the run's time window, kept to
    the run's own traces, rather than a request per trace: the bot's own
    traffic in the same window is dropped by the trace filter. Judge calls are
    not on these traces, so this is the candidate's bill alone.
    """
    items = API.experiment_items(experiment["id"], fields="core")
    traces = {i["traceId"] for i in items}
    starts = [i["startTime"] for i in items if i.get("startTime")]
    ends = [i["endTime"] for i in items if i.get("endTime")]
    if not traces or not starts:
        return None, 0
    params = {
        "type": "GENERATION",
        "fields": "core,usage",
        "limit": 100,
        "fromStartTime": min(starts),
    }
    if ends:
        params["toStartTime"] = max(ends)
    cost, priced = 0.0, set()
    for row in API.paginate("v2/observations", params):
        if row.get("traceId") in traces and row.get("totalCost") is not None:
            cost += row["totalCost"]
            priced.add(row["traceId"])
    return cost, len(priced)


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


def _jev_cells(scores):
    """Median weakest-bullet probability, and the share flagged below the line."""
    values = [s[JEV] for s in scores if s.get(JEV) is not None]
    if not values:
        return f"{'-':>8s} {'-':>9s}"
    flagged = sum(1 for v in values if v < judge.JEV_FLAG_BELOW) / len(values)
    return f"{statistics.median(values):8.2f} {flagged:9.0%}"


def _cost_cell(cost, n_items):
    """The run's bill; starred when not every item's generation was priced."""
    if not cost or cost[0] is None:
        return f"{'-':>7s}"
    dollars, priced = cost
    return f"{dollars:6.2f}{'*' if priced < n_items else ' '}"


def _tier2_table(rows_by_candidate, costs):
    """Per-candidate means, with the caveat that they do not rank anything."""
    header = (
        f"{'model':28s} {'strategy':12s} {'n':>3s} "
        f"{'invented':>9s} {'jev med':>8s} {f'jev<{judge.JEV_FLAG_BELOW}':>9s} "
        f"{'t1_pass':>8s} {'compress':>9s} {'latency':>8s} {'run $':>7s}"
    )
    print("\nTier 2 means - context only; the paired tests below are what rank")
    print(header)
    print("-" * len(header))
    for candidate, rows in sorted(rows_by_candidate.items()):
        model, strategy = _split(candidate)
        scores = [s for s, _ in rows.values()]
        latencies = [s for _, s in rows.values() if s is not None]
        fabricated = [s[FABRICATED] for s in scores if s.get(FABRICATED) is not None]
        cells = [
            # The share of summaries Opus found something invented in.
            _mean_cell([1 - v for v in fabricated], 9, ".0%"),
            _jev_cells(scores),
        ]
        passes = [s["t1_pass"] for s in scores if "t1_pass" in s]
        comp = [s["t1_compression"] for s in scores if "t1_compression" in s]
        latency = f"{statistics.median(latencies):7.1f}s" if latencies else f"{'-':>8s}"
        print(
            f"{model:28s} {strategy.replace('_for_transcript', ''):12s} "
            f"{len(rows):3d} " + " ".join(cells) + " "
            f"{_mean_cell(passes, 8, '.0%')} {_mean_cell(comp, 9, '.4f')} {latency} "
            f"{_cost_cell(costs.get(candidate), len(rows))}",
        )


def _paired_tier2_table(rows_by_candidate, metric):
    """Sign test on per-item Tier 2 deltas, for every pair sharing items.

    It needs no judge call beyond the Tier 2 scores each run already banked,
    and it answers the question the means table cannot — whether one candidate
    beats another on the *same* item more often than not.
    """
    header = (
        f"{'pair (better/worse is for the left candidate)':52s} "
        f"{'n':>3s} {'better':>7s} {'worse':>6s} {'median d':>9s} {'p':>7s}"
    )
    print(f"\nPaired {metric} - per-item deltas, sign test")
    print(header)
    print("-" * len(header))
    printed = 0
    for left, right in combinations(sorted(rows_by_candidate), 2):
        deltas = _deltas(rows_by_candidate, left, right, metric)
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
        print(f"  no candidate pair shares an item scored on {metric}")


def _shared_items(rows_by_candidate, left, right):
    if left not in rows_by_candidate or right not in rows_by_candidate:
        return set()
    return set(rows_by_candidate[left]) & set(rows_by_candidate[right])


def _deltas(rows_by_candidate, left, right, metric):
    """Per-item `metric` difference, left minus right, on shared items."""
    out = []
    for item in sorted(_shared_items(rows_by_candidate, left, right)):
        a = rows_by_candidate[left][item][0].get(metric)
        b = rows_by_candidate[right][item][0].get(metric)
        if a is not None and b is not None:
            out.append(a - b)
    return out


def _filter(rows_by_candidate):
    """Who goes on to be read live: Tier 1 is the gate, the judges are signals.

    `t1_pass` below `PASS_THRESHOLD` drops a candidate — the only check here
    that is deterministic. Neither judge sets a floor: JEV's flagged share and,
    for finalists, Opus's invented share are printed for the user to weigh
    against cost, compression and the other candidates.
    """
    keep, drop = [], []
    for candidate, rows in sorted(rows_by_candidate.items()):
        scores = [s for s, _ in rows.values()]
        passes = [s["t1_pass"] for s in scores if "t1_pass" in s]
        reasons = []
        if passes and sum(passes) / len(passes) < PASS_THRESHOLD:
            reasons.append(f"t1_pass {sum(passes) / len(passes):.0%}")
        jev = [s[JEV] for s in scores if s.get(JEV) is not None]
        signal = (
            f"jev<{judge.JEV_FLAG_BELOW} {sum(v < judge.JEV_FLAG_BELOW for v in jev) / len(jev):.0%}"
            if jev
            else "no jev"
        )
        (drop if reasons else keep).append(
            f"{_short(candidate)} ({', '.join(reasons) or signal})",
        )
    print(
        f"\nFilter: t1_pass below {PASS_THRESHOLD:.0%} is dropped; the judges are signals",
    )
    print(f"KEEP ({len(keep)}): {', '.join(keep) or 'none'}")
    print(f"DROP ({len(drop)}): {', '.join(drop) or 'none'}")


def _short(candidate):
    """Drop the strategy when it is the one every candidate is swept under."""
    model, strategy = _split(candidate)
    return model if strategy == judge.PROMPT_KEY else candidate


def report(dataset_name=COMPARE):
    """Aggregate every compare run on one dataset and apply the Tier 1 gate."""
    runs = discover_runs(dataset_name)
    if not runs:
        sys.exit(
            f"no runs found with prefix {RUN_PREFIX!r} on {dataset_name!r}; "
            "run `stage2.py sweep <model>` first",
        )
    print(f"\nStage 2 - {dataset_name}, thinking={judge.THINKING_LEVEL}")
    print(
        f"{len(runs)} candidate(s); Tier 2: {judge.JEV_MODEL}, "
        f"and {judge.FABRICATED_MODEL} where run",
    )

    tier2 = _tier2_scores()
    rows_by_candidate = {c: _item_rows(e, tier2) for c, e in runs.items()}
    costs = {c: _run_cost(e) for c, e in runs.items()}
    _tier2_table(rows_by_candidate, costs)
    print(
        "  run $ is what OpenRouter charged for the 50 summaries (* = some unpriced); judge calls excluded",
    )
    for metric in PAIRED_METRICS:
        _paired_tier2_table(rows_by_candidate, metric)
    _filter(rows_by_candidate)

    # The `n` column counts a run's items, while a mean covers only the items
    # that carry the score — a judge call that failed attaches nothing. Say so
    # rather than let a mean over half a run read as that run's verdict. A run
    # with no score at all under a judge was simply not judged by it.
    incomplete = []
    for c, rows in sorted(rows_by_candidate.items()):
        for metric in PAIRED_METRICS:
            scored = sum(1 for s, _ in rows.values() if s.get(metric) is not None)
            if 0 < scored < len(rows):
                incomplete.append(f"{c}: {metric} on {scored} of {len(rows)} items")
    if incomplete:
        print("\nINCOMPLETE COVERAGE - a Tier 2 score is missing on some items:")
        for line in incomplete:
            print(f"  {line}")
        print("      Rows above average only the items that carry it.")


def backfill(tier2, models=(), dataset_name=COMPARE):
    """Score a Tier 2 judge on compare items that lack it, without regenerating.

    `tier2` names an entry of `judge.JUDGES` — `jev` at about two cents a run,
    `opus` at about $3 — and `models` limits it to those candidates, which is
    how Opus is spent on finalists only. The score is attached exactly as
    `run_experiment` attaches an evaluator's: to the experiment item's
    observation, whose id is the item's `id`. Anything else — the trace alone,
    say — would be missing from the experiment-items read the report is built
    on, and look like the judge never ran.
    """
    (evaluator,) = judge.JUDGES[tier2]
    client = Langfuse()
    sources = {
        i.id: i.input  # the evaluator reads `content` off the item input
        for i in client.get_dataset(dataset_name).items
    }
    todo = []
    for candidate, run in sorted(discover_runs(dataset_name).items()):
        if models and _split(candidate)[0] not in models:
            continue
        for item in API.experiment_items(run["id"], fields="core,io,scores"):
            names = {s["name"] for s in item.get("scores") or []}
            summary = judge._text(item.get("output"))  # noqa: SLF001
            if not summary or summary.startswith("Error:"):
                continue
            todo.append((candidate, item, summary, names))
    # The score name is only known from an evaluation, so skip on a probe.
    probe = evaluator.__name__.removeprefix("eval_")
    name = {"jev": JEV, "fabricated": FABRICATED}[probe]
    todo = [(c, i, s) for c, i, s, names in todo if name not in names]
    print(f"{len(todo)} item(s) without {name}")

    def one(job):
        candidate, item, summary = job
        try:
            result = evaluator(input=sources[item["experimentItemId"]], output=summary)
        except (OSError, RuntimeError, KeyError, ValueError) as exc:
            return candidate, item["experimentItemId"], 0, str(exc)[:200]
        if result is None:
            return candidate, item["experimentItemId"], 0, "evaluator returned nothing"
        client.create_score(
            name=result.name,
            value=result.value,
            data_type=result.data_type,
            comment=result.comment,
            trace_id=item["traceId"],
            observation_id=item["id"],
            metadata=result.metadata,
        )
        return (
            candidate,
            item["experimentItemId"],
            (result.metadata or {}).get("cost") or 0,
            None,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, todo))
    client.flush()
    failed = [r for r in results if r[3]]
    print(f"{len(results) - len(failed)} scored, ${sum(r[2] for r in results):.4f}")
    for candidate, item, _, error in failed:
        print(f"  FAILED {candidate} {item}: {error}")
    print("wait a minute for ingestion, then `stage2.py report`")


def _resolve(model_ids):
    """Check every id against OpenRouter's catalog before anything is spent.

    A typo or a wrongly guessed id would otherwise surface as a per-item error
    partway through a paid sweep. Never *derive* an id by prefixing a vendor
    name: the catalog carries `:free` and `:batch` siblings of the plain id, so
    a computed id can silently select the wrong one. Exits naming the
    near-misses.
    """
    catalog = requests.get(CATALOG_URL, timeout=60).json()["data"]
    names = {m["id"] for m in catalog}
    unknown = [m for m in model_ids if m not in names]
    for bad in unknown:
        stem = bad.split(":")[0]
        near = sorted(i for i in names if i.startswith(stem))
        hint = f" — did you mean {', '.join(near)}?" if near else ""
        print(f"unknown OpenRouter model: {bad}{hint}")
    if unknown:
        sys.exit("nothing run")


def sweep(model_ids, dataset_name=COMPARE, prompt_key=None, tier2="jev"):
    """Produce a compare run for each model, over the whole dataset.

    Ids are validated against the OpenRouter catalog up front, so the sixth
    id's typo is not found after the first five are paid for.
    """
    if not model_ids:
        sys.exit(
            "usage: stage2.py sweep <openrouter-model-id> [...]\n"
            "  ids are OpenRouter ids, e.g. vendor/model",
        )
    prompt_key = prompt_key or judge.PROMPT_KEY
    _resolve(model_ids)
    print(f"{len(model_ids)} model(s) over {dataset_name}, {prompt_key}\n")
    for index, model_id in enumerate(model_ids, 1):
        print(f"[{index}/{len(model_ids)}] {model_id}")
        judge.run(model_id, dataset_name, prompt_key, tier2=tier2)
        print()
    print("done - `stage2.py report` next")


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "report"
    if command == "report":
        report(args[1] if len(args) > 1 else COMPARE)
    elif command == "sweep":
        tier2 = next(
            (a.split("=", 1)[1] for a in args if a.startswith("--judge=")),
            "jev",
        )
        sweep([a for a in args[1:] if not a.startswith("--judge=")], tier2=tier2)
    elif command == "judge":
        if len(args) < 2 or args[1] not in judge.JUDGES or args[1] == "none":
            sys.exit("usage: stage2.py judge jev|opus [<openrouter-model-id> ...]")
        backfill(args[1], tuple(args[2:]))
    else:
        sys.exit(f"unknown command: {command}")
