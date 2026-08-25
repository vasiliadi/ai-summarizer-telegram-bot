"""Key-facts checklists: the reference `t2_coverage` scores every summary against.

Coverage is the hard part of reference-free summarization, and this is what
converts it into a reference-based one without anyone writing a gold summary:
a strong model extracts the atomic facts a summary must not omit, a human edits
the list, and it is stored as the dataset item's `expected_output`. Every
experiment afterwards scores recall against it. The cost is paid once per
*item*, not once per run.

    uv run python scripts/eval/checklists.py status            # free
    uv run python scripts/eval/checklists.py generate [limit]  # COSTS MONEY: one call per item
    uv run python scripts/eval/checklists.py show <digest> [--full]  # free: source + facts, to review
    uv run python scripts/eval/checklists.py review            # free: one markdown file to edit
    uv run python scripts/eval/checklists.py apply             # free: reads that file back
    uv run python scripts/eval/checklists.py push [--all]      # free: writes expected_output

Generation writes to a working file under `temp/`, never straight to Langfuse.
The hand-review step in the middle is not optional decoration: `eval_coverage`
returns `None` while an item has no checklist, which is visibly missing data,
whereas a wrong checklist silently mis-scores **every model at once** and looks
like a result. `push` therefore sends only entries marked `"reviewed": true`
unless `--all` overrides it.

**Checklists are keyed by content digest, not by dataset item id.** The same
source sits in `summarization-compare-v1` as `cmp-<digest>` and in
`summarization-screen-v1` as `scr-<digest>`, so one reviewed list is written to
both items and the 25 shared sources are reviewed once rather than twice.

**A dataset item has no partial update.** `POST /dataset-items` upserts by id,
so writing `expected_output` means re-sending `input`, `metadata`,
`source_trace_id`, `source_observation_id` and `status` alongside it — omit one
and it is gone, with no way to restore it and no error to say so. `push` reads
each item, changes exactly one field, and verifies the write.

Facts are extracted **in the language of the source**, which is usually not the
summary's language. That is deliberate: the judge is explicitly told wording and
language need not match, while translating the checklist at build time would
bake a translation error into the reference everything downstream is measured
against.
"""

from __future__ import annotations

import json
import sys

import _bootstrap
from langfuse import Langfuse

REPO = _bootstrap.load()

import judge

COMPARE, SCREEN = judge.COMPARE_DATASET, judge.SCREEN_DATASET
WORKING_FILE = REPO / "temp" / "key_facts.json"

MIN_FACTS, MAX_FACTS = 5, 12
SOURCE_LIMIT = 120000


def _digest(item_id):
    """`cmp-8754ac89a43d` -> `8754ac89a43d`, the key both datasets share."""
    return item_id.split("-", 1)[1]


def _items(client, dataset_name):
    return list(client.get_dataset(dataset_name).items)


def _load():
    if not WORKING_FILE.exists():
        return {"generated_with": None, "items": {}}
    return json.loads(WORKING_FILE.read_text())


def _save(state):
    WORKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKING_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _seed(state, items):
    """Adopt any checklist already living in Langfuse.

    Makes the working file reconstructible after it is deleted, so hand-review
    survives in exactly one place — the dataset — rather than depending on a
    file under `temp/` that nothing backs up.
    """
    adopted = 0
    for item in items:
        key = _digest(item.id)
        facts = judge._facts_of(item.expected_output)  # noqa: SLF001
        if facts and key not in state["items"]:
            state["items"][key] = {
                "reviewed": True,
                "chars": len(item.input.get("content", "")),
                "stratum": (item.metadata or {}).get("stratum"),
                "key_facts": facts,
            }
            adopted += 1
    return adopted


def _check(facts):
    """Complaints about one generated list, as plain sentences."""
    out = []
    if not MIN_FACTS <= len(facts) <= MAX_FACTS:
        out.append(f"{len(facts)} facts, expected {MIN_FACTS}-{MAX_FACTS}")
    if any(not f.strip() for f in facts):
        out.append("contains a blank fact")
    # The prompt asks for flat statements; a model that numbers or bullets them
    # anyway puts that punctuation inside the fact the judge is asked to entail.
    marked = [f for f in facts if _is_marked(f)]
    if marked:
        out.append(f"{len(marked)} fact(s) carry a bullet or number")
    return out


def _is_marked(fact):
    head = fact.lstrip()
    if not head:
        return False
    return head[0] in "-*•–—" or head[:2].rstrip(".)").isdigit()


