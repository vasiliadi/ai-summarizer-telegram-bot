"""Judge calibration: measure the judge against hand labels before trusting it.

A judge is worth nothing until it agrees with a human. Nothing in a Tier 2/3
ranking means anything until this passes, so it runs *before* the compare stage
rather than after.

    uv run python scripts/eval/calibrate.py sample      # free: show the fixed sample
    uv run python scripts/eval/calibrate.py setup       # free: configs, queues, traces
    uv run python scripts/eval/calibrate.py judge [<model>] [<dimension>]  # COSTS MONEY
    uv run python scripts/eval/calibrate.py agreement   # free: accuracy + kappa

`judge` takes both arguments in either order; `<dimension>` is `faithfulness` or
`pairwise` and restricts the round to it. Prompts move one dimension at a time,
so naming one is the normal invocation — re-scoring the other pays to replace a
banked result whose prompt has not changed.

Calibration decides the judge model rather than assuming it. Run `judge` once
per candidate judge — the model id is an optional argument, defaulting to the
pinned `judge.JUDGE_MODEL` — and `agreement` reports every judge it finds side
by side against the same hand labels. Take the higher number, and if the
cheaper judge clears the bar, spend the difference on dataset items instead:
more items buy more statistical power than a better judge does.

The judge prompts and schemas are imported from `judge.py` and never restated.
Calibration has to measure the prompt production actually uses; a copy here
would drift and the agreement number would describe nothing.

Both dimensions are hand-labelled in Langfuse annotation queues, and one detail
decides whether that measurement means anything: **queue items point at the root
span, never at the GENERATION inside it.** A screening trace holds four
observations. The root span's output is the clean summary, byte-identical to
what the judge is given. The generation's output is the model's reply *as
parts*, and a reasoning model puts a `thinking` part in front of the `text` one
— annotate that and the human reads a different artefact than the judge scores,
and sees reasoning the judge never sees. Both sit in the same trace, so picking
the wrong one is easy and nothing complains.

Pairwise has no existing object to point at: a queue item is one object and the
comparison needs two summaries side by side, the same constraint that stopped
Tier 3 being an evaluator. `setup` therefore writes one purpose-built span per
pair, source as input and both summaries as output, blinded and carrying the
blinding in its metadata. They are free, named `calibration pair`, and hold the
only record of which model the labeller saw as A.

The sample is derived, not stored: items are sorted by id and dealt round-robin
across the screening runs, so re-running `sample` reproduces it exactly. That
matters because agreement is only comparable across prompt revisions when the
items stay fixed.
"""

from __future__ import annotations

import sys
from hashlib import sha256

import _bootstrap
import requests
from langfuse import Langfuse
from langfuse_api import EPOCH, LangfuseAPI, score_value

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

import judge
import stage1

SCREEN = stage1.SCREEN

# The duel worth calibrating on is the one that varies along the axis the spec
# is least sure of. These two sit close on length (compression 0.199 vs 0.176),
# so length — the part the pairwise prompt already handles explicitly — is held
# roughly fixed, and what separates them is how readable the Russian is. That is
# the criterion the prompt gained last and has never been measured on. Two
# models a reader rates equally would mostly produce TIE, which inflates chance
# agreement and collapses kappa.
PAIR_A = "minimax/minimax-m3"
PAIR_B = "thinkingmachines/inkling"

# Human channels vs judge channels. Distinct names, one score table — which is
# what keeps the comparison a query instead of a spreadsheet.
H_FAITHFUL, C_FAITHFUL = "h_faithful", "cal_faithful"
H_PAIRWISE, C_PAIRWISE = "h_pairwise", "cal_pairwise"

PAIRWISE_CATEGORIES = ("A", "B", "TIE")

# `judge` takes its arguments in either order: a token naming a dimension
# restricts the round to it, anything else is a candidate judge model.
DIMENSIONS = ("faithfulness", "pairwise")

# One queue holds both dimensions: the Hobby plan allows exactly one, and
# there is no API route to update a queue's score configs after creation.
QUEUE_NAME = "calibration-faithful-v1"
# Name given to the purpose-built pairwise annotation traces, and the only way
# to find them again — they carry the item id and the blinding in metadata.
PAIR_TRACE_NAME = "calibration pair"


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


def _flipped(item_id):
    """Whether this item shows `PAIR_B` in the left column.

    Which model sits in which column is randomised per item so the labeller
    cannot track a vendor across the file, and derived from the item id rather
    than drawn, so the layout reproduces exactly without a stored manifest — the
    same property the rest of the sample relies on.
    """
    return sha256(item_id.encode()).digest()[0] % 2 == 1


