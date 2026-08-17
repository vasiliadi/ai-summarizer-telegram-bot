"""Screening stage: whether a model clears the deterministic checks at all.

Sweeps `summarization-screen-v1` at one fixed thinking level with no judge
calls, then tabulates the Tier 1 scores that Langfuse's `tier1-on-experiments`
rule attaches to each run. Screening only proves a model is not broken; the
ranking is Tier 2/3's job.

    python scripts/eval/stage1.py run <vendor/model> [<vendor/model> ...]
    python scripts/eval/stage1.py report
    python scripts/eval/stage1.py failures

**Models are named by their OpenRouter id and passed as arguments.** There is
no default list and the registry is not consulted: the point of screening is to
decide whether a model belongs in `config.MODEL_SPECS` at all, so requiring it
to already be there inverts the tool. Nor should a default list come back — the
set worth screening changes every time, and once the first pass over the
registry is done the normal invocation is a single new model. Every model — candidate or incumbent —
runs over the one OpenRouter route so results are comparable; the small
difference against a provider's own endpoint is accepted deliberately, so a
model the bot reaches natively is still screened over OpenRouter.

Never *derive* an OpenRouter id by prefixing a vendor name: the catalog carries
`:free` and `:batch` variants alongside the plain id, so a computed id can
silently select the wrong one. `run` validates every id against the catalog
before spending anything.

Summarising goes through `eval_client.LLM`, which reuses `llm.LLMClient` for
everything except model construction, so a run records cost (via
`OpenRouterCostReporter`) and applies the thinking level exactly as the bot
does. The compare stage summarises through the same client, which is what keeps
the two stages' cost and latency numbers comparable. Importing `config` is what
turns instrumentation on.
"""

from __future__ import annotations

import sys
import time
from textwrap import dedent

import _bootstrap
import requests
from langfuse import Langfuse
from langfuse_api import LangfuseAPI

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

from eval_client import THINKING_LEVEL, summarize

import config
from prompts import PROMPTS, prompt_version

SCREEN = "summarization-screen-v1"
PROMPT_KEY = "key_points_for_transcript"
RUN_PREFIX = "stage1 / "
PASS_THRESHOLD = 0.70
CATALOG_URL = "https://openrouter.ai/api/v1/models"

# The binary checks `t1_pass` ANDs. `t1_no_preamble`, `t1_no_artifacts` and
# `t1_bullet_purity` were removed from the evaluator; runs scored before that
# still carry them, so the report simply stops showing columns nothing emits.
CHECKS = (
    "t1_language_match",
    "t1_bullet_count",
)

# OpenRouter id -> the id `config.MODEL_SPECS` uses, where the two differ. Only
# Google does today: its native ids carry no vendor prefix. Recorded in run
# metadata so a screening result can be tied back to a production model without
# anyone having to know the mapping.
REGISTRY_ID = {"google/gemini-3.7-flash": "gemini-3.7-flash"}


def make_task(model_id):
    """Build the per-item task for one candidate model."""
    prompt = dedent(PROMPTS[PROMPT_KEY]).strip()

    async def task(*, item, **kwargs):  # noqa: ARG001
        text = (item.input or {}).get("content", "")
        language = (item.input or {}).get("target_language", "Russian")
        try:
            return await summarize(model_id, prompt, text, language)
        except Exception as exc:
            # An empty response raises AttributeError; provider errors land here
            # too. Both are screen failures for that item, not a reason to
            # abandon the sweep — Tier 1 books "" as a language failure.
            print(f"    {model_id}: {type(exc).__name__}: {str(exc)[:160]}")
            return ""

    return task


def _resolve(model_ids):
    """Check every id against OpenRouter's catalog, returning id -> display name.

    A typo or a wrongly guessed id would otherwise surface as a per-item error
    partway through a paid sweep. Exits rather than screening a model that does
    not exist, and names the `:free`/`:batch` siblings that a near-miss usually
    means.
    """
    catalog = requests.get(CATALOG_URL, timeout=60).json()["data"]
    names = {m["id"]: m.get("name") or m["id"] for m in catalog}
    unknown = [m for m in model_ids if m not in names]
    if unknown:
        for bad in unknown:
            stem = bad.split(":")[0]
            near = sorted(i for i in names if i.startswith(stem))
            hint = f" — did you mean {', '.join(near)}?" if near else ""
            print(f"unknown OpenRouter model: {bad}{hint}")
        sys.exit("nothing run")
    return {m: names[m] for m in model_ids}