def status():
    """What exists locally, what exists in Langfuse, and what is still missing."""
    client = Langfuse()
    compare, screen = _items(client, COMPARE), _items(client, SCREEN)
    state = _load()
    local = state["items"]
    reviewed = [k for k, v in local.items() if v.get("reviewed")]
    in_langfuse = [i for i in compare if judge._facts_of(i.expected_output)]  # noqa: SLF001

    print(f"\nworking file: {WORKING_FILE}")
    print(f"  {'exists' if WORKING_FILE.exists() else 'not created yet'}")
    if state.get("generated_with"):
        print(f"  generated with {state['generated_with']}")
    print(f"\n{COMPARE}: {len(compare)} items, {len(in_langfuse)} carry a checklist")
    print(f"{SCREEN}: {len(screen)} items (digests are a subset of the above)")
    print(f"\nlocal checklists: {len(local)}  ({len(reviewed)} marked reviewed)")
    missing = [i for i in compare if _digest(i.id) not in local]
    print(f"still to generate: {len(missing)}")
    if missing:
        print(f"  ~{len(missing)} judge calls, one per item")
    unreviewed = [k for k in local if k not in reviewed]
    if unreviewed:
        print(f"awaiting review: {len(unreviewed)}")
        print(f"  `checklists.py show {unreviewed[0]}` to read one against its source")
    flagged = {k: _check(v["key_facts"]) for k, v in local.items()}
    flagged = {k: v for k, v in flagged.items() if v}
    if flagged:
        print(f"\n{len(flagged)} list(s) worth looking at first:")
        for key, complaints in sorted(flagged.items()):
            print(f"  {key}: {'; '.join(complaints)}")


def generate(limit=0):
    """Extract a checklist for every compare item that has none yet."""
    client = Langfuse()
    compare = _items(client, COMPARE)
    state = _load()
    adopted = _seed(state, compare)
    if adopted:
        print(f"adopted {adopted} checklist(s) already in Langfuse")

    version = f"key_facts@{judge.judge_version('key_facts')}"
    # A checklist generated under a different prompt is a different reference,
    # so the file records which one built it and refuses to mix two.
    if state.get("generated_with") not in (None, version) and state["items"]:
        sys.exit(
            f"working file was generated with {state['generated_with']}, "
            f"not {version}. Move {WORKING_FILE} aside and regenerate, or "
            f"restore the prompt.",
        )
    state["generated_with"] = version

    todo = [i for i in compare if _digest(i.id) not in state["items"]]
    todo = todo[: limit or None]
    print(f"{len(todo)} item(s) to generate, {judge.JUDGE_MODEL}, {version}\n")
    for index, item in enumerate(todo, 1):
        source = (item.input or {}).get("content", "")
        verdict, _ = judge.ask("key_facts", source=source[:SOURCE_LIMIT])
        facts = [f.strip() for f in verdict["key_facts"] if f.strip()]
        state["items"][_digest(item.id)] = {
            "reviewed": False,
            "chars": len(source),
            "stratum": (item.metadata or {}).get("stratum"),
            "key_facts": facts,
        }
        # Saved per item: a crash on item 40 must not throw away 39 paid calls.
        _save(state)
        complaints = _check(facts)
        note = f"  <- {'; '.join(complaints)}" if complaints else ""
        print(f"[{index}/{len(todo)}] {item.id}  {len(facts)} facts{note}")
    print(f"\nwritten to {WORKING_FILE}")
    print('Review each list, set "reviewed": true, then `checklists.py push`.')


def show(key, full=False):
    """Print one source next to its checklist, for the hand-review step.

    The default truncates to keep a 70k-character transcript from filling the
    terminal. `--full` prints all of it, for handing the source to something
    else: asked over a *truncated* source, a model reports the entries it
    cannot see as absent, which is indistinguishable from the generator having
    invented them and is wrong. Redirect it to a file.
    """
    state = _load()
    entry = state["items"].get(key)
    if not entry:
        sys.exit(f"no local checklist for {key!r}; run `generate` first")
    client = Langfuse()
    sources = {
        _digest(i.id): (i.input or {}).get("content", "")
        for i in _items(client, COMPARE)
    }
    source = sources.get(key, "")
    print(f"\n=== {key} | {entry.get('stratum')} | {entry['chars']} chars ===\n")
    limit = len(source) if full else 12000
    print(source[:limit])
    if len(source) > limit:
        print(f"\n[... {len(source) - limit} more chars — pass --full for all]")
    print(f"\n=== {len(entry['key_facts'])} facts ===\n")
    for index, fact in enumerate(entry["key_facts"], 1):
        print(f"{index:2d}. {fact}")
    for complaint in _check(entry["key_facts"]):
        print(f"\n  NOTE: {complaint}")
    # The next-step hint is for a person reading a terminal, and `--full` output
    # is not that: it goes to a file handed to another model. An imperative
    # sentence sitting in that file is an instruction something may act on, and
    # this one names a path and an edit to make there. The same shape as the
    # `## ` heading that once reattributed labels — content read as direction —
    # except the reader here can write to disk. Nothing imperative goes in.
    if not full:
        print(
            f'\nEdit {WORKING_FILE} under "{key}", then set its "reviewed" to true.',
        )


