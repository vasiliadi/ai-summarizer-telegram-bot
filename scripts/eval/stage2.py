"""Compare stage: a candidate over the 50-item set, with Tier 1 and JEV.

One run per candidate: the Langfuse rule scores Tier 1 on every compare run for
free, and JEV is the default Tier 2 judge. Tier 1 is the only hard gate. JEV's
weakest-bullet probability is a signal of plain fabrication, read against the
other candidates and never against a floor; Opus is added on finalists. The
harness is a filter, not a ranking: a person reads the survivors.

    uv run python scripts/eval/stage2.py report [--all-pairs]           # free
    uv run python scripts/eval/stage2.py sweep <model> ... [--judge=jev|opus|none]  # COSTS MONEY
    uv run python scripts/eval/stage2.py judge jev [<model> ...]        # ~2 cents a run: add JEV to runs
    uv run python scripts/eval/stage2.py judge opus <model> ...         # ~$3 a run: Opus FABRICATED on finalists

Models are named by their OpenRouter id and passed as arguments; there is no
default list and the registry is not consulted, because the point is to decide
whether a model belongs in `config.MODEL_SPECS` at all.

`report` prints one markdown table. **Its means do not rank models**: with 50
items a few points between two means can be noise, and `--all-pairs` adds a
sign test over per-item Tier 2 deltas for every pair of candidates, on the
*same* items.

A candidate is a model **and** a strategy, because `t1_pass` and the Tier 2
means compare models only within one strategy. So runs are keyed by
`<model> / <prompt_key>` throughout.
"""

from __future__ import annotations

import collections
import math
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from itertools import combinations

import _bootstrap
import requests
from langfuse import Langfuse
from langfuse_api import EPOCH, LangfuseAPI, score_value

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

# The snapshot behind every JEV score banked before `judge_model_version` was
# recorded: `typesafe/jev-1.13` answered as this on 2026-09-30 (evals.md, *Tier 2*).
UNRECORDED_JEV = "typesafe/jev-1.13-20260917"

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


def _tier2_scores(runs):
    """Tier 2 scores by observation id, and the JEV snapshot behind each.

    Returns `({observation id: {score name: value}}, {observation id: snapshot})`.
    The snapshot is the score's `judge_model_version`, `None` for scores banked
    before it was recorded; it rides in the score metadata, which only the
    `details` field group returns.

    **The experiment-items read returns at most seven scores per item.** An item
    carrying five Tier 1 scores, a retired Tier 2 score, JEV and then
    `t2_fabricated` came back with seven and the eighth silently missing, so the
    report showed "-" for a judge that had scored every item.
    Tier 2 scores are therefore read by name from `v3/scores` and merged in; the
    inline scores still serve Tier 1. No score predates the run it scores, so
    the read starts at the earliest of `runs`.
    """
    since = min((r["startTime"] for r in runs.values()), default=EPOCH)
    out: dict[str, dict] = {}
    jev_versions: dict[str, str | None] = {}
    for name in PAIRED_METRICS:
        rows = API.paginate(
            "v3/scores",
            {
                "name": name,
                "limit": 100,
                "fields": "core,subject,details",
                "fromTimestamp": since,
            },
        )
        for row in rows:
            subject = row.get("subject") or {}
            if subject.get("kind") != "observation":
                continue
            out.setdefault(subject["id"], {})[name] = score_value(row)
            if name == JEV:
                meta = row.get("metadata") or {}
                jev_versions[subject["id"]] = meta.get("judge_model_version")
    return out, jev_versions


def _snapshots(counts):
    """`Counter` of JEV snapshots -> "`typesafe/jev-1.13-20260917` x40, unrecorded x10"."""
    return ", ".join(
        f"`{version}` x{n}" if version else f"unrecorded x{n}"
        for version, n in counts.most_common()
    )


def _jev_snapshot_notes(items, jev_versions):
    """Say which JEV snapshots scored the report, and warn when they differ.

    `JEV_MODEL` is an alias, so the snapshot recorded on each score is the only
    thing that says whether two candidates were measured by the same judge.
    Unrecorded scores predate the field but are not of unknown origin: they
    count as `UNRECORDED_JEV`, so old scores beside a newer snapshot are a mix.
    """
    by_candidate = {
        c: collections.Counter(
            jev_versions[i["id"]] for i in rows if i["id"] in jev_versions
        )
        for c, rows in items.items()
    }
    total = sum(by_candidate.values(), collections.Counter())
    if not total:
        return
    print(f"JEV answered as {_snapshots(total)}")
    if len({v or UNRECORDED_JEV for v in total}) > 1:
        print(
            "WARNING: JEV scores come from more than one snapshot; compare "
            "candidates only on scores from the same one.",
        )
        for candidate, counts in sorted(by_candidate.items()):
            print(f"  {_short(candidate)}: {_snapshots(counts)}")


