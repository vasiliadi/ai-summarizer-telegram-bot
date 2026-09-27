"""Judge calibration: measure the judge against hand labels before trusting it.

A judge is worth nothing until it agrees with a human. Nothing in a Tier 2
ranking means anything until this passes, so it runs *before* the compare stage
rather than after.

    uv run python scripts/eval/calibrate.py sample      # free: show the fixed sample
    uv run python scripts/eval/calibrate.py setup       # free: score configs and the queue
    uv run python scripts/eval/calibrate.py judge [<model>]   # COSTS MONEY
    uv run python scripts/eval/calibrate.py agreement [<file>]  # free: accuracy + kappa
    uv run python scripts/eval/calibrate.py export [<file>]     # free: labels to disk
    uv run python scripts/eval/calibrate.py versus <model> [--labels f] [--author m] [--variant v]  # COSTS MONEY

Only faithfulness is calibrated here. Tier 3 pairwise was removed: readability
is judged by the user reading the survivors, not by a model.

Calibration decides the judge model rather than assuming it. Run `judge` once
per candidate judge — the model id is an optional argument, defaulting to the
pinned `judge.JUDGE_MODEL` — and `agreement` reports every judge it finds side
by side against the same hand labels. Take the higher number, and if the
cheaper judge clears the bar, spend the difference on dataset items instead:
more items buy more statistical power than a better judge does.

The judge prompts and schemas are imported from `judge.py` and never restated.
Calibration has to measure the prompt production actually uses; a copy here
would drift and the agreement number would describe nothing.

Faithfulness is hand-labelled in a Langfuse annotation queue, and one detail
decides whether that measurement means anything: **queue items point at the root
span, never at the GENERATION inside it.** A screening trace holds four
observations. The root span's output is the clean summary, byte-identical to
what the judge is given. The generation's output is the model's reply *as
parts*, and a reasoning model puts a `thinking` part in front of the `text` one
— annotate that and the human reads a different artefact than the judge scores,
and sees reasoning the judge never sees. Both sit in the same trace, so picking
the wrong one is easy and nothing complains.

The sample is derived, not stored: items are sorted by id and dealt round-robin
across the screening runs, so re-running `sample` reproduces it exactly. That
matters because agreement is only comparable across prompt revisions when the
items stay fixed.

**The public API reads only the last 30 days on this plan, hand labels
included.** The 25 `h_faithful` labels behind the recorded calibration still
show on their queue items in the UI, but no API call returns them.
`export` writes the sample, the hand labels and every judge's verdicts to a
local file, and `agreement <file>` reports from that file once Langfuse has
stopped returning the originals — run `export` as soon as a round is
labelled. The file holds summaries of the user's own content, so it goes under
the gitignored `temp/` and never into this public repository.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import _bootstrap
import requests
from langfuse import Langfuse
from langfuse_api import LangfuseAPI, score_value

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

import judge
import stage1
import stage2

SCREEN = stage1.SCREEN

# The bar a cheaper judge must clear against the pinned one in `versus`, agreed
# before the first run on 2026-09-27: a filter judge that misses real errors
# passes models that invent facts, so the catch rate is the number that decides.
VERSUS_MIN_CATCH = 0.75
VERSUS_MAX_FALSE_ALARMS = 5

JEV_MODEL = "typesafe/jev-1.13"
# Fixed before the first per-bullet run, not tuned on it: a bullet below even
# odds of being supported fails its summary.
JEV_THRESHOLD = 0.5
JEV_INSTRUCTIONS = (
    "A summary of the source makes this claim: «{claim}». The summary may be in "
    "another language than the source; a faithful translation of a supported claim "
    "is supported. Compression, rewording, generalisation, merging related points "
    "and leaving details out are not errors. The claim fails only if it contradicts "
    "the source, adds a fact the source neither states nor implies, changes a status "
    "(proposed to done, can to does, planned to released), distorts a number, date or "
    "scale, asserts a causal link the source never draws, or attributes something to "
    "the wrong person or company — so that a reader acting on it would be misled."
)
JEV_CRITERIA = {
    "true": "The source supports the claim.",
    "false": "The claim materially misstates or invents something relative to the source.",
}
# The question with every exclusion and error type stripped, keeping only the
# note on translation: summaries are Russian and most sources are not.
JEV_MINIMAL = (
    "Is this claim supported by the source? The claim may be a translation. "
    "Claim: «{claim}»"
)
JEV_MINIMAL_CRITERIA = {
    "true": "The source states or clearly implies the claim.",
    "false": "The source contradicts the claim or does not contain it.",
}
# The user's question after labelling the judges' disagreements, where only
# invented facts counted as errors. The question asks about invention, but
# `true` stays the clean answer so every variant is read the same way.
JEV_INVENTED = (
    "Does this claim state a fact that is not in the source? The claim may be a "
    "translation. Claim: «{claim}»"
)
JEV_INVENTED_CRITERIA = {
    "true": "No: every fact the claim states is in the source.",
    "false": "Yes: the claim states a fact the source does not contain.",
}
# Variant -> (instructions, criteria, all bullets in one call). Separating the
# call shape from the wording tells which of the two moves the result.
JEV_VARIANTS = {
    "batched": (JEV_INSTRUCTIONS, JEV_CRITERIA, True),
    "single": (JEV_INSTRUCTIONS, JEV_CRITERIA, False),
    "minimal": (JEV_MINIMAL, JEV_MINIMAL_CRITERIA, False),
    "invented": (JEV_INVENTED, JEV_INVENTED_CRITERIA, True),
    # `minimal` in one call: batching was measured to change nothing.
    "minimal-batched": (JEV_MINIMAL, JEV_MINIMAL_CRITERIA, True),
}

# Human channels vs judge channels. Distinct names, one score table — which is
# what keeps the comparison a query instead of a spreadsheet.
H_FAITHFUL, C_FAITHFUL = "h_faithful", "cal_faithful"

# The Hobby plan allows exactly one annotation queue, and there is no API route
# to update a queue's score configs after creation.
QUEUE_NAME = "calibration-faithful-v1"
EXPORT_DIR = REPO / "temp"


def _runs():
    """Newest screening run per model, keyed by OpenRouter id.

    Every screened model is sampled, registered or not: a screening survivor is
    exactly what the candidate route sends to Tier 2/3 next, and calibration
    measures the *judge*, so a wider spread of output styles makes the agreement
    number more robust rather than less representative.

    The `/` test drops runs recorded under a model's pre-OpenRouter identity,
    which would otherwise enter the sample a second time under its old name.
    Empty outputs are dropped in `sample` instead, where the text is in hand.
    """
    runs = stage1.discover_runs()
    return {m: r for m, r in sorted(runs.items()) if "/" in m}


def _outputs(experiment_id):
    """Dataset item id -> (summary text, trace id) for one experiment."""
    return {
        i["experimentItemId"]: (judge._text(i.get("output")), i["traceId"])  # noqa: SLF001
        for i in API.experiment_items(experiment_id, fields="core,io")
    }


def _sources():
    """Dataset item id -> source text."""
    client = Langfuse()
    return {i.id: judge._source_of(i.input) for i in client.get_dataset(SCREEN).items}  # noqa: SLF001


def sample():
    """Build the fixed calibration sample from the existing screening runs.

    Every dataset item appears exactly once, dealt round-robin across the
    models, so the set is stratified by model without any model dominating it.
    """
    runs = _runs()
    if not runs:
        sys.exit(
            "no screening runs in Langfuse's API window, which is the last 30 days; "
            "run `stage1.py run <model>` first",
        )
    models = sorted(runs)
    outputs = {m: _outputs(runs[m]["id"]) for m in models}
    sources = _sources()

    faithful = []
    for index, item_id in enumerate(sorted(sources)):
        model = models[index % len(models)]
        text, trace = outputs.get(model, {}).get(item_id, ("", None))
        if text and trace:
            faithful.append(
                {"item": item_id, "model": model, "summary": text, "trace": trace},
            )
    return faithful, sources


def cmd_sample():
    faithful, _ = sample()
    print(f"faithfulness: {len(faithful)} items")
    counts: dict[str, int] = {}
    for row in faithful:
        counts[row["model"]] = counts.get(row["model"], 0) + 1
    for model, n in sorted(counts.items()):
        print(f"  {model:28s} {n}")


def _post(path, body):
    response = requests.post(
        f"{API.base}/api/public/{path}",
        auth=API.auth,
        json=body,
        timeout=120,
    )
    if response.status_code not in (200, 201):
        msg = f"POST {path} -> {response.status_code}: {response.text[:300]}"
        raise RuntimeError(msg)
    return response.json()


def _root_observations(trace_ids, from_time):
    """Trace id -> its ROOT observation id (the one with no parent).

    **Annotate the root span, never the GENERATION inside it.** The root span's
    output is the clean summary, byte-identical to what the judge is given. The
    generation's output is the model's reply *as parts*, and a reasoning model
    puts a `thinking` part in front of the `text` one — so annotating it would
    show a different artefact than the judge scores and would expose reasoning
    the judge never sees. Both live in the same trace, which makes picking the
    wrong one easy and silent.
    """
    wanted = set(trace_ids)
    found = {}
    for row in API.paginate(
        "v2/observations",
        {"fields": "core", "fromStartTime": from_time, "limit": 100},
    ):
        if row["traceId"] in wanted and row.get("parentObservationId") is None:
            found.setdefault(row["traceId"], row["id"])
    return found


def _queue(score_config_ids):
    """Find or create the single annotation queue.

    The Hobby plan caps annotation queues at one, and no route updates a
    queue's score configs after creation. A config missing from an existing
    queue is simply not offered in the UI; this says so rather than letting the
    labeller discover it.
    """
    queues = {q["name"]: q for q in API.paginate("annotation-queues", {"limit": 100})}
    if QUEUE_NAME in queues:
        queue = queues[QUEUE_NAME]
        attached = set(queue.get("scoreConfigIds") or [])
        missing = [c for c in score_config_ids if c not in attached]
        print(f"  queue exists: {QUEUE_NAME}")
        if missing:
            # UI-only: the API has GET and POST on the queue collection and GET
            # alone on a single queue, so it can neither update a queue's
            # configs nor delete it. The UI can, and adding one there is
            # verified to take effect immediately with items and statuses
            # intact — no rebuild, and nothing labelled is at risk either way,
            # since a label is a score on an observation, not on the queue.
            print(
                f"  WARNING: {len(missing)} score config(s) not attached to it, "
                "so that channel is offered on no item at all. Add them in the "
                "queue's settings in the Langfuse UI, then re-run this. "
                "Existing items, statuses and labels are unaffected.",
            )
        return queue["id"]
    created = _post(
        "annotation-queues",
        {
            "name": QUEUE_NAME,
            "description": (
                "Judge calibration. Answer h_faithful: does the summary assert "
                "anything the source does not support?"
            ),
            "scoreConfigIds": score_config_ids,
        },
    )
    print(f"  created queue: {QUEUE_NAME}")
    return created["id"]


def _enqueue(queue_id, observation_ids):
    for observation in observation_ids:
        _post(
            f"annotation-queues/{queue_id}/items",
            {"objectId": observation, "objectType": "OBSERVATION"},
        )
    return len(observation_ids)


def setup():
    """Create the score configs and the queue, and queue the sample.

    Faithfulness annotates observations that already exist — the root span of
    each screening run item.
    """
    existing = {c["name"]: c for c in API.paginate("score-configs", {"limit": 100})}
    ids = {}

    def config(name, data_type, description):
        if name in existing:
            print(f"  score config exists: {name}")
            ids[name] = existing[name]["id"]
            return
        body = {"name": name, "dataType": data_type, "description": description}
        ids[name] = _post("score-configs", body)["id"]
        print(f"  created score config: {name}")

    config(
        H_FAITHFUL,
        "BOOLEAN",
        "Human: does every claim in the summary hold up against the source? "
        "False if the summary asserts anything the source does not support. "
        "Omission, translation and rewording are not unfaithfulness.",
    )
    config(
        C_FAITHFUL,
        "BOOLEAN",
        "Judge's binarised faithfulness verdict, for comparison against "
        f"{H_FAITHFUL}. Written by calibrate.py, not by hand.",
    )

    faithful, _ = sample()
    runs = _runs()
    from_time = min(r["startTime"] for r in runs.values())

    print()
    queue_id = _queue([ids[H_FAITHFUL]])
    queued = {
        i.get("objectId")
        for i in API.paginate(
            f"annotation-queues/{queue_id}/items",
            {"limit": 100},
        )
    }

    roots = _root_observations([r["trace"] for r in faithful], from_time)
    missing = [r["item"] for r in faithful if r["trace"] not in roots]
    if missing:
        print(f"  no root observation for {len(missing)} item(s) — skipped")
    fresh = [
        roots[r["trace"]]
        for r in faithful
        if r["trace"] in roots and roots[r["trace"]] not in queued
    ]
    print(
        f"  faithfulness: {_enqueue(queue_id, fresh)} queued, {len(faithful) - len(fresh)} already there",
    )

    print(f"\nLabel at {API.base} -> Human Annotation")


def _resume(model, rows):
    """Drop the sample items this pin has already banked a verdict for.

    A round is 25 calls and any one of them can fail outright, mid-round.
    OpenRouter reserves the *maximum possible* cost of a call against the
    remaining credit, so a balance that comfortably covers a whole round still
    refuses a single item carrying a full-size source — a 402 that says nothing
    about the item and everything about the reservation. The verdicts bought
    before that point are real and already banked, so re-running the round
    whole would pay for them a second time and leave two scores per item under
    one pin, which `agreement` resolves to whichever page arrived last.

    Editing the judge prompt moves the pin, which is what makes a genuine
    re-measurement possible: nothing is skipped when the pin is new.
    """
    if not rows:
        return rows
    pin = f"faithfulness@{judge.judge_version('faithfulness')}"
    done = set()
    for row in API.paginate(
        "v3/scores",
        {"limit": 100, "fields": "core,details", "name": C_FAITHFUL},
    ):
        meta = row.get("metadata") or {}
        if (meta.get("judge_model"), meta.get("judge_prompt")) != (model, pin):
            continue
        if item := meta.get("dataset_item_id"):
            done.add(item)
    remaining = [r for r in rows if r["item"] not in done]
    if skipped := len(rows) - len(remaining):
        print(f"{skipped} already banked under {pin}, skipping")
    return remaining


def run_judge(model=None):
    """Score the calibration sample with one judge. COSTS MONEY.

    `model` names a candidate judge to measure instead of the pinned one. The
    plan is explicit that calibration *supersedes* judge-model choice: run two,
    measure both against the same hand labels, take the higher number — and if
    the cheaper one clears the bar, spend the difference on dataset items
    instead. Both judges write the same score names and stay separable by the
    pin in their metadata, so running a second one never disturbs the first.
    """
    faithful, sources = sample()
    client = Langfuse()
    model = model or judge.JUDGE_MODEL
    faithful = _resume(model, faithful)
    spent = []
    refused = []

    def attempt(**fields):
        """One judge call, or `None` when the provider refused to answer.

        A round is 25 calls and the scores are only flushed at the end, so
        letting one refusal propagate discards every verdict bought before it.
        Opus returned `content_filter` on an ordinary summary about the Go
        language — nothing about the item predicts it, and a retry is not free —
        so the item is dropped, named at the end, and the round continues.
        """
        try:
            return judge.ask(model=model, **fields)
        except RuntimeError as exc:
            refused.append(str(exc))
            return None

    print(f"judge: {model}, effort {judge.JUDGE_EFFORT}")
    print(f"faithfulness: {len(faithful)} calls")
    for row in faithful:
        source = sources.get(row["item"], "")
        if not source:
            continue
        answer = attempt(
            name="faithfulness",
            source=source[:120000],
            summary=row["summary"],
        )
        if answer is None:
            print(f"  {row['item']}  refused")
            continue
        verdict, usage = answer
        spent.append(usage.get("cost") or 0)
        # The judge enumerates and the runner decides. Binarised here because the
        # human label is binary: a ratio cannot be hand-assigned reproducibly.
        # An item is unfaithful when it carries at least one *material* finding —
        # the same gate the hand labels were assigned under, which is what makes
        # the two sides answers to one question rather than two.
        material, comment = judge.faithfulness_verdict(verdict)
        clean = not material
        client.create_score(
            name=C_FAITHFUL,
            value=clean,
            data_type="BOOLEAN",
            comment=comment,
            trace_id=row["trace"],
            metadata={
                **judge.judge_meta("faithfulness", model),
                "candidate_model": row["model"],
                "dataset_item_id": row["item"],
            },
        )
        print(f"  {row['item']}  {'clean' if clean else 'UNSUPPORTED'}")

    client.flush()
    # OpenRouter prices each call, so this is what was actually charged rather
    # than an estimate against a price table that goes stale.
    total = sum(spent)
    priced = sum(1 for c in spent if c)
    print(f"\n{len(spent)} judge calls, ${total:.4f}", end="")
    print(f" ({priced} priced)" if priced != len(spent) else "")
    if refused:
        # A refusal is a missing item, not a verdict. Naming it keeps the count
        # in `agreement` honest — a silently dropped item reads as a judge that
        # scored fewer items than the sample holds, which is what a broken
        # runner also looks like.
        print(f"{len(refused)} call(s) refused, item(s) left unscored:")
        for message in refused:
            print(f"  {message}")
    print("scores posted; run `calibrate.py agreement`")


def _kappa(pairs_seen):
    """Cohen's kappa for a list of (human, judge) label pairs."""
    if not pairs_seen:
        return 0.0
    n = len(pairs_seen)
    observed = sum(1 for h, j in pairs_seen if h == j) / n
    labels_seen = {label for pair in pairs_seen for label in pair}
    expected = sum(
        (sum(1 for h, _ in pairs_seen if h == label) / n)
        * (sum(1 for _, j in pairs_seen if j == label) / n)
        for label in labels_seen
    )
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def _scores_by_name(names):
    """Score name -> judge pin -> {dataset item id: value}.

    Grouped by pin because measuring a second judge is the *point* — the plan
    says pick two, measure both against the same labels and take the higher
    number. Both write the same score names, so without this grouping the
    second run silently overwrites the first in whatever order the pages
    arrive, and the comparison it was run for is unreadable.

    The pin is model plus prompt hash, so iterating a judge prompt separates
    its verdicts from the ones banked before the edit for the same reason.
    """
    out: dict[str, dict[tuple, dict]] = {n: {} for n in names}
    rows = API.paginate(
        "v3/scores",
        {"limit": 100, "fields": "core,details", "name": ",".join(names)},
    )
    for row in rows:
        name = row.get("name")
        if name not in out:
            continue
        meta = row.get("metadata") or {}
        item = meta.get("dataset_item_id")
        if item:
            pin = (meta.get("judge_model") or "?", meta.get("judge_prompt") or "?")
            out[name].setdefault(pin, {})[item] = score_value(row)
    return out