def _upsert(client, item, facts):
    """Re-send one dataset item with `expected_output` filled in.

    Every other field is carried across verbatim because the route is an upsert
    with no partial form — anything omitted is silently dropped.
    """
    client.create_dataset_item(
        dataset_name=item.dataset_name,
        id=item.id,
        input=item.input,
        expected_output={"key_facts": facts},
        metadata=item.metadata,
        source_trace_id=item.source_trace_id,
        source_observation_id=item.source_observation_id,
        status=item.status,
    )


REVIEW_FILE = REPO / "temp" / "checklist-review.md"
EXCERPT = 700
TAIL = 3

# The parser keys on these exact lines rather than on markdown structure. Facts
# are model-written prose and sources are raw transcripts, so any heading- or
# bullet-shaped anchor can be produced by the content itself — the same trap the
# pairwise labelling file hit, where a `## ` prefix reattributed verdicts to
# headings inside a summary. A digest heading is additionally only honoured when
# it names a checklist the working file already knows.
FACTS_OPEN, FACTS_CLOSE = "<!-- facts -->", "<!-- /facts -->"
REVIEWED_NO, REVIEWED_YES = "<!-- reviewed: no -->", "<!-- reviewed: yes -->"


def _flags(facts):
    """Why this checklist needs attention before the padding question."""
    out = []
    if len(facts) > MAX_FACTS:
        out.append(f"{len(facts)} facts over the cap of {MAX_FACTS} — cut it down")
    if len(facts) < MIN_FACTS:
        out.append(f"{len(facts)} facts, minimum is {MIN_FACTS}")
    marked = sum(1 for f in facts if _is_marked(f))
    if marked:
        out.append(f"{marked} fact(s) carry a bullet or number inside — strip it")
    return out


def review(client=None):
    """Write every checklist to one markdown file for the hand-review pass.

    The source is *not* inlined. Fifty sources run to 1.28M characters, so the
    file would be unreadable and the facts — the thing actually being edited —
    would be buried. A short excerpt orients, `show` prints the whole thing for
    the few that need it.

    Flagged checklists come first. The cap is read as a quota rather than a
    limit, so nearly every list arrives at exactly twelve and the real work is
    cutting the tail, not fixing the count; the last few facts are marked for
    that reason.
    """
    state = _load()
    if not state["items"]:
        sys.exit(f"nothing in {WORKING_FILE}; run `generate` first")

    client = client or Langfuse()
    sources = {
        _digest(i.id): (i.input or {}).get("content", "")
        for i in _items(client, COMPARE)
    }

    ordered = sorted(
        state["items"].items(),
        key=lambda kv: (not _flags(kv[1]["key_facts"]), kv[0]),
    )
    flagged = sum(1 for _, e in ordered if _flags(e["key_facts"]))

    out = [
        "# Checklist review",
        "",
        f"{len(ordered)} lists, {flagged} flagged and listed first.",
        "",
        "Delete a fact's line to drop it; edit in place to reword it. Only lines",
        f"between `{FACTS_OPEN}` and `{FACTS_CLOSE}` are facts.",
        "",
        f"Change `{REVIEWED_NO}` to `{REVIEWED_YES}` when a list is done — `apply`",
        "takes only those, so stopping part-way is safe.",
        "",
        f"`TAIL` marks the last {TAIL} facts. {MAX_FACTS} is a cap, not a target, and it",
        "is read as one: that is where the padding is.",
        "",
        "Then: `uv run python scripts/eval/checklists.py apply`",
        "",
    ]
    for key, entry in ordered:
        facts = entry["key_facts"]
        source = sources.get(key, "")
        out += [
            "---",
            "",
            f"## {key}",
            REVIEWED_NO,
            "",
            (
                f"{entry.get('stratum')} · source {entry['chars']} chars"
                f" · {len(facts)} facts"
            ),
        ]
        out += [f"⚠️ {f}" for f in _flags(facts)]
        out += [
            "",
            (
                "whole source to a file: `uv run python scripts/eval/checklists.py"
                f" show {key} --full > temp/src-{key}.md`"
            ),
            "",
            (
                "<details><summary>opening of the source — to recognise it, not to"
                " hand to a model</summary>"
            ),
            "",
            "> " + " ".join(source[:EXCERPT].split()) + "…",
            "",
            "</details>",
            "",
            FACTS_OPEN,
        ]
        for index, fact in enumerate(facts):
            tail = "  <!-- TAIL -->" if index >= len(facts) - TAIL else ""
            out.append(f"- {fact}{tail}")
        out += [FACTS_CLOSE, ""]

    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_FILE.write_text("\n".join(out) + "\n")
    print(f"{len(ordered)} checklist(s) written to {REVIEW_FILE}")
    print(f"{flagged} flagged, listed first")
    print("Edit, mark each finished list reviewed, then `checklists.py apply`.")


