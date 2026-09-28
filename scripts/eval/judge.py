"""Tier 2 judges and the compare-run task, imported by `stage2.py`.

Runs outside Langfuse, though it could move — see `docs/context/evals.md` for
what moving it would cost. The judges plug into `Langfuse.run_experiment` as
evaluator functions, so scores attach to the run automatically.

Two judges, chosen per run through `JUDGES`: JEV, the default, asks per bullet
whether the source supports it for about two cents a run; Opus with the
`FABRICATED` prompt sorts every unsupported claim into invented or compression
for about $3 a run, and is spent on finalists only.

Two model callers live here and only one of them is the bot's. The **candidate**
summarises through `eval_client.summarize`, so a compare run records cost and
applies the thinking level — quality alone always picks the most expensive
configuration, so the price has to arrive beside the score. The **judges** keep
their own HTTP calls: Opus needs structured output against a JSON schema, which
`LLMClient` does not do and the bot never asks for, and what a judge spends is a
cost of running the evaluation rather than a property of the model being ranked.

Neither judge returns a verdict already reduced to one number: Opus enumerates
its findings and the invented/compression split is counted here, and JEV
returns a probability per bullet. Editing a prompt or schema moves its pin
(`judge_prompt` in the score metadata), which unpins it from every score
already banked.
"""

import json
import os
import urllib.request
from hashlib import sha256
from textwrap import dedent

import _bootstrap
from langfuse import Langfuse
from langfuse.experiment import Evaluation

REPO = _bootstrap.load()

from eval_client import THINKING_LEVEL, summarize

import config
from prompts import PROMPTS, prompt_version

BASE = "https://openrouter.ai/api"
CHAT_URL = f"{BASE}/v1/chat/completions"

COMPARE_DATASET = "summarization-compare-v1"
PROMPT_KEY = "key_points_for_transcript"

# Compare runs carry a prefix because `GET /experiments` returns no metadata, so
# which stage a run belongs to and which candidate produced it are readable only
# from its name. What follows the prefix is `<model> / <prompt_key>`, because a
# candidate is a model *and* a strategy.
RUN_PREFIX = "stage2 / "

# --- Opus: the finalists' judge ---------------------------------------------
#
# FABRICATED on Opus 5.5 since 2026-09-28. The user checked most of its 30
# "invented" findings on 29 summaries against the full sources and agreed with
# every one they checked; what they had rejected in earlier Opus verdicts had
# been compression. Opus 5.5 rejects a forced tool call with a 400, so the
# schema is asked for through `response_format`.

FABRICATED_MODEL = "anthropic/claude-opus-5.5"
FABRICATED_EFFORT = "medium"  # pins depth; recorded in every score's metadata

# A prompt asking only for invented facts flagged 23 of the 36 summaries the user
# had labelled clean, and on reading them the user found a mix they could
# neither accept nor reject as a set: real fabrications beside artefacts of
# compressing a long source. What the filter must catch is a model that plainly
# makes things up, so every finding is sorted into one of those two, and only
# the first fails.
FABRICATED = """Check whether the summary makes things up.

SOURCE:
{source}

SUMMARY:
{summary}

The summary is in Russian; the source may be in another language, and a faithful
translation is not an error. Go through the summary claim by claim, from the
first bullet to the last, and report every claim the source does not support.
Put each one in exactly one of two kinds:

- invented — the claim has no basis in the source or the source says otherwise:
  a name, company, person, number, date or event the source does not have; the
  wrong actor; something stated as done that the source says was not done, or
  the reverse.
- compression — the claim comes from squeezing the source into a few bullets:
  points merged, generalised, re-emphasised, stated a little more or less
  strongly, an obvious link spelled out, a detail rounded or blurred.

When a claim could be either, it is compression. Do not report omission, style,
or how fully the summary covers the source.

Return one entry per reported claim, with what the source actually says, and an
empty list when there is nothing to report."""