def _human_scores(name, by_observation):
    """Dataset item id -> the human's label, read back from the queue.

    A label set in the annotation UI hangs off the observation and carries no
    metadata this code controls, so the item id has to come from the mapping
    that put the observation in the queue in the first place.

    **`subject` is its own `fields` group and has to be asked for.** Without it
    a score carries no target at all — not `observationId`, not `subject` — so
    every label maps to nothing and the report reads "0 labelled of 25", which
    is indistinguishable from nobody having labelled anything. That is what it
    said with 25 labels already saved.
    """
    out = {}
    for row in API.paginate(
        "v3/scores",
        {"limit": 100, "fields": "core,details,subject", "name": name},
    ):
        item = by_observation.get((row.get("subject") or {}).get("id"))
        if item:
            out[item] = score_value(row)
    return out


def _live_round():
    """The sample, the hand labels and the judges' verdicts, read from Langfuse."""
    faithful, _ = sample()
    runs = _runs()
    from_time = min(r["startTime"] for r in runs.values())
    roots = _root_observations([r["trace"] for r in faithful], from_time)
    human = _human_scores(
        H_FAITHFUL,
        {roots[r["trace"]]: r["item"] for r in faithful if r["trace"] in roots},
    )
    return faithful, human, _scores_by_name([C_FAITHFUL])[C_FAITHFUL]


