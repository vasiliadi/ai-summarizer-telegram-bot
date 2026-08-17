"""Judge calibration: measure the judge against hand labels before trusting it.

A judge is worth nothing until it agrees with a human. Nothing in a Tier 2/3
ranking means anything until this passes, so it runs *before* the compare stage
rather than after.

    python scripts/eval/calibrate.py sample      # free: show the fixed sample
    python scripts/eval/calibrate.py setup       # free: score configs + queue
    python scripts/eval/calibrate.py pairs       # free: side-by-side to label
    python scripts/eval/calibrate.py labels <md> # free: ingest pairwise labels
    python scripts/eval/calibrate.py judge       # COSTS MONEY
    python scripts/eval/calibrate.py agreement   # free: accuracy + kappa

The judge prompts and schemas are imported from `judge.py` and never restated.
Calibration has to measure the prompt production actually uses; a copy here
would drift and the agreement number would describe nothing.

**Two label channels, because a queue item is one object.** Faithfulness is a
per-summary judgement, so it goes through a Langfuse annotation queue and the
labels land in the same score table as everything else. Pairwise needs two
summaries side by side, which no single queue item can show — the same
constraint that stopped Tier 3 being an evaluator — so it is labelled in a
generated markdown file and ingested with `labels`.

Queue items point at the **generation observation**, not the trace. Trace-level
input/output is deprecated and nothing in this project sets it, so a TRACE item
would open empty in the annotation UI.

The sample is derived, not stored: items are sorted by id and dealt round-robin
across the screening runs, so re-running `sample` reproduces it exactly. That
matters because agreement is only comparable across prompt revisions when the
items stay fixed.
"""

from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path

import _bootstrap
import requests
from langfuse import Langfuse
from langfuse_api import LangfuseAPI

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

import judge
import stage1

SCREEN = stage1.SCREEN
QUEUE_NAME = "calibration-faithfulness-v1"

# The pairwise duel worth calibrating on: Tier 1 cannot tell these two apart,
# while one costs several times the other, so this is the comparison a ranking
# would actually have to get right.
PAIR_A = "openai/gpt-5.6-luna"
PAIR_B = "meta/muse-spark-1.2"

# Human channels vs judge channels. Distinct names, one score table — which is
# what keeps the comparison a query instead of a spreadsheet.
H_FAITHFUL, C_FAITHFUL = "h_faithful", "cal_faithful"
H_PAIRWISE, C_PAIRWISE = "h_pairwise", "cal_pairwise"

PAIRWISE_CATEGORIES = ("A", "B", "TIE")
LABELS_FILE = REPO / "docs" / "summaries" / "calibration-pairwise.md"


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


def _observation_ids(trace_ids):
    """Trace id -> its generation observation id.

    A queue item must point at the observation: trace-level input/output is
    deprecated and unset here, so a TRACE item shows the annotator nothing.
    """
    wanted = set(trace_ids)
    found = {}
    rows = API.paginate(
        "v2/observations",
        {
            "type": "GENERATION",
            "fields": "core",
            "fromStartTime": "2026-08-17T00:00:00Z",
            "limit": 100,
        },
    )
    for row in rows:
        if row["traceId"] in wanted:
            found.setdefault(row["traceId"], row["id"])
    return found


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


def setup():
    """Create the score configs and the faithfulness annotation queue."""
    existing = {c["name"]: c for c in API.paginate("score-configs", {"limit": 100})}

    def config(name, data_type, description, categories=None):
        if name in existing:
            print(f"  score config exists: {name}")
            return existing[name]["id"]
        body = {"name": name, "dataType": data_type, "description": description}
        if categories:
            body["categories"] = [
                {"label": c, "value": i} for i, c in enumerate(categories)
            ]
        created = _post("score-configs", body)
        print(f"  created score config: {name}")
        return created["id"]

    human_id = config(
        H_FAITHFUL,
        "BOOLEAN",
        "Human: does every claim in the summary hold up against the source? "
        "False if the summary asserts anything the source does not support. "
        "Omission is not unfaithfulness.",
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
        "Human: which summary serves a reader better?",
        PAIRWISE_CATEGORIES,
    )
    config(
        C_PAIRWISE,
        "CATEGORICAL",
        f"Judge's pairwise verdict, for comparison against {H_PAIRWISE}.",
        PAIRWISE_CATEGORIES,
    )

    queues = {q["name"]: q for q in API.paginate("annotation-queues", {"limit": 100})}
    if QUEUE_NAME in queues:
        queue_id = queues[QUEUE_NAME]["id"]
        print(f"  queue exists: {QUEUE_NAME}")
    else:
        queue_id = _post(
            "annotation-queues",
            {
                "name": QUEUE_NAME,
                "description": (
                    "Hand labels for judge calibration. One generation per item: "
                    "read the source and the summary, then set h_faithful."
                ),
                "scoreConfigIds": [human_id],
            },
        )["id"]
        print(f"  created queue: {QUEUE_NAME}")

    faithful, _, _ = sample()
    obs = _observation_ids([r["trace"] for r in faithful])
    added = 0
    for row in faithful:
        observation = obs.get(row["trace"])
        if not observation:
            print(f"  no generation found for item {row['item']} — skipped")
            continue
        _post(
            f"annotation-queues/{queue_id}/items",
            {"objectId": observation, "objectType": "OBSERVATION"},
        )
        added += 1
    print(f"\n{added} items queued in {QUEUE_NAME}")
    print(f"Label them at {API.base} -> Annotation Queues -> {QUEUE_NAME}")


