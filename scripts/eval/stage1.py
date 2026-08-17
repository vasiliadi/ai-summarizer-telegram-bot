"""STG-138 §7 stage 1: screen the model registry on Tier 1 only.

Runs every registered model over `summarization-screen-v1` at one fixed
thinking level with no judge calls, then tabulates the Tier 1 scores that
Langfuse's `tier1-on-experiments` rule attaches to each run.

    python scripts/eval/stage1.py run
    python scripts/eval/stage1.py report

The task drives `llm.LLMClient`, the same path the bot uses, rather than
posting to a provider directly. That is what records the three things §7 asks
to track beside quality, none of which a hand-rolled HTTP call produces:

  * **cost** — `OpenRouterCostReporter` copies the charge OpenRouter reports
    onto `gen_ai.usage.cost`, the attribute Langfuse ingests. Langfuse cannot
    price a bare `provider/model` id, so without the wrapper a run shows
    tokens and no cost — or, with no generation span at all, `$0.00`.
  * **thinking level** — `build_settings` applies it; a raw HTTP call sends
    none, so "one fixed thinking level" silently becomes the provider default.
  * **provider routing** — `build_model` sends Gemini through `GoogleModel`
    natively instead of over OpenRouter.

Importing `config` is what turns instrumentation on: it loads `.env`, builds
the providers, and calls `Agent.instrument_all()` when the Langfuse keys exist.
"""

from __future__ import annotations

import sys
import time
from textwrap import dedent

import _bootstrap
from langfuse import Langfuse
from langfuse_api import LangfuseAPI

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

import config
from llm import LLMClient
from prompts import PROMPTS, prompt_version

SCREEN = "summarization-screen-v1"
PROMPT_KEY = "key_points_for_transcript"
THINKING_LEVEL = config.DEFAULT_THINKING_LEVEL
RUN_PREFIX = "stage1 / "
PASS_THRESHOLD = 0.70

CHECKS = (
    "t1_language_match",
    "t1_no_preamble",
    "t1_no_artifacts",
    "t1_bullet_count",
    "t1_bullet_purity",
)

_llm = LLMClient(
    client=config.gemini_client,
    openrouter_provider=config.openrouter_provider,
)


def make_task(model_id):
    """Build the per-item task for one candidate model."""
    prompt = dedent(PROMPTS[PROMPT_KEY]).strip()

    def task(*, item, **kwargs):  # noqa: ARG001
        text = (item.input or {}).get("content", "")
        language = (item.input or {}).get("target_language", "Russian")
        # Mirrors summarize_text: prompt and content as two parts, and a blank
        # text drops its part rather than sending an empty one.
        content = [prompt, text] if text.strip() else [prompt]
        try:
            return _llm.run(
                content=content,
                model_id=model_id,
                target_language=language,
                thinking_level=THINKING_LEVEL,
            )
        except Exception as exc:
            # An empty response raises AttributeError; provider errors land here
            # too. Both are screen failures for that item, not a reason to
            # abandon the sweep — Tier 1 books "" as a language failure.
            print(f"    {model_id}: {type(exc).__name__}: {str(exc)[:160]}")
            return ""

    return task


def run():
    """Sweep every registered model over the screening dataset."""
    client = Langfuse()
    items = list(client.get_dataset(SCREEN).items)
    models = list(config.MODEL_SPECS)
    print(
        f"{len(items)} items x {len(models)} models, {PROMPT_KEY}, "
        f"thinking={THINKING_LEVEL}",
    )

    for model_id in models:
        provider = config.MODEL_SPECS[model_id].provider
        print(f"\n{model_id}  (provider={provider})")
        started = time.monotonic()
        result = client.run_experiment(
            name=f"{RUN_PREFIX}{model_id}",
            data=items,
            task=make_task(model_id),
            max_concurrency=4,
            metadata={
                "stage": "stg-138-stage-1",
                "candidate_model": model_id,
                "provider": provider,
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


def _discover_runs():
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


def report():
    """Tabulate Tier 1 pass rates per model and apply the elimination threshold."""
    runs = _discover_runs()
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

    verdicts, incomplete = {}, []
    for model, experiment in sorted(runs.items()):
        per_item = _item_scores(experiment)
        scored = [s for s in per_item.values() if s]
        if not scored or len(scored) != len(per_item):
            incomplete.append(f"{model}: {len(scored)} scored of {len(per_item)} items")
        if not scored:
            print(f"{model:28s}   0   (no scores)")
            continue
        rate = sum(1 for s in scored if s.get("t1_pass")) / len(scored)
        cells = []
        for check in CHECKS:
            vals = [s[check] for s in scored if check in s]
            cells.append(
                f"{sum(1 for v in vals if v) / len(vals):10.0%}"
                if vals
                else f"{'-':>10s}",
            )
        comp = [s["t1_compression"] for s in scored if "t1_compression" in s]
        comp_cell = f"{sum(comp) / len(comp):9.4f}" if comp else f"{'-':>9s}"
        print(
            f"{model:28s} {len(scored):3d} {rate:8.0%} "
            + " ".join(cells)
            + f" {comp_cell}",
        )
        verdicts[model] = rate

    print()
    if incomplete:
        # Never let a partial read pass as a verdict.
        print("INCOMPLETE COVERAGE - rows above are not final:")
        for line in incomplete:
            print(f"  {line}")
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
    what the evaluator saw, and where to open it. Defaults to the three checks
    that catch prompt-obedience failures rather than outright breakage.
    """
    wanted = tuple(check_names) or (
        "t1_bullet_purity",
        "t1_no_preamble",
        "t1_no_artifacts",
    )
    runs = _discover_runs()
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
        run()
    elif command == "report":
        report()
    elif command == "failures":
        failures(sys.argv[2:])
    else:
        sys.exit(f"unknown command: {command}")