def sample():
    """Build the fixed calibration sample from the existing screening runs.

    Every dataset item appears exactly once for faithfulness, dealt round-robin
    across the models, so the set is stratified by model without any model
    dominating it. Pairwise uses the same items for one fixed model duel.
    """
    runs = _runs()
    models = sorted(runs)
    outputs = {m: _outputs(runs[m]["id"]) for m in models}
    sources = _sources()

    faithful, pairwise = [], []
    for index, item_id in enumerate(sorted(sources)):
        model = models[index % len(models)]
        text, trace = outputs.get(model, {}).get(item_id, ("", None))
        if text and trace:
            faithful.append(
                {"item": item_id, "model": model, "summary": text, "trace": trace},
            )
        a = outputs.get(PAIR_A, {}).get(item_id)
        b = outputs.get(PAIR_B, {}).get(item_id)
        if a and b and a[0] and b[0]:
            pairwise.append(
                {
                    "item": item_id,
                    "a": a[0],
                    "b": b[0],
                    "trace": a[1],
                    "flipped": _flipped(item_id),
                },
            )
    return faithful, pairwise, sources


def cmd_sample():
    faithful, pairwise, _ = sample()
    print(f"faithfulness: {len(faithful)} items")
    counts: dict[str, int] = {}
    for row in faithful:
        counts[row["model"]] = counts.get(row["model"], 0) + 1
    for model, n in sorted(counts.items()):
        print(f"  {model:28s} {n}")
    print(f"\npairwise: {len(pairwise)} pairs — A={PAIR_A}  B={PAIR_B}")


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


def _pair_observations():
    """Observation id -> its pairwise annotation trace's metadata.

    The purpose-built traces are found by name; each carries the dataset item
    and the blinding it was rendered with, which is the only record of which
    model the labeller saw as A.
    """
    found = {}
    for row in API.paginate(
        "v2/observations",
        {"fields": "core,metadata", "fromStartTime": EPOCH, "limit": 100},
    ):
        meta = row.get("metadata") or {}
        if meta.get("calibration") == PAIR_TRACE_NAME:
            found[row["id"]] = meta
    return found


