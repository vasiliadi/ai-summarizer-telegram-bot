"""Tier 2 / Tier 3 LLM judge.

Runs outside Langfuse. Tier 3 has to: an evaluator sees one item and has no
mapping source for a second run's output, so pairwise comparison cannot be an
evaluator at all. Tier 2 could move but stays here — see `docs/context/evals.md`
for what moving it would cost.

Tier 2 plugs into `Langfuse.run_experiment` as evaluator functions, so scores
attach to the run automatically. Tier 3 compares two runs and posts its own
scores.

Two model callers live here and only one of them is the bot's. The **candidate**
summarises through `eval_client.LLM`, the same path screening takes, so a
compare run records cost and applies the thinking level — quality alone always
picks the most expensive configuration, so the price has to arrive beside the
score. The **judge** keeps its own HTTP call: it needs a forced tool call
against a JSON schema, which `LLMClient` does not do and the bot never asks for,
and what it spends is a cost of running the evaluation rather than a property of
the model being ranked.

The judge is synchronous and returns structured output through a forced tool
call; its model is the `JUDGE_MODEL` constant below, chosen so that no
candidate shares its family. It **counts** (claims, entailed facts) and
the ratio is computed here, because a model asked directly for `0.71` makes
arithmetic slips no prompt wording fixes. Editing a judge prompt or schema moves
its `judge_version` hash, which unpins it from every score already banked.

    python judge.py run <vendor/model> 2
    python judge.py pairwise <run-a> <run-b>
    python judge.py smoke 3
"""

import json
import os
import sys
import urllib.error
import urllib.request
from hashlib import sha256
from textwrap import dedent

import _bootstrap
from langfuse import Langfuse
from langfuse.experiment import Evaluation
from langfuse_api import LangfuseAPI

REPO = _bootstrap.load()
API = LangfuseAPI(*_bootstrap.langfuse_rest())

from eval_client import LLM, THINKING_LEVEL

import config
from prompts import PROMPTS, prompt_version

BASE = "https://openrouter.ai/api"
CHAT_URL = f"{BASE}/v1/chat/completions"

JUDGE_MODEL = "anthropic/claude-sonnet-5"
JUDGE_EFFORT = "medium"  # pins depth; Sonnet 5 rejects temperature outright

COMPARE_DATASET = "summarization-compare-v1"
SCREEN_DATASET = "summarization-screen-v1"

FAITHFULNESS = """You are checking whether a summary invents information.

SOURCE:
{source}

SUMMARY:
{summary}

Work through the summary one claim at a time. A claim is a single assertion of
fact: a name, a number, an event, a causal link, or an attribution.

A claim is UNSUPPORTED when the source neither states it nor directly implies it.
Invented names, dates, figures or quotations count as unsupported, as does a
causal link the source never draws, a statement attributed to the wrong speaker,
and a specific detail where the source was vague.

A claim is SUPPORTED when the source states it, or when it is a fair paraphrase
or generalisation of something the source states. Rewording, condensing and
reordering are not violations.

Judge only whether the source backs each claim. Do not judge whether the summary
is complete, well written, or the right length — omission is not a faithfulness
error and must not be counted. The summary is in Russian while the source may be
in another language; a faithful translation of a supported claim is supported.

Report the total number of claims and how many were unsupported. Keep the
reasoning under 60 words: name the unsupported claims, and nothing else."""

COVERAGE = """You are measuring how much of a checklist a summary covers.

KEY FACTS:
{key_facts}

SUMMARY:
{summary}

For each fact, decide whether the summary entails it — whether someone who read
only the summary would come away knowing that fact.

A fact is ENTAILED when the summary states it, or states something that
necessarily includes it. Wording need not match, and the two may be in different
languages. A fact is NOT ENTAILED when the summary omits it or is so vague that a
reader could not recover it.

Each fact is entailed or not; there is no partial credit. Do not penalise the
summary for covering material outside the checklist — that is not what this
measures.

Report how many facts are entailed out of the total. Keep the reasoning under
60 words: name the facts that were missed, and nothing else."""

NO_FILLER = """The summary below was written under a prompt requiring at least five bullets
that explicitly forbids padding to reach that number: every bullet must carry a
distinct, significant idea, with no overlap and no filler.

SUMMARY:
{summary}

Decide one thing: does any bullet exist only to reach the count?

A bullet is padding when it restates another bullet in different words, when it
says something vacuous that would be true of almost any content ("the speaker
shares useful insights", "several topics are covered"), or when it comments on
the material rather than summarising it.

A bullet is not padding merely for being short, minor, or less interesting than
the others. A genuine but small point is still a distinct idea."""

