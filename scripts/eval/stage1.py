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

import contextlib
import sys
import time
from textwrap import dedent

import _bootstrap
import requests
from langfuse import Langfuse

REPO = _bootstrap.load()
BASE, AUTH = _bootstrap.langfuse_rest()

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


def _get(url, params=None, attempts=8):
    """GET honouring Langfuse's rate limit.

    The limit is 30 requests per window and the 429 body carries
    `details.retryAfterSeconds`; obeying it is what makes this terminate, since
    blind backoff spends another request per retry. Failing loudly matters:
    an unchecked 429 falls through as an empty list and is indistinguishable
    from a model that scored nothing.
    """
    for attempt in range(attempts):
        response = requests.get(url, auth=AUTH, timeout=120, params=params)
        if response.status_code == 200:
            return response.json()
        retryable = response.status_code in {429, 500, 502, 503, 504}
        if retryable and attempt < attempts - 1:
            wait = 5.0
            with contextlib.suppress(ValueError, KeyError, TypeError):
                wait = float(response.json()["details"]["retryAfterSeconds"])
            time.sleep(wait + 1)
            continue
        msg = f"GET {url} -> HTTP {response.status_code}: {response.text[:200]}"
        raise RuntimeError(msg)
    msg = f"GET {url}: giving up after {attempts} attempts"
    raise RuntimeError(msg)


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
    """Map candidate model -> run name, from Langfuse rather than local state."""
    body = _get(
        f"{BASE}/api/public/experiments",
        params={"fromStartTime": "2020-01-01T00:00:00Z"},
    )
    runs = {}
    for row in body.get("data", []):
        name = row.get("name") or ""
        if not name.startswith(RUN_PREFIX):
            continue
        model = name[len(RUN_PREFIX) :].split(" - ")[0]
        # Several sweeps may exist; the newest run for a model wins.
        if model not in runs or row["startTime"] > runs[model][1]:
            runs[model] = (name, row["startTime"])
    return {model: name for model, (name, _) in runs.items()}


def _all_t1_scores():
    """Every t1_* score in the project, keyed by the trace it scored.

    One paginated sweep rather than a request per item: a per-item join over
    six 25-item runs is ~156 requests against a 30-per-window limit, which
    returned a different table on each run until it was replaced.
    """
    by_trace = {}
    cursor = None
    while True:
        params = {"source": "EVAL", "limit": 100, "fields": "core,details"}
        if cursor:
            params["cursor"] = cursor
        body = _get(f"{BASE}/api/public/v3/scores", params=params)
        rows = body.get("data", [])
        for row in rows:
            if not row["name"].startswith("t1_"):
                continue
            trace = (row.get("metadata") or {}).get("target_trace_id")
            if trace:
                by_trace.setdefault(trace, {})[row["name"]] = row.get("value")
        # Paginate on meta.cursor — meta.nextCursor does not exist and would
        # silently truncate the sweep at the first page.
        cursor = (body.get("meta") or {}).get("cursor")
        if not cursor or not rows:
            break
    return by_trace


def _run_traces(run_name):
    """Dataset item id -> trace id for one run."""
    from urllib.parse import quote

    run = _get(
        f"{BASE}/api/public/datasets/"
        f"{quote(SCREEN, safe='')}/runs/{quote(run_name, safe='')}",
    )
    return {
        row["datasetItemId"]: row["traceId"] for row in run.get("datasetRunItems", [])
    }


def report():
    """Tabulate Tier 1 pass rates per model and apply the elimination threshold."""
    runs = _discover_runs()
    if not runs:
        sys.exit(f"no runs found with prefix {RUN_PREFIX!r}; run the sweep first")
    all_scores = _all_t1_scores()

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
    for model, run_name in sorted(runs.items()):
        per_item = {
            item_id: all_scores.get(trace, {})
            for item_id, trace in _run_traces(run_name).items()
        }
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


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "report"
    if command == "run":
        run()
    elif command == "report":
        report()
    else:
        sys.exit(f"unknown command: {command}")