def _queue(score_config_ids):
    """Find or create the single annotation queue.

    The Hobby plan caps annotation queues at one, and no route updates a
    queue's score configs after creation — so both dimensions share this queue
    and it has to be created with both configs attached. A queue that predates
    that carries only one, and the missing channel simply will not be offered
    in the UI; this says so rather than letting the labeller discover it.
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
                "Judge calibration. Two kinds of item share this queue, and "
                "they ask deliberately different questions. If Output holds one "
                "summary, answer h_faithful: does it assert anything the source "
                "does not support? If Output holds two under A and B, answer "
                "h_pairwise: which is better to READ — style, coherence, "
                "comprehensibility — ignoring factual errors, which h_faithful "
                "already covers. Leave the other channel empty."
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


def setup():  # noqa: C901, PLR0915
    """Create the score configs, the queue, and the pairwise annotation traces.

    Faithfulness annotates observations that already exist — the root span of
    each screening run item. Pairwise has nothing to point at: a queue item is
    one object and the comparison needs two summaries side by side, the same
    constraint that stopped Tier 3 being an evaluator. So one span per pair is
    written purpose-built, carrying the source as input and both summaries as
    output. They cost nothing and are named so they never read as bot traffic.
    """
    existing = {c["name"]: c for c in API.paginate("score-configs", {"limit": 100})}
    ids = {}

    def config(name, data_type, description, categories=None):
        if name in existing:
            print(f"  score config exists: {name}")
            ids[name] = existing[name]["id"]
            return
        body = {"name": name, "dataType": data_type, "description": description}
        if categories:
            body["categories"] = [
                {"label": c, "value": i} for i, c in enumerate(categories)
            ]
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
    config(
        H_PAIRWISE,
        "CATEGORICAL",
        "Human: which summary is better to READ, A or B as shown? Judge style, "
        "coherence and comprehensibility only. Ignore factual errors entirely — "
        f"accuracy is {H_FAITHFUL}'s question, and weighing it here counts the "
        "same defect twice. Blind — which model is which is randomised per item.",
        PAIRWISE_CATEGORIES,
    )
    config(
        C_PAIRWISE,
        "CATEGORICAL",
        f"Judge's pairwise verdict, for comparison against {H_PAIRWISE}.",
        PAIRWISE_CATEGORIES,
    )

    faithful, pairwise, sources = sample()
    runs = _runs()
    from_time = min(r["startTime"] for r in runs.values())

    print()
    queue_id = _queue([ids[H_FAITHFUL], ids[H_PAIRWISE]])
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

    pair_meta = _pair_observations()
    already = {
        m.get("dataset_item_id")
        for m in pair_meta.values()
        if m.get("run_a") == PAIR_A and m.get("run_b") == PAIR_B
    }
    # A trace built from a different duel answers a different question. Its
    # observation cannot be deleted, but it must leave the queue or it gets
    # labelled as though it belonged to this calibration.
    stale = {
        obs
        for obs, m in pair_meta.items()
        if m.get("run_a") != PAIR_A or m.get("run_b") != PAIR_B
    }
    if stale:
        removed = 0
        for item in API.paginate(
            f"annotation-queues/{queue_id}/items",
            {"limit": 100},
        ):
            if item.get("objectId") in stale:
                response = requests.delete(
                    f"{API.base}/api/public/annotation-queues/"
                    f"{queue_id}/items/{item['id']}",
                    auth=API.auth,
                    timeout=120,
                )
                removed += response.status_code in (200, 202, 204)
        print(f"  removed {removed} queue item(s) from a previous duel")
    client = Langfuse()
    created = []
    for row in pairwise:
        if row["item"] in already:
            continue
        left = row["b"] if row["flipped"] else row["a"]
        right = row["a"] if row["flipped"] else row["b"]
        span = client.start_observation(
            name=PAIR_TRACE_NAME,
            input={
                "content": sources.get(row["item"], ""),
                "target_language": "Russian",
            },
            output=f"## A\n\n{left}\n\n---\n\n## B\n\n{right}",
            metadata={
                # `calibration` is what `_pair_observations` matches on; the
                # rest is the only record of which model was shown as A.
                "calibration": PAIR_TRACE_NAME,
                "dataset_item_id": row["item"],
                "columns_flipped": row["flipped"],
                "run_a": PAIR_A,
                "run_b": PAIR_B,
            },
        )
        span.end()
        created.append(span.id)
    client.flush()
    # Enqueue every span for this duel that is not in the queue, not only the
    # ones just created. The two sets come apart exactly when the queue is
    # rebuilt to fix its score configs: the spans still exist, so nothing is
    # created, and queueing only `created` would leave the new queue with 25
    # faithfulness items and no pairwise ones — the very problem the rebuild
    # was meant to fix.
    existing_pairs = [
        obs
        for obs, m in pair_meta.items()
        if m.get("run_a") == PAIR_A and m.get("run_b") == PAIR_B and obs not in queued
    ]
    if created or existing_pairs:
        _enqueue(queue_id, created + existing_pairs)
    print(
        f"  pairwise: {len(created)} created, "
        f"{len(created) + len(existing_pairs)} queued, "
        f"{len(already) - len(existing_pairs)} already there",
    )

    print(f"\nLabel both at {API.base} -> Human Annotation")


def run_judge(model=None, only=None):  # noqa: C901, PLR0915
    """Score the calibration sample with one judge. COSTS MONEY.

    `model` names a candidate judge to measure instead of the pinned one. The
    plan is explicit that calibration *supersedes* judge-model choice: run two,
    measure both against the same hand labels, take the higher number — and if
    the cheaper one clears the bar, spend the difference on dataset items
    instead. Both judges write the same score names and stay separable by the
    pin in their metadata, so running a second one never disturbs the first.

    `only` restricts the round to one dimension. Prompts move one dimension at a
    time, so this is the normal case rather than an optimisation: the other
    dimension's banked round is still pinned to a prompt that has not changed,
    and re-running it would spend money replacing a measured result with a fresh
    sample of itself — severity near the boundary is unstable per run, so the
    replacement would not even be the same number.
    """
    faithful, pairwise, sources = sample()
    if only == "pairwise":
        faithful = []
    elif only == "faithfulness":
        pairwise = []
    client = Langfuse()
    model = model or judge.JUDGE_MODEL
    spent = []
    refused = []

    def attempt(**fields):
        """One judge call, or `None` when the provider refused to answer.

        A round is 75 calls and the scores are only flushed at the end, so
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

    print(f"\npairwise: {len(pairwise)} pairs x 2 orders")
    flip = {"A": "B", "B": "A", "TIE": "TIE"}
    for row in pairwise:
        source = sources.get(row["item"], "")[:120000]
        forward = attempt(
            name="pairwise",
            source=source,
            summary_a=row["a"],
            summary_b=row["b"],
        )
        backward = attempt(
            name="pairwise",
            source=source,
            summary_a=row["b"],
            summary_b=row["a"],
        )
        if forward is None or backward is None:
            print(f"  {row['item']}  refused")
            continue
        (ab, usage_ab), (ba, usage_ba) = forward, backward
        spent.extend([usage_ab.get("cost") or 0, usage_ba.get("cost") or 0])
        # Order-swap disagreement is position bias, not a verdict. Recording it
        # as INCONSISTENT keeps the discard rate visible instead of hiding it.
        consistent = ab["winner"] == flip[ba["winner"]]
        value = ab["winner"] if consistent else "INCONSISTENT"
        client.create_score(
            name=C_PAIRWISE,
            value=value,
            data_type="CATEGORICAL",
            comment=ab["reasoning"][:900],
            trace_id=row["trace"],
            metadata={
                **judge.judge_meta("pairwise", model),
                "run_a": PAIR_A,
                "run_b": PAIR_B,
                "dataset_item_id": row["item"],
                "order_ab": ab["winner"],
                "order_ba": ba["winner"],
            },
        )
        print(f"  {row['item']}  {value}")
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