def apply_review():  # noqa: C901, PLR0912
    """Read the edited review file back into the working file.

    Only sections marked reviewed are taken, so a half-finished pass is safe to
    apply and resume. A section deleted outright is left alone rather than
    emptied — the file is an editing surface, not the record.
    """
    if not REVIEW_FILE.exists():
        sys.exit(f"{REVIEW_FILE} does not exist; run `review` first")
    state = _load()
    known = set(state["items"])

    edited, key, in_facts, reviewed, facts = {}, None, False, False, []

    def close():
        if key and reviewed:
            edited[key] = facts

    for raw in REVIEW_FILE.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## ") and line[3:].strip() in known:
            close()
            key, in_facts, reviewed, facts = line[3:].strip(), False, False, []
        elif line == REVIEWED_YES:
            reviewed = True
        elif line == FACTS_OPEN:
            in_facts = True
        elif line == FACTS_CLOSE:
            in_facts = False
        elif in_facts and line.startswith("- "):
            fact = line[2:].split("<!-- TAIL -->")[0].strip()
            if fact:
                facts.append(fact)
    close()

    if not edited:
        sys.exit(
            f"no list is marked {REVIEWED_YES} in {REVIEW_FILE}; nothing to apply",
        )

    changed = 0
    for key, facts in edited.items():
        entry = state["items"][key]
        if entry["key_facts"] != facts:
            changed += 1
        entry["key_facts"] = facts
        entry["reviewed"] = True
    _save(state)

    print(f"{len(edited)} list(s) marked reviewed, {changed} edited")
    for key, facts in sorted(edited.items()):
        complaints = _check(facts)
        if complaints:
            print(f"  {key}: {'; '.join(complaints)}")
    remaining = len(state["items"]) - sum(
        1 for e in state["items"].values() if e.get("reviewed")
    )
    print(f"{remaining} still awaiting review")
    print(f"written to {WORKING_FILE}; `checklists.py push` when done")


def push(include_unreviewed=False):  # noqa: C901, PLR0912
    """Write reviewed checklists onto both datasets' items, and verify."""
    client = Langfuse()
    state = _load()
    if not state["items"]:
        sys.exit(f"nothing in {WORKING_FILE}; run `generate` first")

    ready = {
        key: entry["key_facts"]
        for key, entry in state["items"].items()
        if entry.get("reviewed") or include_unreviewed
    }
    skipped = len(state["items"]) - len(ready)
    if not ready:
        sys.exit(
            f"no checklist is marked reviewed ({skipped} awaiting review). "
            "A wrong checklist mis-scores every model at once, so review them "
            "or pass --all deliberately.",
        )
    if include_unreviewed and skipped:
        print(f"WARNING: including {skipped} unreviewed checklist(s)")

    written = 0
    for dataset_name in (COMPARE, SCREEN):
        for item in _items(client, dataset_name):
            facts = ready.get(_digest(item.id))
            if facts:
                _upsert(client, item, facts)
                written += 1
        print(f"  {dataset_name}: wrote {written} so far")
    client.flush()

    # Read back rather than trust the write: the upsert is the one operation
    # here that can quietly destroy hand-curated data.
    bad = []
    for dataset_name in (COMPARE, SCREEN):
        for item in _items(client, dataset_name):
            facts = ready.get(_digest(item.id))
            if not facts:
                continue
            stored = judge._facts_of(item.expected_output)  # noqa: SLF001
            if stored != facts:
                bad.append(
                    f"{item.id}: {len(stored)} facts stored, expected {len(facts)}",
                )
            elif not (item.input or {}).get("content"):
                bad.append(f"{item.id}: input.content is gone")
    print(f"\n{written} item(s) written across both datasets, {skipped} skipped")
    if bad:
        print(f"{len(bad)} item(s) did not verify:")
        for line in bad:
            print(f"  {line}")
    else:
        print("verified: every written item reads back with its checklist and input")


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "status"
    if command == "status":
        status()
    elif command == "generate":
        generate(int(args[1]) if len(args) > 1 else 0)
    elif command == "show":
        show(args[1], full="--full" in args)
    elif command == "review":
        review()
    elif command == "apply":
        apply_review()
    elif command == "push":
        push(include_unreviewed="--all" in args)
    else:
        sys.exit(f"unknown command: {command}")