def run(model_ids):
    """Sweep the given OpenRouter model ids over the screening dataset."""
    if not model_ids:
        sys.exit(
            "usage: stage1.py run <openrouter-model-id> [...]\n"
            "  ids are OpenRouter ids, e.g. vendor/model",
        )
    resolved = _resolve(model_ids)

    client = Langfuse()
    items = list(client.get_dataset(SCREEN).items)
    print(
        f"{len(items)} items x {len(model_ids)} models, {PROMPT_KEY}, "
        f"thinking={THINKING_LEVEL}",
    )

    for model_id in model_ids:
        registry_id = REGISTRY_ID.get(model_id)
        note = f", registered as {registry_id}" if registry_id else ""
        print(f"\n{model_id}  ({resolved[model_id]}{note})")
        started = time.monotonic()
        result = client.run_experiment(
            name=f"{RUN_PREFIX}{model_id}",
            data=items,
            task=make_task(model_id),
            max_concurrency=4,
            metadata={
                "stage": "screen",
                "candidate_model": model_id,
                # Present only for a model that is already in the registry, and
                # only spelled differently there.
                "registry_model_id": registry_id,
                "thinking_level": THINKING_LEVEL,
                # Distinct from the item's own prompt_key, which records the
                # strategy of the trace the item was harvested from. Tier 1
                # branches on this one.
                "run_prompt_key": PROMPT_KEY,
                "prompt_version": prompt_version(PROMPT_KEY),
            },
        )
        client.flush()
        if config.langfuse_client is not None:
            config.langfuse_client.flush()
        empty = sum(1 for r in result.item_results if not (r.output or "").strip())
        print(
            f"  {time.monotonic() - started:.0f}s, "
            f"{len(result.item_results)} items, {empty} empty",
        )


def discover_runs():
    """Map candidate model -> newest experiment for it, from Langfuse itself."""
    runs = {}
    # experiments() returns newest first, so the first hit per model wins.
    for row in API.experiments(API.dataset_id(SCREEN), name_prefix=RUN_PREFIX):
        model = (row["name"])[len(RUN_PREFIX) :].split(" - ")[0]
        runs.setdefault(model, row)
    return runs


def _item_scores(experiment):
    """Dataset item id -> {score name: value} for one experiment.

    `fields=scores` returns each item's scores inline, which is what replaced
    fetching every run item's trace and sweeping /v3/scores separately.
    """
    per_item = {}
    for item in API.experiment_items(experiment["id"], fields="core,scores"):
        per_item[item["experimentItemId"]] = {
            s["name"]: s.get("value")
            for s in (item.get("scores") or [])
            if s["name"].startswith("t1_")
        }
    return per_item


