"""Tier 2 judges and the compare-run task, imported by `stage2.py`.

See evals.md → *Tier 2: the judges*; editing a prompt or schema moves its pin.
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

# Followed by `<model> / <prompt_key>`; the name is the only place a run's candidate
# lives. See evals.md → *The report*.
RUN_PREFIX = "stage2 / "

# --- Opus: the finalists' judge ---------------------------------------------
# See evals.md → *Opus `FABRICATED`: the finalists' judge*.

FABRICATED_MODEL = "anthropic/claude-opus-5.5"
FABRICATED_EFFORT = "medium"  # pins depth; recorded in every score's metadata

# Two kinds, and only `invented` fails: a one-kind prompt flagged too many clean
# summaries. See evals.md → *Rejected, and why* (`INVENTED`).
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

# No count or verdict field: the judge enumerates and the runner counts. See
# evals.md → *Opus `FABRICATED`: the finalists' judge*.
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
            # Same attribution the bot sends (see config); the judges' spend is this
            # repo's spend even though they skip LLMClient.
            "HTTP-Referer": config.OPENROUTER_APP_URL,
            "X-Title": config.OPENROUTER_APP_TITLE,
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
        # Ask OpenRouter to price the call. See evals.md →
        # *Judge spend is measured, not estimated*.
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


def generation_failed(output):
    """Whether an item's output is a failed generation (`Error: ...` or empty)."""
    return not output.strip() or output.startswith("Error:")


def _source_of(item_input):
    if isinstance(item_input, dict):
        return item_input.get("content", "")
    return _text(item_input)


# --- JEV: the default Tier 2 judge -------------------------------------------
# See evals.md → *JEV: the cheap screen on every candidate*.

# An alias; `judge_model_version` on each score names the snapshot that answered.
JEV_MODEL = "~typesafe/jev-latest"
DECISIONS_URL = f"{BASE}/alpha/decisions"
# Positive framing on purpose: JEV ignores the criteria's polarity. See evals.md →
# *JEV: the cheap screen on every candidate*.
JEV_SUPPORTED = (
    "Is this claim supported by the source? The claim may be a translation. "
    "Claim: «{claim}»"
)
JEV_SUPPORTED_CRITERIA = {
    "true": "The source states or clearly implies the claim.",
    "false": "The source contradicts the claim or does not contain it.",
}
# A reading aid for the report, not a gate. See evals.md →
# *JEV: the cheap screen on every candidate*.
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
    """P(supported) per bullet, the cost, and the snapshot that answered (or `None`).

    Raises on HTTP errors. Never truncate the source; see evals.md →
    *JEV: the cheap screen on every candidate*.
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
    return [answers[k] for k in questions], cost, payload.get("model")


# --- Tier 2: evaluator functions for Langfuse.run_experiment -----------------


def eval_jev(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """JEV's P(supported) for the weakest bullet, which stands for the summary."""
    source, summary = _source_of(input), _text(output)
    bullets = bullets_of(summary)
    if not source or not bullets:
        return None
    probabilities, cost, version = jev_probabilities(source, bullets)
    weakest = min(range(len(bullets)), key=probabilities.__getitem__)
    return Evaluation(
        name="t2_jev_weakest",
        value=probabilities[weakest],
        data_type="NUMERIC",
        comment=f"bullet {weakest + 1}: {bullets[weakest]}"[:900],
        metadata={**jev_meta(), "judge_model_version": version, "cost": cost},
    )


def eval_fabricated(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """1 when Opus finds nothing invented in the summary, 0 when it finds any.

    Compression findings are recorded in the comment and move nothing.
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


# `none` generates only, so a judge can be added later with `stage2.py judge`.
JUDGES = {"jev": [eval_jev], "opus": [eval_fabricated], "none": []}


# --- the task under evaluation ----------------------------------------------


def make_task(model_id, prompt_key):
    """Summarise one dataset item with a candidate model, through the bot's own client.

    Nothing is caught here: `run_experiment` stores a task that raised as `Error: ...`.
    """
    prompt = dedent(PROMPTS[prompt_key]).strip()

    async def task(*, item, **kwargs):  # noqa: ARG001
        text = _source_of(item.input)
        language = (item.input or {}).get("target_language", "Russian")
        return await summarize(model_id, prompt, text, language)

    return task


def run(model_id, dataset_name, prompt_key, *, tier2="jev"):
    """One compare run over the whole dataset, with the Tier 2 judge named by `tier2`."""
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
            # Not `prompt_key`: Tier 1 branches on this. See evals.md → *A code evaluator
            # receives every metadata value as a string, and a crash inside it is silent*.
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
    # A raised task is missing from `item_results`, not stored there. See evals.md →
    # *API shapes that cost real time to rediscover*.
    empty = sum(generation_failed(_text(r.output)) for r in result.item_results)
    failed = len(items) - len(result.item_results) + empty
    if failed:
        print(
            f"\n  WARNING: {failed}/{len(items)} items failed to generate (the SDK "
            f"logged each as `Item N failed`). Their Tier 1 scores describe the error "
            f"text, not a summary.",
        )
    return result