def pairs():
    """Write the side-by-side markdown for hand-labelling the pairwise duel."""
    _, pairwise, sources = sample()
    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Pairwise calibration labels",
        "",
        "**Blind.** Two models are compared across these items, and which one is",
        "shown as A is randomised per item. Nothing here says which is which, on",
        "purpose: these labels become the standard the judge is measured against,",
        "so a preference for a vendor would be baked into the target itself.",
        "",
        "For each item write `A`, `B` or `TIE` on the **verdict** line. Judge",
        "faithfulness first, then how much substance survives, then whether every",
        "sentence earns its place. Length is not quality. Use TIE only when",
        "neither is meaningfully better, not to avoid a hard call.",
        "",
        (
            "Then: `uv run python scripts/eval/calibrate.py labels "
            f"{LABELS_FILE.relative_to(REPO)}`"
        ),
        "",
        "---",
        "",
    ]
    for row in pairwise:
        source = sources.get(row["item"], "")
        lines += [
            f"## {row['item']}",
            "",
            f"<details><summary>source ({len(source):,} chars)</summary>",
            "",
            "```",
            source[:8000],
            "```",
            "",
            "</details>",
            "",
            "### A",
            "",
            row["b"] if row["flipped"] else row["a"],
            "",
            "### B",
            "",
            row["a"] if row["flipped"] else row["b"],
            "",
            "verdict: ",
            "",
            "---",
            "",
        ]
    LABELS_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(pairwise)} pairs written to {LABELS_FILE}")
    print("Fill in every `verdict:` line, then run `calibrate.py labels`.")


def labels(path):
    """Ingest hand-written pairwise verdicts and post them as scores."""
    _, pairwise, _ = sample()
    traces = {r["item"]: r["trace"] for r in pairwise}
    flipped = {r["item"]: r["flipped"] for r in pairwise}

    text = Path(path).read_text(encoding="utf-8")
    verdicts, item = {}, None
    for line in text.splitlines():
        # Only a heading naming a known item starts a new block. The summaries
        # being labelled are themselves markdown and do contain `## ` headings,
        # so matching the prefix alone would silently reattribute a verdict to a
        # heading the model wrote — and a dropped label looks like an unlabelled
        # item rather than an error.
        if line.startswith("## ") and line[3:].strip() in traces:
            item = line[3:].strip()
        elif line.startswith("verdict:") and item:
            value = line[len("verdict:") :].strip().upper()
            if value in PAIRWISE_CATEGORIES:
                verdicts[item] = value
            elif value:
                print(f"  {item}: unrecognised verdict {value!r} — skipped")
            item = None
    missing = [r["item"] for r in pairwise if r["item"] not in verdicts]
    if missing:
        print(f"{len(missing)} pair(s) still unlabelled: {', '.join(missing[:5])}")
        if len(missing) == len(pairwise):
            sys.exit("nothing to post")

    # The file is blind: its A is whichever model `_flipped` put on the left.
    # Verdicts are stored canonically, A meaning PAIR_A always, so a human label
    # and a judge label are the same kind of statement and can be compared.
    unflip = {"A": "B", "B": "A", "TIE": "TIE"}
    client = Langfuse()
    for item_id, shown in verdicts.items():
        if item_id not in traces:
            continue
        value = unflip[shown] if flipped[item_id] else shown
        client.create_score(
            name=H_PAIRWISE,
            value=value,
            data_type="CATEGORICAL",
            trace_id=traces[item_id],
            metadata={
                "run_a": PAIR_A,
                "run_b": PAIR_B,
                "dataset_item_id": item_id,
                "shown_as": shown,
                "columns_flipped": flipped[item_id],
            },
        )
    client.flush()
    print(f"posted {len(verdicts)} human pairwise label(s)")