def report():  # noqa: C901
    """Tabulate Tier 1 pass rates per model and apply the elimination threshold."""
    runs = discover_runs()
    if not runs:
        sys.exit(f"no runs found with prefix {RUN_PREFIX!r}; run the sweep first")

    print(f"\nStage 1 - {SCREEN}, {PROMPT_KEY}, thinking={THINKING_LEVEL}")
    print(f"Elimination threshold: t1_pass < {PASS_THRESHOLD:.0%}\n")
    header = (
        f"{'model':28s} {'n':>3s} {'t1_pass':>8s} "
        + " ".join(f"{c.replace('t1_', ''):>10s}" for c in CHECKS)
        + f" {'compress':>9s}"
    )
    print(header)
    print("-" * len(header))

    verdicts, incomplete, stale, broken = {}, [], [], []
    for model, experiment in sorted(runs.items()):
        per_item = _item_scores(experiment)
        scored = [s for s in per_item.values() if s]
        if not scored or len(scored) != len(per_item):
            incomplete.append(f"{model}: {len(scored)} scored of {len(per_item)} items")
        if not scored:
            print(f"{model:28s}   0   (no scores)")
            continue
        comp = [s["t1_compression"] for s in scored if "t1_compression" in s]
        # Compression is output chars over source chars, so zero on every item
        # means every output was empty. That is what a run looks like when the
        # harness never reached the model, and scoring it 0% would eliminate a
        # model for the runner's failure — the same shape as the rate-limit
        # response that once fell through as an empty list.
        if comp and not any(comp):
            broken.append(model)
            print(f"{model:28s} {len(scored):3d}   (no output on any item)")
            continue
        rate = sum(1 for s in scored if s.get("t1_pass")) / len(scored)
        # `t1_pass` is the evaluator's own verdict at the time it ran, so a run
        # scored by an earlier version ANDs checks this report no longer shows.
        # Surface that rather than let the columns look self-contradictory.
        if any(
            s.get("t1_pass") != all(s.get(c) for c in CHECKS if c in s) for s in scored
        ):
            stale.append(model)
        cells = []
        for check in CHECKS:
            vals = [s[check] for s in scored if check in s]
            cells.append(
                f"{sum(1 for v in vals if v) / len(vals):10.0%}"
                if vals
                else f"{'-':>10s}",
            )
        comp_cell = f"{sum(comp) / len(comp):9.4f}" if comp else f"{'-':>9s}"
        print(
            f"{model:28s} {len(scored):3d} {rate:8.0%} "
            + " ".join(cells)
            + f" {comp_cell}",
        )
        verdicts[model] = rate

    print()
    if broken:
        print(
            "NO OUTPUT - these runs produced nothing on any item and carry no verdict:",
        )
        print(f"  {', '.join(broken)}")
        print(
            "      Suspect the runner before the models. Re-run; the newest "
            "experiment per model is what this reads.",
        )
        print()
    if incomplete:
        # Never let a partial read pass as a verdict.
        print("INCOMPLETE COVERAGE - rows above are not final:")
        for line in incomplete:
            print(f"  {line}")
        print()
    if stale:
        print(
            "NOTE: t1_pass was recorded by an earlier evaluator version for "
            f"{', '.join(stale)}",
        )
        print(
            "      It ANDs checks this report no longer shows, so it can be "
            "lower than the columns imply. Re-run to score under the current "
            "evaluator.",
        )
        print()
    survivors = [m for m, r in verdicts.items() if r >= PASS_THRESHOLD]
    dropped = [m for m, r in verdicts.items() if r < PASS_THRESHOLD]
    print(f"ADVANCE ({len(survivors)}): {', '.join(survivors) or 'none'}")
    print(f"DROP    ({len(dropped)}): {', '.join(dropped) or 'none'}")


def _collect_failures(runs, wanted):
    """Items failing any of `wanted`, plus the score ids to fetch comments for."""
    found, score_ids = [], []
    for model, experiment in sorted(runs.items()):
        for item in API.experiment_items(experiment["id"], fields="core,io,scores"):
            failed = [
                s
                for s in (item.get("scores") or [])
                if s["name"] in wanted and s.get("value") in (False, 0, 0.0)
            ]
            if failed:
                found.append((model, item, failed))
                score_ids.extend(s["id"] for s in failed)
    return found, score_ids


def failures(check_names=()):
    """Show every item that failed a given Tier 1 check, with its trace link.

    The pass rates say how often a model broke a rule; this says which item,
    what the evaluator saw, and where to open it. Defaults to the binary checks
    Tier 1 still emits; pass names to inspect others, including checks that only
    older runs carry.
    """
    wanted = tuple(check_names) or CHECKS
    runs = discover_runs()
    if not runs:
        sys.exit(f"no runs found with prefix {RUN_PREFIX!r}; run the sweep first")

    found, score_ids = _collect_failures(runs, wanted)
    comments = API.score_comments(score_ids) if score_ids else {}
    project = found[0][2][0].get("projectId") if found else None

    print(f"\nTier 1 failures for: {', '.join(wanted)}")
    print(f"{len(found)} failing item(s) across {len(runs)} runs\n")
    for model, item, failed in found:
        trace = item["traceId"]
        print(f"{model}  item {item['experimentItemId']}")
        for score in sorted(failed, key=lambda s: s["name"]):
            print(f"  {score['name']:20s} {comments.get(score['id'], '')}")
        output = (item.get("output") or "").strip()
        lines = [ln for ln in output.splitlines() if ln.strip()]
        if lines:
            print(f"  first line : {lines[0][:100]!r}")
            if len(lines) > 1:
                print(f"  last line  : {lines[-1][:100]!r}")
        print(f"  chars={len(output)}  lines={len(lines)}")
        if project:
            print(f"  {API.base}/project/{project}/traces/{trace}")
        print()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "report"
    if command == "run":
        run(sys.argv[2:])
    elif command == "report":
        report()
    elif command == "failures":
        failures(sys.argv[2:])
    else:
        sys.exit(f"unknown command: {command}")