def agreement():
    """Report judge-vs-human agreement and every disagreement."""
    faithful, pairwise, _ = sample()
    scores = _scores_by_name([C_FAITHFUL, C_PAIRWISE])

    runs = _runs()
    from_time = min(r["startTime"] for r in runs.values())
    roots = _root_observations([r["trace"] for r in faithful], from_time)
    human_faithful = _human_scores(
        H_FAITHFUL,
        {roots[r["trace"]]: r["item"] for r in faithful if r["trace"] in roots},
    )

    # Only this duel's spans. A previous duel's spans survive forever — nothing
    # in v4 deletes an observation — and they carry the same `dataset_item_id`,
    # so an unfiltered read maps a label about two *other* models onto this
    # comparison. `setup` already filters on `run_a`/`run_b` when it enqueues;
    # this is the same filter on the way back out.
    pair_meta = {
        obs: m
        for obs, m in _pair_observations().items()
        if m.get("run_a") == PAIR_A and m.get("run_b") == PAIR_B
    }
    flipped = {
        m["dataset_item_id"]: m.get("columns_flipped") for m in pair_meta.values()
    }
    shown = _human_scores(
        H_PAIRWISE,
        {obs: m["dataset_item_id"] for obs, m in pair_meta.items()},
    )
    # The queue is blind: its A is whichever model `_flipped` put first. Store
    # the comparison canonically, A always meaning PAIR_A, so a human label and
    # a judge label are the same kind of statement.
    unflip = {"A": "B", "B": "A", "TIE": "TIE"}
    human_pairwise = {
        item: (unflip[v] if flipped.get(item) and v in unflip else v)
        for item, v in shown.items()
    }

    for title, human, by_pin, rows in (
        ("faithfulness", human_faithful, scores[C_FAITHFUL], faithful),
        ("pairwise", human_pairwise, scores[C_PAIRWISE], pairwise),
    ):
        # Two counts, not one. "Nothing to compare" with 25 hand labels banked
        # and no judge run is a completely different state from nobody having
        # labelled anything, and one number cannot tell them apart — it reads
        # as lost work.
        print(f"\n=== {title}: {len(human)} hand-labelled of {len(rows)} ===")
        if not by_pin:
            print(
                "  no judge scores yet — run `calibrate.py judge [<model>]`"
                if human
                else "  neither side has run",
            )
            continue
        for pin in sorted(by_pin):
            _report_judge(pin, human, by_pin[pin], rows)


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
    # An INCONSISTENT pairwise verdict is the judge abstaining, not
    # disagreeing: the two orders contradicted each other, so it has no
    # opinion to compare. Production discards those, and counting them
    # against the judge here would understate agreement while conflating
    # position bias with error. The discard rate is reported instead — it is
    # its own signal about judge quality.
    abstained = [(i, h) for i, h, j in shared if j == "INCONSISTENT"]
    if abstained:
        print(
            f"    {len(abstained)} inconsistent "
            f"({len(abstained) / len(shared):.0%}) — excluded",
        )
    shared = [(i, h, j) for i, h, j in shared if j != "INCONSISTENT"]
    if not shared:
        print("    every verdict was inconsistent; nothing to compare")
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
        rest = args[1:]
        dimension = next((a for a in rest if a in DIMENSIONS), None)
        run_judge(next((a for a in rest if a not in DIMENSIONS), None), dimension)
    elif command == "agreement":
        agreement()
    else:
        sys.exit(f"unknown command: {command}")