def run_judge():
    """Score the calibration sample with the judge. COSTS MONEY."""
    faithful, pairwise, sources = sample()
    client = Langfuse()

    print(f"faithfulness: {len(faithful)} calls")
    for row in faithful:
        source = sources.get(row["item"], "")
        if not source:
            continue
        verdict, _ = judge.ask(
            "faithfulness",
            source=source[:120000],
            summary=row["summary"],
        )
        # The judge counts and the runner decides. Binarised here because the
        # human label is binary: a ratio cannot be hand-assigned reproducibly.
        clean = verdict["unsupported_claims"] == 0
        client.create_score(
            name=C_FAITHFUL,
            value=clean,
            data_type="BOOLEAN",
            comment=(
                f"{verdict['unsupported_claims']}/{verdict['total_claims']} "
                f"unsupported. {verdict['reasoning']}"
            )[:900],
            trace_id=row["trace"],
            metadata={
                **judge.judge_meta("faithfulness"),
                "candidate_model": row["model"],
                "dataset_item_id": row["item"],
            },
        )
        print(f"  {row['item']}  {'clean' if clean else 'UNSUPPORTED'}")

    print(f"\npairwise: {len(pairwise)} pairs x 2 orders")
    flip = {"A": "B", "B": "A", "TIE": "TIE"}
    for row in pairwise:
        source = sources.get(row["item"], "")[:120000]
        ab, _ = judge.ask(
            "pairwise",
            source=source,
            summary_a=row["a"],
            summary_b=row["b"],
        )
        ba, _ = judge.ask(
            "pairwise",
            source=source,
            summary_a=row["b"],
            summary_b=row["a"],
        )
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
                **judge.judge_meta("pairwise"),
                "run_a": PAIR_A,
                "run_b": PAIR_B,
                "dataset_item_id": row["item"],
                "order_ab": ab["winner"],
                "order_ba": ba["winner"],
            },
        )
        print(f"  {row['item']}  {value}")
    client.flush()
    print("\nscores posted; run `calibrate.py agreement`")


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
    """Score name -> {dataset item id: value}, read back from Langfuse."""
    out: dict[str, dict[str, str]] = {n: {} for n in names}
    rows = API.paginate(
        "v3/scores",
        {"limit": 100, "fields": "core,details", "name": ",".join(names)},
    )
    for row in rows:
        name = row.get("name")
        if name not in out:
            continue
        item = (row.get("metadata") or {}).get("dataset_item_id")
        if item:
            out[name][item] = row.get("value")
    return out


def agreement():
    """Report judge-vs-human agreement and every disagreement."""
    faithful, pairwise, _ = sample()
    obs = _observation_ids([r["trace"] for r in faithful])
    by_observation = {obs.get(r["trace"]): r["item"] for r in faithful}
    scores = _scores_by_name([H_FAITHFUL, C_FAITHFUL, H_PAIRWISE, C_PAIRWISE])

    # Queue annotations attach to the observation, so they carry no
    # dataset_item_id metadata — map them back through the observation id.
    human_faithful = {}
    for row in API.paginate(
        "v3/scores",
        {"limit": 100, "fields": "core,details", "name": H_FAITHFUL},
    ):
        item = by_observation.get(row.get("observationId"))
        if item:
            human_faithful[item] = row.get("value")

    for title, human, judged, rows in (
        ("faithfulness", human_faithful, scores[C_FAITHFUL], faithful),
        ("pairwise", scores[H_PAIRWISE], scores[C_PAIRWISE], pairwise),
    ):
        shared = [
            (r["item"], human[r["item"]], judged[r["item"]])
            for r in rows
            if r["item"] in human and r["item"] in judged
        ]
        print(f"\n{title}: {len(shared)} labelled of {len(rows)}")
        if not shared:
            print("  nothing to compare yet")
            continue
        # An INCONSISTENT pairwise verdict is the judge abstaining, not
        # disagreeing: the two orders contradicted each other, so it has no
        # opinion to compare. Production discards those, and counting them
        # against the judge here would understate agreement while conflating
        # position bias with error. The discard rate is reported instead — it is
        # its own signal about judge quality.
        abstained = [(i, h) for i, h, j in shared if j == "INCONSISTENT"]
        if abstained:
            rate = len(abstained) / len(shared)
            print(f"  {len(abstained)} inconsistent ({rate:.0%}) — excluded")
        shared = [(i, h, j) for i, h, j in shared if j != "INCONSISTENT"]
        if not shared:
            print("  every verdict was inconsistent; nothing to compare")
            continue
        pairs_seen = [(h, j) for _, h, j in shared]
        accuracy = sum(1 for h, j in pairs_seen if h == j) / len(pairs_seen)
        kappa = _kappa(pairs_seen)
        verdict = "PASS" if accuracy >= 0.80 and kappa > 0.6 else "NOT CALIBRATED"
        print(f"  agreement {accuracy:.0%}   kappa {kappa:.2f}   {verdict}")
        for item, h, j in shared:
            if h != j:
                print(f"    {item}  human={h}  judge={j}")


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "sample"
    if command == "sample":
        cmd_sample()
    elif command == "setup":
        setup()
    elif command == "pairs":
        pairs()
    elif command == "labels":
        labels(args[1] if len(args) > 1 else LABELS_FILE)
    elif command == "judge":
        run_judge()
    elif command == "agreement":
        agreement()
    else:
        sys.exit(f"unknown command: {command}")