def export(path=None):
    """Write the current round to a local file before it leaves the API window."""
    faithful, human, by_pin = _live_round()
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    path = Path(path) if path else EXPORT_DIR / f"calibration-{stamp}.json"
    payload = {
        "exported_at": stamp,
        "sample": faithful,
        "human": human,
        # JSON keys are strings, so the (model, prompt) pin is joined here and
        # split again on the way back in.
        "judged": {f"{m}|{p}": v for (m, p), v in by_pin.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"{len(human)} hand label(s), {len(by_pin)} judge pin(s), "
        f"{len(faithful)} sample item(s) -> {path}",
    )
    if not human:
        print("  WARNING: no hand labels in Langfuse — nothing worth keeping yet")


def _file_round(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    judged = {
        tuple(key.split("|", 1)): verdicts
        for key, verdicts in payload["judged"].items()
    }
    print(f"from {path} (exported {payload['exported_at']})")
    return payload["sample"], payload["human"], judged


def agreement(path=None):
    """Report judge-vs-human agreement and every disagreement."""
    faithful, human_faithful, by_pin = _file_round(path) if path else _live_round()

    # Two counts, not one. "Nothing to compare" with 25 hand labels banked and
    # no judge run is a completely different state from nobody having labelled
    # anything, and one number cannot tell them apart — it reads as lost work.
    print(
        f"\n=== faithfulness: {len(human_faithful)} hand-labelled of {len(faithful)} ===",
    )
    if not by_pin:
        print(
            "  no judge scores yet — run `calibrate.py judge [<model>]`"
            if human_faithful
            else "  neither side has run",
        )
        return
    for pin in sorted(by_pin):
        _report_judge(pin, human_faithful, by_pin[pin], faithful)


def _compare_rows(limit, author=None):
    """Every summary in the newest compare run per candidate, judged or not.

    A row carries the pinned judge's verdict (`t2_faithfulness`) and the score
    id, so its comment can be fetched for the items the two judges split. A run
    made with `judge.py run --no-judge` has neither, and its rows carry
    `reference: None` — they are there for hand labels, not for the pinned judge.
    """
    rows = []
    for candidate, run in sorted(stage2.discover_runs(stage2.COMPARE).items()):
        model = stage2._split(candidate)[0]  # noqa: SLF001
        if author and model != author:
            continue
        items = API.experiment_items(run["id"], fields="core,io,scores")
        for item in sorted(items, key=lambda i: i["experimentItemId"])[: limit or None]:
            score = next(
                (s for s in item.get("scores") or [] if s["name"] == "t2_faithfulness"),
                None,
            )
            summary = judge._text(item.get("output"))  # noqa: SLF001
            if not summary or summary.startswith("Error:"):
                continue
            source = json.loads(item["input"]).get("content", "")
            rows.append(
                {
                    "item": item["experimentItemId"],
                    "author": model,
                    "reference": None if score is None else score["value"] == 1,
                    "reference_score": score and score["id"],
                    "source": source,
                    "summary": summary,
                },
            )
    return rows


def _load_labels(path):
    """(item, author) -> the user's verdict, True for clean; unsure ones dropped."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        (r["item"], r["author"]): r["clean"] for r in rows if r["clean"] is not None
    }


def versus(model, limit=0, variant="batched", labels=None, author=None):
    """Re-judge the compare runs with another judge, against the pinned one. COSTS MONEY.

    Calibration proper needs hand labels, and the ones behind the recorded round
    have left the API window. This measures the cheaper question — does a
    candidate judge reach the pinned judge's verdicts on summaries that judge has
    already scored — at no cost beyond the candidate's own calls. The reference
    is 88% against hand labels, not ground truth.

    `labels` names a file of the user's own verdicts: only those summaries are
    judged, and the report adds agreement with the user beside agreement with
    the pinned judge — which on 2026-09-27 turned out to be the one that counts.

    Nothing is posted to Langfuse: the verdicts go to `temp/` beside the source
    text they were judged on, which is the user's own content.
    """
    if model != JEV_MODEL:  # a decisions model is absent from the chat catalog
        stage1._resolve([model])  # noqa: SLF001
    human = _load_labels(labels) if labels else None
    rows = _compare_rows(limit, author)
    if human is not None:
        rows = [r for r in rows if (r["item"], r["author"]) in human]
    label = f"{model} ({variant})" if model == JEV_MODEL else model
    print(f"judge {label} vs {judge.JUDGE_MODEL}: {len(rows)} summaries")

    def one(row):
        if model == JEV_MODEL:
            return _ask_jev(row, variant)
        try:
            verdict, usage = judge.ask(
                "faithfulness",
                model=model,
                source=row["source"][:120000],
                summary=row["summary"],
            )
        except (RuntimeError, OSError, json.JSONDecodeError, KeyError) as exc:
            return {**row, "error": str(exc)[:300]}
        material, comment = judge.faithfulness_verdict(verdict)
        return {
            **row,
            "clean": not material,
            "comment": comment,
            "cost": usage.get("cost") or 0,
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, rows))

    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    path = (
        EXPORT_DIR / f"versus-{label.replace('/', '_').replace(' ', '')}-{stamp}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    _report_versus(model, results, human)
    print(f"\nverdicts -> {path}")


def _ask_jev(row, variant):
    """JEV on one summary: the source as state, a question per bullet.

    JEV returns a probability per yes/no question and writes no text, and asked
    once whether a whole summary is faithful it ranked barely above chance
    (AUC 0.64). Finding one wrong claim among a dozen in a long source is a
    search, so each bullet becomes its own local decision and the runner takes
    the weakest one — the same split as the enumerating judge, where the model
    reports and the runner decides.

    The source is never truncated to fit JEV's context: a cut source would make
    every claim from its missing half look unsupported.
    """
    bullets = [
        line.lstrip("-*• ").strip()
        for line in row["summary"].splitlines()
        if line.strip()
    ]
    instructions, criteria, batched = JEV_VARIANTS[variant]
    questions = {
        f"b{i:02d}": {
            "type": "noul",
            "instructions": instructions.format(claim=bullet),
            "criteria": criteria,
        }
        for i, bullet in enumerate(bullets)
    }
    # Batched sends every bullet in one call; otherwise each bullet pays for
    # the whole source again, about twelve times the batched cost.
    calls = [questions] if batched else [{k: q} for k, q in questions.items()]
    answers, cost = {}, 0
    for batch in calls:
        body = {
            "model": JEV_MODEL,
            "state": {"source": row["source"]},
            "questions": batch,
        }
        try:
            payload = judge._post(f"{judge.BASE}/alpha/decisions", body, timeout=120)  # noqa: SLF001
        except urllib.error.HTTPError as exc:
            return {
                **row,
                "error": f"{exc.code}: {exc.read()[:300].decode(errors='replace')}",
            }
        except OSError as exc:
            return {**row, "error": str(exc)[:300]}
        answers |= {k: a["noul"] for k, a in payload["answers"].items()}
        cost += (payload.get("usage") or {}).get("cost") or 0
    probabilities = [answers[k] for k in questions]
    weakest = min(range(len(bullets)), key=probabilities.__getitem__)
    return {
        **row,
        "clean": probabilities[weakest] >= JEV_THRESHOLD,
        "probabilities": probabilities,
        "comment": f"weakest {probabilities[weakest]:.2f}: {bullets[weakest][:200]}",
        "cost": cost,
    }


def _auc(done):
    """Probability that a summary Opus passed scores above one it failed."""
    clean = [min(r["probabilities"]) for r in done if r["reference"]]
    flagged = [min(r["probabilities"]) for r in done if not r["reference"]]
    if not clean or not flagged:
        return float("nan")
    pairs = [(c > f) + 0.5 * (c == f) for c in clean for f in flagged]
    return sum(pairs) / len(pairs)


def _report_versus(model, results, human=None):
    """Misses and false alarms against the pinned judge and the user's labels.

    Split by author because the candidate judge may share a family with the
    models it is judging; leniency towards its own family shows up there first.
    """
    failed = [r for r in results if "error" in r]
    done = [r for r in results if "error" not in r]
    cost = sum(r["cost"] for r in done)
    print(f"\n{len(done)} judged, {len(failed)} failed, ${cost:.4f}")
    for r in failed:
        print(f"  FAILED  {r['item']}  ({r['author']}): {r['error']}")
    if human is not None:
        _report_human(model, done, human)
    scored = [r for r in done if r["reference"] is not None]
    if not scored:
        print(f"\nno {judge.JUDGE_MODEL} verdicts on these summaries (an unjudged run)")
        return
    print(f"\n--- against {judge.JUDGE_MODEL} ---")
    _report_reference(model, scored)


def _report_human(model, done, human):
    """Errors caught and false alarms against the user's labels, for both judges."""
    print("\n--- against the user's labels ---")
    judges = {model: lambda r: r["clean"], judge.JUDGE_MODEL: lambda r: r["reference"]}
    for name, clean in judges.items():
        rows = [r for r in done if clean(r) is not None]
        if not rows:
            continue
        errors = [r for r in rows if not human[r["item"], r["author"]]]
        caught = sum(1 for r in errors if not clean(r))
        alarms = sum(1 for r in rows if human[r["item"], r["author"]] and not clean(r))
        agree = sum(1 for r in rows if clean(r) == human[r["item"], r["author"]])
        print(
            f"  {name:28s} n={len(rows):3d}  caught {caught}/{len(errors)}  "
            f"false alarms {alarms}  agreement {agree / len(rows):.0%}",
        )


def _report_reference(model, done):
    """The comparison with the pinned judge, over rows it has scored."""
    if "probabilities" in done[0]:
        # The bar is judged at the threshold fixed before the run; the others
        # are shown for diagnosis and pick their best on the very data scored.
        print(f"\nAUC {_auc(done):.2f}; weakest-bullet threshold sweep:")
        for t in (0.5, 0.6, 0.7, 0.8, 0.9):
            caught = sum(
                1 for r in done if not r["reference"] and min(r["probabilities"]) < t
            )
            alarms = sum(
                1 for r in done if r["reference"] and min(r["probabilities"]) < t
            )
            print(f"  < {t:.1f}  caught {caught}  false alarms {alarms}")
    header = f"  {'author':24s} {'n':>3s} {'ref flags':>9s} {'caught':>7s} {'false alarm':>12s}"
    print(header)
    for author in [*sorted({r["author"] for r in done}), "all"]:
        mine = [r for r in done if author in ("all", r["author"])]
        flagged = [r for r in mine if not r["reference"]]
        caught = sum(1 for r in flagged if not r["clean"])
        alarms = sum(1 for r in mine if r["reference"] and not r["clean"])
        print(
            f"  {author:24s} {len(mine):3d} {len(flagged):9d} {caught:7d} {alarms:12d}",
        )

    flagged = [r for r in done if not r["reference"]]
    caught = sum(1 for r in flagged if not r["clean"])
    alarms = sum(1 for r in done if r["reference"] and not r["clean"])
    rate = caught / len(flagged) if flagged else 0.0
    ok = rate >= VERSUS_MIN_CATCH and alarms <= VERSUS_MAX_FALSE_ALARMS
    print(
        f"\n  catches {caught}/{len(flagged)} ({rate:.0%}), {alarms} false alarm(s): "
        f"{'MEETS' if ok else 'FAILS'} the bar "
        f"(>= {VERSUS_MIN_CATCH:.0%}, <= {VERSUS_MAX_FALSE_ALARMS})",
    )

    split = [r for r in done if r["reference"] != r["clean"]]
    reference_comments = API.score_comments([r["reference_score"] for r in split])
    for r in split:
        kind = "MISS" if r["reference"] is False else "FALSE ALARM"
        print(f"\n  {kind}  {r['item']}  ({r['author']})")
        print(
            f"    {judge.JUDGE_MODEL}: {reference_comments.get(r['reference_score'], '?')}",
        )
        print(f"    {model}: {r['comment']}")


def _report_judge(pin, human, judged, rows):
    """Agreement for one judge pin against the hand labels, and its misses."""
    model, prompt = pin
    shared = [
        (r["item"], human[r["item"]], judged[r["item"]])
        for r in rows
        if r["item"] in human and r["item"] in judged
    ]
    print(f"\n  {model}  [{prompt}]")
    print(f"    {len(shared)} comparable ({len(judged)} judged)")
    if not shared:
        print("    nothing to compare — label the queue in Langfuse")
        return
    pairs_seen = [(h, j) for _, h, j in shared]
    accuracy = sum(1 for h, j in pairs_seen if h == j) / len(pairs_seen)
    kappa = _kappa(pairs_seen)
    verdict = "PASS" if accuracy >= 0.80 and kappa > 0.6 else "NOT CALIBRATED"
    print(f"    agreement {accuracy:.0%}   kappa {kappa:.2f}   {verdict}")
    for item, h, j in shared:
        if h != j:
            print(f"      {item}  human={h}  judge={j}")


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "sample"
    if command == "sample":
        cmd_sample()
    elif command == "setup":
        setup()
    elif command == "judge":
        run_judge(args[1] if len(args) > 1 else None)
    elif command == "agreement":
        agreement(args[1] if len(args) > 1 else None)
    elif command == "export":
        export(args[1] if len(args) > 1 else None)
    elif command == "versus":
        parser = argparse.ArgumentParser(prog="calibrate.py versus")
        parser.add_argument("model")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--variant", default="batched", choices=JEV_VARIANTS)
        parser.add_argument("--labels", help="the user's verdicts; judge only those")
        parser.add_argument("--author", help="only summaries by this model")
        opts = parser.parse_args(args[1:])
        versus(opts.model, opts.limit, opts.variant, opts.labels, opts.author)
    else:
        sys.exit(f"unknown command: {command}")