def _item_rows(items, tier2):
    """Dataset item id -> ({score name: value}, latency seconds, generation errored)."""
    return {
        item["experimentItemId"]: (
            {s["name"]: s.get("value") for s in (item.get("scores") or [])}
            | tier2.get(item["id"], {}),
            _seconds(item),
            judge.generation_failed(judge._text(item.get("output"))),  # noqa: SLF001
        )
        for item in items
    }


def _run_cost(items):
    """(dollars, items priced) OpenRouter charged for a run's summaries.

    The cost wrapper in `src/llm.py` puts what OpenRouter charged on each
    generation as `gen_ai.usage.cost`, which Langfuse returns as `totalCost` —
    but only when the `usage` field group is requested; without it the field
    is simply absent. One paginated read over the run's time window, kept to
    the run's own traces, rather than a request per trace: the bot's own
    traffic in the same window is dropped by the trace filter. Judge calls are
    not on these traces, so this is the candidate's bill alone.
    """
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


def _summary(rows, cost):
    """One candidate's report row: raw values, `None` where nothing was scored."""
    scores = [s for s, _, _ in rows.values()]
    latencies = [t for _, t, _ in rows.values() if t is not None]
    passes = [s["t1_pass"] for s in scores if "t1_pass" in s]
    comp = [s["t1_compression"] for s in scores if "t1_compression" in s]
    jev = [s[JEV] for s in scores if s.get(JEV) is not None]
    fabricated = [s[FABRICATED] for s in scores if s.get(FABRICATED) is not None]
    incomplete = not rows or len(passes) != len(rows)
    t1_pass = sum(passes) / len(passes) if not incomplete else None
    dollars, priced = cost or (None, 0)
    return {
        "t1_pass": t1_pass,
        "jev_median": statistics.median(jev) if jev else None,
        "jev_flagged": (
            sum(v < judge.JEV_FLAG_BELOW for v in jev) / len(jev) if jev else None
        ),
        # The share of summaries Opus found something invented in.
        "invented": 1 - sum(fabricated) / len(fabricated) if fabricated else None,
        "compression": sum(comp) / len(comp) if comp else None,
        "latency": statistics.median(latencies) if latencies else None,
        "cost": dollars,
        "drop": t1_pass is not None and t1_pass < PASS_THRESHOLD,
        "incomplete": incomplete,
        "t1_scored": len(passes),
        "n": len(rows),
        "errored": sum(e for _, _, e in rows.values()),
        "unpriced": dollars is not None and priced < len(rows),
        "scored": {"JEV": len(jev), "Opus": len(fabricated)},
    }


# Column -> (header, format, which end is best). Best is bolded among the kept
# candidates: a longer summary (higher compression) counts in a model's favour.
COLUMNS = {
    "t1_pass": ("t1_pass", "{:.0%}", max),
    "jev_median": ("JEV median", "{:.2f}", max),
    "jev_flagged": (f"JEV < {judge.JEV_FLAG_BELOW}", "{:.0%}", min),
    "invented": ("invented (Opus)", "{:.0%}", min),
    "compression": ("compression", "{:.3f}", max),
    "latency": ("latency", "{:.1f} s", min),
    "cost": ("run $", "{:.2f}", min),
}


def _notes(row):
    """Why a row's numbers cover fewer items than the run, if they do."""
    notes = []
    if row["incomplete"]:
        notes.append(f"Tier 1 scored {row['t1_scored']} of {row['n']} items")
    if row["errored"]:
        notes.append(f"{row['errored']} of {row['n']} items failed to generate")
    for judge_name, scored in row["scored"].items():
        if 0 < scored < row["n"] - row["errored"]:
            notes.append(f"{judge_name} scored {scored} of {row['n']} items")
    if row["unpriced"]:
        notes.append("some generations unpriced")
    return notes