# No count or verdict field: a model that declares a number before its reasoning
# commits to it before it has thought, and one that truncates loses the grounds
# for a number already asserted. An enumerated list loses only its tail.
FABRICATED_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "source_says": {"type": "string"},
                    "kind": {"type": "string", "enum": ["invented", "compression"]},
                },
                "required": ["claim", "source_says", "kind"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def fabricated_meta():
    """The pin recorded beside every Opus score."""
    payload = f"{FABRICATED}\0{json.dumps(FABRICATED_SCHEMA, sort_keys=True)}"
    return {
        "judge_model": FABRICATED_MODEL,
        "judge_effort": FABRICATED_EFFORT,
        "judge_prompt": f"fabricated@{sha256(payload.encode()).hexdigest()[:12]}",
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


def ask_fabricated(source, summary):
    """One synchronous Opus call: the verdict, and OpenRouter's usage block."""
    body = {
        "model": FABRICATED_MODEL,
        "max_tokens": 8000,
        "reasoning": {"effort": FABRICATED_EFFORT},
        # Ask OpenRouter to price the call. Without this the usage block counts
        # tokens only, and what a judge actually cost has to be reconstructed
        # from a price table that goes stale the week a vendor changes it.
        "usage": {"include": True},
        "messages": [
            {
                "role": "user",
                "content": FABRICATED.format(source=source, summary=summary),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "verdict",
                "strict": True,
                "schema": FABRICATED_SCHEMA,
            },
        },
    }
    payload = _post(CHAT_URL, body)
    choice = payload["choices"][0]
    verdict = json.loads(choice["message"].get("content") or "{}")
    # OpenRouter does not enforce `required`, so a truncated or lazy call can
    # arrive short a field. Fail loudly rather than score a partial.
    if "findings" not in verdict:
        msg = f"fabricated: verdict missing findings ({choice.get('finish_reason')})"
        raise RuntimeError(msg)
    return verdict, payload.get("usage", {})


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


# --- JEV: the default Tier 2 judge -------------------------------------------
#
# TypeSafe's decisions model, reached on OpenRouter's /api/alpha/decisions with
# the ordinary key. It returns a probability per yes/no question and writes no
# text. Chosen on 2026-09-28 over Opus on cost, not on a calibration: no judge
# could be certified against the user's labels (evals.md, *JEV*), and Opus
# costs about $3 a candidate against JEV's two cents. Its number is read
# comparatively across candidates, never against a floor.

JEV_MODEL = "typesafe/jev-1.13"
DECISIONS_URL = f"{BASE}/alpha/decisions"
# The positive framing. Asked whether a claim is *invented*, JEV answered the
# question and ignored the criteria's polarity (AUC 0.28), so the question
# asks whether a claim is supported and `true` is the clean answer.
JEV_SUPPORTED = (
    "Is this claim supported by the source? The claim may be a translation. "
    "Claim: «{claim}»"
)
JEV_SUPPORTED_CRITERIA = {
    "true": "The source states or clearly implies the claim.",
    "false": "The source contradicts the claim or does not contain it.",
}
# A summary whose weakest bullet is below this is counted as possibly
# fabricated. 0.6 was the best balance on 42 hand-labelled summaries (2 of 3
# stepfun errors, 2 false alarms of 17); treat it as a reading aid, not a gate.
JEV_FLAG_BELOW = 0.6


def bullets_of(summary):
    """The summary's bullets, markers stripped; every non-empty line is one."""
    return [
        line.lstrip("-*• ").strip() for line in summary.splitlines() if line.strip()
    ]


def jev_meta():
    """The pin recorded beside every JEV score."""
    payload = f"{JEV_SUPPORTED}\0{json.dumps(JEV_SUPPORTED_CRITERIA, sort_keys=True)}"
    return {
        "judge_model": JEV_MODEL,
        "judge_prompt": f"jev-supported@{sha256(payload.encode()).hexdigest()[:12]}",
    }


def jev_probabilities(source, bullets):
    """P(supported) per bullet, and what OpenRouter charged. Raises on HTTP errors.

    The source goes whole into `state` and each bullet is its own question:
    asked once whether a whole summary was faithful, JEV ranked barely above
    chance, because finding one wrong claim in a long source is a search, not
    a decision. All bullets go in one call: against one call per bullet, that
    changes a bullet's probability by a median of 0.000 and cuts the bill about
    ten times. The source is never truncated: a cut source makes every claim
    from its missing half look unsupported.
    """
    questions = {
        f"b{i:02d}": {
            "type": "noul",
            "instructions": JEV_SUPPORTED.format(claim=b),
            "criteria": JEV_SUPPORTED_CRITERIA,
        }
        for i, b in enumerate(bullets)
    }
    body = {"model": JEV_MODEL, "state": {"source": source}, "questions": questions}
    payload = _post(DECISIONS_URL, body, timeout=120)
    answers = {k: a["noul"] for k, a in payload["answers"].items()}
    cost = (payload.get("usage") or {}).get("cost") or 0
    return [answers[k] for k in questions], cost


# --- Tier 2: evaluator functions for Langfuse.run_experiment -----------------


def eval_jev(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """JEV's P(supported) for the summary's weakest bullet.

    One number per summary: a single invented claim is enough to mislead, so
    the weakest bullet stands for the summary, and an average would let ten
    sound bullets hide one invented one.
    """
    source, summary = _source_of(input), _text(output)
    bullets = bullets_of(summary)
    if not source or not bullets:
        return None
    probabilities, cost = jev_probabilities(source, bullets)
    weakest = min(range(len(bullets)), key=probabilities.__getitem__)
    return Evaluation(
        name="t2_jev_weakest",
        value=probabilities[weakest],
        data_type="NUMERIC",
        comment=f"bullet {weakest + 1}: {bullets[weakest]}"[:900],
        metadata={**jev_meta(), "cost": cost},
    )


def eval_fabricated(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """1 when Opus finds nothing invented in the summary, 0 when it finds any.

    Compression findings are recorded in the comment and move nothing: they
    are what squeezing a long source into a few bullets does, and the user
    rejected them as errors while accepting every invented one they checked.
    ~$0.06 a call.
    """
    source, summary = _source_of(input), _text(output)
    if not source or not summary:
        return None
    verdict, usage = ask_fabricated(source, summary)
    findings = verdict["findings"]
    invented = [f for f in findings if f["kind"] == "invented"]
    detail = "; ".join(f["claim"] for f in invented) or "none"
    return Evaluation(
        name="t2_fabricated",
        value=0.0 if invented else 1.0,
        data_type="NUMERIC",
        comment=f"{len(invented)} invented/{len(findings) - len(invented)} compression. {detail}"[
            :900
        ],
        metadata={
            **fabricated_meta(),
            "invented": len(invented),
            "compression": len(findings) - len(invented),
            "cost": usage.get("cost") or 0,
        },
    )


# Tier 2 judges selectable per run. JEV is the default and costs cents; Opus
# with FABRICATED is for finalists, at ~$3 a 50-item run; `none` generates only,
# so a judge can be added to the run later with `stage2.py judge`.
JUDGES = {"jev": [eval_jev], "opus": [eval_fabricated], "none": []}


# --- the task under evaluation ----------------------------------------------


def make_task(model_id, prompt_key):
    """Summarise one dataset item with a candidate model.

    Goes through `EvalLLMClient`, so the call is the bot's own: instrumented
    agent, system instruction, thinking level, and the cost wrapper that puts a
    price on the same trace as the quality scores. Nothing is caught here: a
    task that raises is stored as `Error: ...` by `run_experiment`, which
    `run` reports.
    """
    prompt = dedent(PROMPTS[prompt_key]).strip()

    async def task(*, item, **kwargs):  # noqa: ARG001
        text = _source_of(item.input)
        language = (item.input or {}).get("target_language", "Russian")
        return await summarize(model_id, prompt, text, language)

    return task


def run(model_id, dataset_name, prompt_key, *, tier2="jev"):
    """One compare run over the whole dataset, with the Tier 2 judge named by `tier2`.

    Every run gets the free Tier 1 scores from the Langfuse rule whatever the
    judge. The run is always the whole dataset: the report reads the newest run
    per candidate, so a short probe run would replace a full one there.
    """
    client = Langfuse()
    items = list(client.get_dataset(dataset_name).items)
    print(
        f"{model_id} over {len(items)} items of {dataset_name} "
        f"({prompt_key}, thinking={THINKING_LEVEL}, tier2={tier2})",
    )

    result = client.run_experiment(
        name=f"{RUN_PREFIX}{model_id} / {prompt_key}",
        data=items,
        task=make_task(model_id, prompt_key),
        evaluators=JUDGES[tier2],
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
            "tier2_judge": tier2,
        },
    )
    client.flush()
    if config.langfuse_client is not None:
        config.langfuse_client.flush()
    print(f"\nrun: {result.run_name}")
    for row in result.item_results:
        scores = {e.name: e.value for e in row.evaluations}
        print(f"  {str(row.item.id)[:18]:20s} {len(_text(row.output)):5d}ch  {scores}")
    # A task that raises is not lost, it is *stored*: `run_experiment` writes
    # `Error: {exc}` into the item's output and skips that item's Tier 2
    # evaluators. The Tier 1 rule still fires, and it scores the English error
    # text as a language failure — so a partly failed run reads as a plausible
    # report about a bad model. Say so here, where there is still a sweep to stop.
    failed = [r for r in result.item_results if _text(r.output).startswith("Error:")]
    if failed:
        print(
            f"\n  WARNING: {len(failed)}/{len(result.item_results)} items failed to "
            f"generate. Their Tier 1 scores describe the error text, not a summary.",
        )
        print(f"  first: {_text(failed[0].output)[:200]}")
    return result