PAIRWISE = """Two summaries of the same source are shown below. Decide which one serves a
reader better.

SOURCE:
{source}

SUMMARY A:
{summary_a}

SUMMARY B:
{summary_b}

Weigh faithfulness to the source first, then how much of the source's substance
survives, then whether every sentence earns its place.

Length is not quality. A longer summary is not better for being longer, and the
shorter of two summaries wins whenever it loses nothing that mattered — judges
reliably drift toward length, so correct for it deliberately.

Both summaries are in Russian. Judge substance, not polish, and ignore which one
sounds more confident.

Answer A, B, or TIE. Use TIE only when neither is meaningfully better, not to
avoid a hard call. Keep the reasoning under 60 words."""

# The verdict field comes before `reasoning` in every schema. Models emit in
# declared order and it is the long reasoning string that runs into `max_tokens`,
# so putting the number first means a truncated call still carries the answer.
SCHEMAS = {
    "faithfulness": {
        "type": "object",
        "properties": {
            "total_claims": {"type": "integer"},
            "unsupported_claims": {"type": "integer"},
            "reasoning": {"type": "string"},
        },
        "required": ["total_claims", "unsupported_claims", "reasoning"],
        "additionalProperties": False,
    },
    "coverage": {
        "type": "object",
        "properties": {
            "total_facts": {"type": "integer"},
            "entailed_facts": {"type": "integer"},
            "reasoning": {"type": "string"},
        },
        "required": ["total_facts", "entailed_facts", "reasoning"],
        "additionalProperties": False,
    },
    "no_filler": {
        "type": "object",
        "properties": {
            "has_padding": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
        "required": ["has_padding", "reasoning"],
        "additionalProperties": False,
    },
    "pairwise": {
        "type": "object",
        "properties": {
            "winner": {"type": "string", "enum": ["A", "B", "TIE"]},
            "reasoning": {"type": "string"},
        },
        "required": ["winner", "reasoning"],
        "additionalProperties": False,
    },
}

TEMPLATES = {
    "faithfulness": FAITHFULNESS,
    "coverage": COVERAGE,
    "no_filler": NO_FILLER,
    "pairwise": PAIRWISE,
}


def judge_version(name):
    """Short hash pinning the judge prompt, mirroring prompts.prompt_version."""
    payload = f"{TEMPLATES[name]}\0{json.dumps(SCHEMAS[name], sort_keys=True)}"
    return sha256(payload.encode()).hexdigest()[:12]


def judge_meta(name):
    return {
        "judge_model": JUDGE_MODEL,
        "judge_effort": JUDGE_EFFORT,
        "judge_prompt": f"{name}@{judge_version(name)}",
    }


def _post(url, body, timeout=300):
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


def _call_body(name, **fields):
    return {
        "max_tokens": 8000,
        "reasoning": {"effort": JUDGE_EFFORT},
        "messages": [{"role": "user", "content": TEMPLATES[name].format(**fields)}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "verdict", "parameters": SCHEMAS[name]},
            },
        ],
        "tool_choice": {"type": "function", "function": {"name": "verdict"}},
    }


def _unpack(name, choice):
    calls = choice["message"].get("tool_calls")
    if not calls:
        msg = f"{name}: no tool call ({choice.get('finish_reason')})"
        raise RuntimeError(msg)
    verdict = json.loads(calls[0]["function"]["arguments"])
    # OpenRouter does not enforce `required` on this route, so a truncated or
    # lazy call can arrive short a field. Fail loudly rather than score a partial.
    missing = [k for k in SCHEMAS[name]["required"] if k not in verdict]
    if missing:
        msg = f"{name}: verdict missing {missing} ({choice.get('finish_reason')})"
        raise RuntimeError(msg)
    return verdict


def ask(name, **fields):
    """One synchronous judge call."""
    body = {"model": JUDGE_MODEL, **_call_body(name, **fields)}
    payload = _post(CHAT_URL, body)
    return _unpack(name, payload["choices"][0]), payload.get("usage", {})


def _text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "text", "output", "value"):
            if key in value:
                return _text(value[key])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "\n".join(_text(v) for v in value)
    return str(value)


def _source_of(item_input):
    if isinstance(item_input, dict):
        return item_input.get("content", "")
    return _text(item_input)


def _facts_of(expected_output):
    if not expected_output:
        return []
    if isinstance(expected_output, dict):
        return expected_output.get("key_facts") or []
    if isinstance(expected_output, list):
        return expected_output
    return []


# --- Tier 2: evaluator functions for Langfuse.run_experiment -----------------