def _table(summaries):  # noqa: C901
    """Print kept candidates first, then incomplete candidates, then dropped ones.

    Within each group, candidates Opus judged come first by invented share, the
    rest by JEV median, so the finalists sit at the top of the table.
    """

    def order(item):
        _, row = item
        opus = row["invented"] is None
        status = 2 if row["drop"] else int(row["incomplete"])
        return (status, opus, row["invented"] or 0, -(row["jev_median"] or 0))

    rows = sorted(summaries.items(), key=order)
    kept = [row for _, row in rows if not row["drop"] and not row["incomplete"]]
    best = {}
    for key, (_, spec, pick) in COLUMNS.items():
        values = [row[key] for row in kept if row[key] is not None]
        if values:
            best[key] = spec.format(pick(values))

    footnotes: list[str] = []
    print("| candidate | " + " | ".join(h for h, _, _ in COLUMNS.values()) + " |")
    print("|---" * (len(COLUMNS) + 1) + "|")
    for candidate, row in rows:
        label = f"`{_short(candidate)}`" + (" — DROP" if row["drop"] else "")
        if row["incomplete"]:
            label += " — INCOMPLETE"
        marks = []
        for note in _notes(row):
            if note not in footnotes:
                footnotes.append(note)
            marks.append(footnotes.index(note) + 1)
        label += "".join(f" [{m}]" for m in sorted(marks))
        cells = []
        for key, (_, spec, _) in COLUMNS.items():
            if row[key] is None:
                cells.append("—")
                continue
            text = spec.format(row[key])
            bold = not row["drop"] and not row["incomplete"] and best.get(key) == text
            cells.append(f"**{text}**" if bold else text)
        print(f"| {label} | " + " | ".join(cells) + " |")
    print()
    for number, note in enumerate(footnotes, 1):
        print(f"[{number}] {note}")
    print(
        f"DROP: t1_pass below {PASS_THRESHOLD:.0%}. The judges are signals and set no "
        "floor. run $ is what OpenRouter charged for the summaries; judge calls excluded.",
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


def _short(candidate):
    """Drop the strategy when it is the one every candidate is swept under."""
    model, strategy = _split(candidate)
    return model if strategy == judge.PROMPT_KEY else candidate


def report(dataset_name=COMPARE, *, all_pairs=False):
    """Print every compare run on one dataset as one table, Tier 1 gate applied.

    `all_pairs` adds a sign test over per-item deltas for every pair of
    candidates on each Tier 2 score — whether one beats another on the *same*
    items more often than not, which a gap between two means cannot tell.
    """
    runs = discover_runs(dataset_name)
    if not runs:
        sys.exit(
            f"no runs found with prefix {RUN_PREFIX!r} on {dataset_name!r}; "
            "run `stage2.py sweep <model>` first",
        )
    print(
        f"`{dataset_name}`, thinking `{judge.THINKING_LEVEL}`, {len(runs)} candidate(s); "
        f"JEV `{judge.JEV_MODEL}`, Opus `{judge.FABRICATED_MODEL}`",
    )
    tier2, jev_versions = _tier2_scores(runs)
    items = {
        c: API.experiment_items(e["id"], fields="core,io,scores")
        for c, e in runs.items()
    }
    _jev_snapshot_notes(items, jev_versions)
    print()
    rows_by_candidate = {c: _item_rows(i, tier2) for c, i in items.items()}
    summaries = {
        c: _summary(rows, _run_cost(items[c])) for c, rows in rows_by_candidate.items()
    }
    _table(summaries)
    if all_pairs:
        for metric in PAIRED_METRICS:
            _paired_tier2_table(rows_by_candidate, metric)


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
    runs = discover_runs(dataset_name)
    scores, _ = _tier2_scores(runs)
    for candidate, run in sorted(runs.items()):
        if models and _split(candidate)[0] not in models:
            continue
        for item in API.experiment_items(run["id"], fields="core,io,scores"):
            names = {s["name"] for s in item.get("scores") or []}
            names.update(scores.get(item["id"], {}))
            summary = judge._text(item.get("output"))  # noqa: SLF001
            if judge.generation_failed(summary):
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
        rest = [a for a in args[1:] if a != "--all-pairs"]
        report(rest[0] if rest else COMPARE, all_pairs="--all-pairs" in args)
    elif command == "sweep":
        tier2 = next(
            (a.split("=", 1)[1] for a in args if a.startswith("--judge=")),
            "jev",
        )
        if tier2 not in judge.JUDGES:
            sys.exit(
                "usage: stage2.py sweep <openrouter-model-id> ... [--judge=jev|opus|none]",
            )
        sweep([a for a in args[1:] if not a.startswith("--judge=")], tier2=tier2)
    elif command == "judge":
        if len(args) < 2 or args[1] not in judge.JUDGES or args[1] == "none":
            sys.exit("usage: stage2.py judge jev|opus [<openrouter-model-id> ...]")
        backfill(args[1], tuple(args[2:]))
    else:
        sys.exit(f"unknown command: {command}")