def eval_faithfulness(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """Share of the summary's claims the source actually supports."""
    source, summary = _source_of(input), _text(output)
    if not source or not summary:
        return None
    verdict, _ = ask("faithfulness", source=source[:120000], summary=summary)
    total = max(verdict["total_claims"], 1)
    unsupported = min(verdict["unsupported_claims"], total)
    return Evaluation(
        name="t2_faithfulness",
        value=1 - unsupported / total,
        data_type="NUMERIC",
        comment=f"{unsupported}/{total} unsupported. {verdict['reasoning']}"[:900],
        metadata=judge_meta("faithfulness"),
    )


def eval_coverage(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """Share of the key-facts checklist the summary entails.

    Returns nothing when the item carries no checklist — the dataset items are
    seeded with an empty `expected_output`, and a fabricated checklist would
    corrupt this score for every model at once.
    """
    facts = _facts_of(expected_output)
    summary = _text(output)
    if not facts or not summary:
        return None
    listed = "\n".join(f"- {f}" for f in facts)
    verdict, _ = ask("coverage", key_facts=listed, summary=summary)
    total = max(verdict["total_facts"], 1)
    entailed = min(verdict["entailed_facts"], total)
    return Evaluation(
        name="t2_coverage",
        value=entailed / total,
        data_type="NUMERIC",
        comment=f"{entailed}/{total} entailed. {verdict['reasoning']}"[:900],
        metadata=judge_meta("coverage"),
    )


def eval_no_filler(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """Whether any bullet exists only to reach the five-bullet minimum.

    Skips non-bulleted output: `basic_prompt_for_transcript` never asked for
    bullets, and scoring it here would penalise it for obeying its own prompt.
    """
    summary = _text(output)
    lines = [ln.strip() for ln in summary.splitlines() if ln.strip()]
    bullets = [ln for ln in lines if ln.startswith(("-", "*", "•", "–", "—"))]
    if len(bullets) < 2:
        return None
    verdict, _ = ask("no_filler", summary=summary)
    return Evaluation(
        name="t2_no_filler",
        value=not verdict["has_padding"],
        data_type="BOOLEAN",
        comment=verdict["reasoning"][:900],
        metadata=judge_meta("no_filler"),
    )


TIER2 = [eval_faithfulness, eval_coverage, eval_no_filler]


# --- the task under evaluation ----------------------------------------------


def make_task(model_id, prompt_key):
    """Summarise one dataset item with a candidate model.

    Goes through `EvalLLMClient`, so the call is the bot's own: instrumented
    agent, system instruction, thinking level, and the cost wrapper that puts a
    price on the same trace as the quality scores.

    Nothing is caught here, unlike the screening task. An empty summary is a
    verdict in screening — Tier 1 books it as a language failure — but in the
    compare stage it would be handed to a judge as if the model had answered,
    and a pairwise duel against a blank is a win that means nothing.
    """
    prompt = dedent(PROMPTS[prompt_key]).strip()

    def task(*, item, **kwargs):  # noqa: ARG001
        text = _source_of(item.input)
        language = (item.input or {}).get("target_language", "Russian")
        # Mirrors summarize_text: prompt and content as two parts, and a blank
        # text drops its part rather than sending an empty one.
        content = [prompt, text] if text.strip() else [prompt]
        return LLM.run(
            content=content,
            model_id=model_id,
            target_language=language,
            thinking_level=THINKING_LEVEL,
        )

    return task


# --- commands ---------------------------------------------------------------


def cmd_run(model_id, limit, dataset_name, prompt_key):
    client = Langfuse()
    dataset = client.get_dataset(dataset_name)
    items = list(dataset.items)[: limit or None]
    print(
        f"{model_id} over {len(items)} items of {dataset_name} "
        f"({prompt_key}, thinking={THINKING_LEVEL})",
    )

    result = client.run_experiment(
        name=f"{model_id} / {prompt_key}",
        data=items,
        task=make_task(model_id, prompt_key),
        evaluators=TIER2,
        max_concurrency=4,
        metadata={
            "stage": "compare",
            "candidate_model": model_id,
            "thinking_level": THINKING_LEVEL,
            # `run_prompt_key`, not `prompt_key`: the Tier 1 rule fires on this
            # experiment too, and it branches on the strategy the run applied.
            # An item's own `prompt_key` is the strategy of the trace it was
            # harvested from, and the datasets are mixed, so leaving this
            # unnamed silently applied the bullet check to the wrong items.
            "run_prompt_key": prompt_key,
            "prompt_version": prompt_version(prompt_key),
        },
    )
    client.flush()
    if config.langfuse_client is not None:
        config.langfuse_client.flush()
    print(f"\nrun: {result.run_name}")
    for row in result.item_results:
        scores = {e.name: e.value for e in row.evaluations}
        print(f"  {str(row.item.id)[:18]:20s} {len(_text(row.output)):5d}ch  {scores}")
    return result


def _run_outputs(dataset_name, run_name):
    """Map dataset item id -> (that run's output text, its trace id).

    Reads the experiment's items directly. The v3 shape this replaced fetched
    the dataset run and then one trace per item for its output, and both halves
    are deprecated: `GET /datasets/{name}/runs/{runName}` is superseded by
    `GET /experiments` plus `GET /experiment-items`, and trace-level
    input/output is deprecated product-wide. `fields=io` returns the root
    observation's output, which is the value the judge should compare anyway,
    and it costs one request per page instead of one per item.
    """
    experiment = API.find_experiment(API.dataset_id(dataset_name), run_name)
    if experiment is None:
        msg = f"no experiment named {run_name!r} on dataset {dataset_name!r}"
        raise RuntimeError(msg)
    out = {}
    for item in API.experiment_items(experiment["id"], fields="core,io"):
        # The trace id travels with the output: a pairwise score has to hang off
        # something, and the natural anchor is run A's trace for that item.
        out[item["experimentItemId"]] = (_text(item.get("output")), item["traceId"])
    return out


def cmd_pairwise(dataset_name, run_a, run_b):
    """Duel two runs over their shared items, both orders, consistent only."""
    client = Langfuse()
    dataset = client.get_dataset(dataset_name)
    sources = {i.id: (_source_of(i.input), i) for i in dataset.items}
    outputs_a, outputs_b = (
        _run_outputs(dataset_name, run_a),
        _run_outputs(
            dataset_name,
            run_b,
        ),
    )
    shared = [k for k in outputs_a if k in outputs_b and k in sources]
    print(f"{len(shared)} shared items between {run_a} and {run_b}")

    calls = []
    for item_id in shared:
        source = sources[item_id][0][:120000]
        text_a, text_b = outputs_a[item_id][0], outputs_b[item_id][0]
        calls.append(
            (
                f"{item_id}|ab",
                "pairwise",
                {"source": source, "summary_a": text_a, "summary_b": text_b},
            ),
        )
        calls.append(
            (
                f"{item_id}|ba",
                "pairwise",
                {"source": source, "summary_a": text_b, "summary_b": text_a},
            ),
        )

    verdicts = {}
    for key, name, fields in calls:
        verdicts[key], _ = ask(name, **fields)

    flip = {"A": "B", "B": "A", "TIE": "TIE"}
    wins = {run_a: 0, run_b: 0, "TIE": 0}
    inconsistent = 0
    for item_id in shared:
        ab, ba = verdicts.get(f"{item_id}|ab"), verdicts.get(f"{item_id}|ba")
        if not ab or not ba:
            continue
        # The second call saw them swapped, so flip its answer back before comparing.
        if ab["winner"] != flip[ba["winner"]]:
            inconsistent += 1
            continue
        winner = {"A": run_a, "B": run_b, "TIE": "TIE"}[ab["winner"]]
        wins[winner] += 1
        client.create_score(
            name="t3_pairwise_win",
            value=ab["winner"],
            data_type="CATEGORICAL",
            comment=ab["reasoning"][:900],
            trace_id=outputs_a[item_id][1],
            metadata={
                **judge_meta("pairwise"),
                "run_a": run_a,
                "run_b": run_b,
                "dataset_item_id": item_id,
                "winner": winner,
            },
        )
    client.flush()
    counted = sum(wins.values())
    print(f"\nconsistent {counted}/{len(shared)}  (dropped {inconsistent})")
    for k, v in wins.items():
        share = f"{v / counted:.0%}" if counted else "-"
        print(f"  {k:45s} {v:3d}  {share}")


def smoke(limit):
    """Judge real traced summaries end to end without posting anything."""
    for name in TEMPLATES:
        print(f"judge prompt {name}: v{judge_version(name)}")
    rows = API.observations(limit=limit, obs_type="GENERATION", fields="core,io")
    print()
    for row in rows:
        try:
            source = json.loads(row["input"])[1]["parts"][1]["content"]
        except Exception:  # noqa: S112
            continue
        summary = _text(row.get("output"))
        if not (source and summary):
            continue
        faith = eval_faithfulness(input={"content": source}, output=summary)
        filler = eval_no_filler(input={"content": source}, output=summary)
        print(f"{row['id']}  src={len(source):6d}ch sum={len(summary):5d}ch")
        print(f"   t2_faithfulness = {faith.value:.3f} | {faith.comment[:100]}")
        if filler:
            print(f"   t2_no_filler    = {filler.value} | {filler.comment[:100]}")
        print()


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "smoke"

    if command == "smoke":
        smoke(int(args[1]) if len(args) > 1 else 2)
    elif command == "run":
        cmd_run(
            args[1],
            int(args[2]) if len(args) > 2 else 0,
            args[3] if len(args) > 3 else SCREEN_DATASET,
            args[4] if len(args) > 4 else "key_points_for_transcript",
        )
    elif command == "pairwise":
        cmd_pairwise(args[1] if len(args) > 1 else COMPARE_DATASET, args[2], args[3])
    else:
        print(f"unknown command: {command}")
        raise SystemExit(2)
