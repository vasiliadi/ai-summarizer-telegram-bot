"""Tier 2 LLM judge.

Runs outside Langfuse, though it could move — see `docs/context/evals.md` for
what moving it would cost. It plugs into `Langfuse.run_experiment` as evaluator
functions, so scores attach to the run automatically. Tier 3 pairwise was
removed: readability is judged by the user reading the survivors.

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
candidate shares its family. It never returns a verdict already reduced to one
number: faithfulness **enumerates** its findings, and the severity gate and the
pass/fail are applied here. A model asked directly for `0.71` makes arithmetic
slips no prompt wording fixes, and one asked for a gated verdict hides what it
gated on. Editing a judge prompt or schema moves its `judge_version` hash, which
unpins it from every score already banked.

    uv run python scripts/eval/judge.py run <vendor/model> 2
    uv run python scripts/eval/judge.py run <vendor/model> 0 summarization-compare-v1 --judge=opus|none
    uv run python scripts/eval/judge.py smoke 3
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

from eval_client import THINKING_LEVEL, summarize

import config
from prompts import PROMPTS, prompt_version

BASE = "https://openrouter.ai/api"
CHAT_URL = f"{BASE}/v1/chat/completions"

# Calibration chose this, and it chose against the cheaper option deliberately.
# Sonnet 5 reached 75% agreement and kappa 0.19 against the hand labels on this
# exact prompt; Opus 5 reached 92% and 0.78 on the same 24 items. The usual rule
# — take the cheaper judge and spend the difference on dataset items — does not
# apply when the cheaper judge does not clear the bar at all. The two failed in
# one direction only: Sonnet graded as `minor` what the labels call `material`,
# catching 1 of 7 unfaithful summaries where Opus caught 5, while both stayed
# clean on all 17 faithful ones. Re-measure before assuming a newer cheap model
# inherits this.
JUDGE_MODEL = "anthropic/claude-opus-5"
JUDGE_EFFORT = "medium"  # pins depth; Sonnet 5 rejects temperature outright

# The judge for the pipeline's Opus option since 2026-09-28: FABRICATED on Opus
# 5.5. The user checked most of its 30 "invented" findings on 29 summaries
# against the full sources and agreed with every one they checked; what they
# had rejected in earlier Opus verdicts had been compression. JUDGE_MODEL above stays the
# pin of the old FAITHFULNESS prompt, whose banked scores it describes.
FABRICATED_MODEL = "anthropic/claude-opus-5.5"

# Models that reject a forced tool call (`tool_choice` of type tool or any) with
# a 400, and are asked for the same schema through `response_format` instead.
SCHEMA_OUTPUT_MODELS = {"anthropic/claude-opus-5.5"}

COMPARE_DATASET = "summarization-compare-v1"
SCREEN_DATASET = "summarization-screen-v1"
PROMPT_KEY = "key_points_for_transcript"

# Compare runs carry a prefix for the same reason screening runs do: `GET
# /experiments` returns no metadata, so which stage a run belongs to and which
# candidate produced it are readable only from its name. What follows the prefix
# is `<model> / <prompt_key>`, because a candidate is a model *and* a strategy.
RUN_PREFIX = "stage2 / "

FAITHFULNESS = """You are checking whether a summary invents information.

SOURCE:
{source}

SUMMARY:
{summary}

Work through the summary one claim at a time, covering every bullet from the
first to the last. A claim is a single assertion of fact: a name, a number, an
event, a causal link, or an attribution. Being conservative is about the bar a
claim must clear to be reported, never about how much of the summary you read.

Be conservative. A summary compresses, generalises and rewords by design, and
none of that is a defect. Do not hunt for faults: when a claim follows reasonably
from the source it is supported, however differently it is worded. An empty list
of findings is a normal answer, not a failure to look.

Never report any of these: ordinary paraphrase, dropped detail, outright
omission, related points merged into one, a fair generalisation, an inference the
context plainly supports, reordered information, shorter terminology that keeps
the meaning, obvious transcription noise, style, or rhetoric the summary left
out.

Report a claim only when the summary does one of these:
- contradicts the source;
- adds a fact the source neither states nor implies;
- states something markedly more strongly than the source does;
- changes the status of a fact — first to exclusive, proposed to implemented,
  can to does, may to will, included to free, draft to send, a potential
  customer or channel to an existing one;
- distorts a number, date, period, percentage, cost or scale;
- asserts a causal link the source never draws;
- attributes an action or opinion to the wrong person or company;
- merges distinct conditions, stages or categories so that the meaning shifts;
- uses a term that markedly changes the original sense.

Words like always, never, only, exclusive, guaranteed, required, automatically,
free, all, every, directly causes, will and must are where this usually goes
wrong, because they quietly make a summary stronger than its source. Check each
one you find against what the source actually says.

Verbs deserve the same care, because a changed status hides in one of them and
reads perfectly naturally. Where the summary says a system sends, publishes,
does or has, check whether the source only had it draft, propose, be able to, or
plan to. That substitution is the single most common material error here, and it
never looks like an error in isolation — only against the source.

Judge only whether the source backs each claim. Do not judge whether the summary
is complete, well written, or the right length — omission is not a faithfulness
error and must not be reported. The summary is in Russian while the source may be
in another language; a faithful translation of a supported claim is supported.

Grade every finding:
- material — the factual meaning, status, conclusion or practical reading changes;
- minor — a real error that leaves the summary's meaning intact;
- borderline — defensibly stronger or looser, yet still close to the source. Use
  this rarely; it is not a bin for wording you merely dislike.

Never let the type decide the severity, and never reserve material for claims
carrying one of the words above — a changed status is material whether or not any
such word appears. Ask only whether a reader who acted on the summary would be
misled about what is true.

Return one entry per finding, and an empty list when there is nothing to
report."""


# A schema with a verdict field declares it before `reasoning`: models emit in
# declared order and it is the long reasoning string that runs into `max_tokens`,
# so the number first means a truncated call still carries the answer.
#
# Faithfulness declares no verdict field at all, and calibration is why. Declaring a count ahead
# of the reasoning makes the model commit to a number before it has thought:
# measured against 25 hand labels, one verdict's own reasoning ended "retracting
# to 0 unsupported" while the emitted count stayed 1, and another talked itself
# out of every flag it had already counted. The count could not be revised and
# the reasoning that would explain it was truncated at the comment cap, leaving a
# number nothing could audit. So the judge enumerates instead: each finding
# justifies itself where it is written, an empty list is a clean verdict, and the
# runner applies the severity gate. Truncation now loses the tail of the list
# rather than the grounds for a number already asserted. No claim total survives
# either; `faithfulness_verdict` records what was wrong with the one it replaced.
SCHEMAS = {
    "fabricated": {
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
    },
    "invented": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "source_says": {"type": "string"},
                    },
                    "required": ["claim", "source_says"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["findings"],
        "additionalProperties": False,
    },
    "faithfulness": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "source_says": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["material", "minor", "borderline"],
                        },
                        "type": {
                            "type": "string",
                            "enum": [
                                "contradiction",
                                "unsupported addition",
                                "overstatement",
                                "wrong status",
                                "wrong number",
                                "causal distortion",
                                "terminology",
                                "compression",
                                "other",
                            ],
                        },
                    },
                    "required": ["claim", "source_says", "severity", "type"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["findings"],
        "additionalProperties": False,
    },
}

# One question, from the user's hand labels on 2026-09-27: every error they
# confirmed was an invented or distorted fact, and what they rejected in the
# FAITHFULNESS verdicts was mostly about compression, emphasis and coverage —
# a judgement of the summary's quality on which two readers need not agree.
# No types, no severity: any finding fails the summary.
INVENTED = """Check whether the summary states facts that the source does not contain.

SOURCE:
{source}

SUMMARY:
{summary}

The summary is in Russian; the source may be in another language, and a faithful
translation is not an error. Go through the summary claim by claim, from the
first bullet to the last.

Report a claim only if it states a fact — a name, a number, a date, an event,
who did or said what, what caused what, or whether something happened or is only
planned or possible — that the source does not contain or that the source
contradicts.

Report nothing else: not omission, compression, emphasis, generalisation,
wording, style, or how fully the summary covers the source. A claim the source
states or plainly implies is supported however differently it is worded.

Return one entry per reported claim, with what the source actually says, and an
empty list when there is nothing to report."""

# INVENTED flagged 23 of the 36 summaries the user had labelled clean, and on
# reading them the user found a mix they could neither accept nor reject as a
# set: real fabrications beside artefacts of compressing a long source. What
# the filter must catch is a model that plainly makes things up, so every
# finding is sorted into one of those two, and only the first fails.
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

TEMPLATES = {
    "faithfulness": FAITHFULNESS,
    "invented": INVENTED,
    "fabricated": FABRICATED,
}


def judge_version(name):
    """Short hash pinning the judge prompt, mirroring prompts.prompt_version."""
    payload = f"{TEMPLATES[name]}\0{json.dumps(SCHEMAS[name], sort_keys=True)}"
    return sha256(payload.encode()).hexdigest()[:12]


def judge_meta(name, model=None):
    """The pin recorded beside every score this judge writes.

    `model` is passed when a run is measuring a *candidate* judge rather than
    the pinned one, so two judges scoring the same items stay separable in the
    score table — they share the score name, and the pin is the only thing that
    tells their verdicts apart.
    """
    return {
        "judge_model": model or JUDGE_MODEL,
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
        # Ask OpenRouter to price the call. Without this the usage block counts
        # tokens only, and what a judge actually cost has to be reconstructed
        # from a price table that goes stale the week a vendor changes it.
        "usage": {"include": True},
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


def ask(name, *, model=None, **fields):
    """One synchronous judge call, against `model` or the pinned judge."""
    model = model or JUDGE_MODEL
    body = {"model": model, **_call_body(name, **fields)}
    if model in SCHEMA_OUTPUT_MODELS:
        del body["tools"], body["tool_choice"]
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "verdict", "strict": True, "schema": SCHEMAS[name]},
        }
    payload = _post(CHAT_URL, body)
    choice = payload["choices"][0]
    if model in SCHEMA_OUTPUT_MODELS:
        # Same shape as a tool call's arguments, so `_unpack` checks it the same way.
        content = choice["message"].get("content") or "{}"
        choice = {
            **choice,
            "message": {"tool_calls": [{"function": {"arguments": content}}]},
        }
    return _unpack(name, choice), payload.get("usage", {})


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


def verdict_of(name, verdict):
    """The findings that fail the summary, and the comment to store, per prompt."""
    if name == "faithfulness":
        return faithfulness_verdict(verdict)
    if name == "fabricated":
        findings = verdict["findings"]
        invented = [f for f in findings if f["kind"] == "invented"]
        detail = "; ".join(f["claim"] for f in invented) or "none"
        return (
            invented,
            f"{len(invented)} invented/{len(findings) - len(invented)} compression. {detail}"[
                :900
            ],
        )
    findings = verdict["findings"]
    detail = "; ".join(f["claim"] for f in findings) or "none"
    return findings, f"{len(findings)} invented. {detail}"[:900]


def faithfulness_verdict(verdict):
    """The material findings and the comment to store.

    The severity gate lives here rather than in the prompt, for the same reason
    the judge counts and the runner divides elsewhere: a model asked to return
    one already-gated verdict lets a single nitpick decide the answer, with
    nothing left to inspect afterwards. Only `material` moves the score —
    `minor` and `borderline` are recorded and deliberately do not, because
    calibration showed the hand labels tolerate a real-but-immaterial error and
    reject a changed meaning.

    There is deliberately no claim total to divide by. The judge was asked for
    one and supplied it erratically — absent entirely on one call, and 6 against
    the previous prompt's 15 on the very same summary. A denominator that
    reflects how finely the model chose to slice the summary, and that sometimes
    fails to arrive, cannot carry a quality score.
    """
    findings = verdict["findings"]
    material = [f for f in findings if f["severity"] == "material"]
    detail = "; ".join(f"{f['type']}: {f['claim']}" for f in material) or "none"
    counts = "/".join(
        f"{sum(1 for f in findings if f['severity'] == s)} {s}"
        for s in ("material", "minor", "borderline")
    )
    return material, f"{counts}. {detail}"[:900]


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


def jev_version(instructions=JEV_SUPPORTED, criteria=JEV_SUPPORTED_CRITERIA):
    """Short hash pinning a JEV question and its criteria."""
    payload = f"{instructions}\0{json.dumps(criteria, sort_keys=True)}"
    return sha256(payload.encode()).hexdigest()[:12]


def jev_probabilities(
    source,
    bullets,
    instructions=JEV_SUPPORTED,
    criteria=JEV_SUPPORTED_CRITERIA,
    *,
    batched=True,
):
    """P(supported) per bullet, and what OpenRouter charged. Raises on HTTP errors.

    The source goes whole into `state` and each bullet is its own question:
    asked once whether a whole summary was faithful, JEV ranked barely above
    chance, because finding one wrong claim in a long source is a search, not
    a decision. Batching the bullets into one call changes a bullet's
    probability by a median of 0.000 and cuts the bill about ten times. The
    source is never truncated: a cut source makes every claim from its missing
    half look unsupported.
    """
    questions = {
        f"b{i:02d}": {
            "type": "noul",
            "instructions": instructions.format(claim=b),
            "criteria": criteria,
        }
        for i, b in enumerate(bullets)
    }
    calls = [questions] if batched else [{k: q} for k, q in questions.items()]
    answers, cost = {}, 0
    for batch in calls:
        body = {"model": JEV_MODEL, "state": {"source": source}, "questions": batch}
        payload = _post(DECISIONS_URL, body, timeout=120)
        answers |= {k: a["noul"] for k, a in payload["answers"].items()}
        cost += (payload.get("usage") or {}).get("cost") or 0
    return [answers[k] for k in questions], cost


# --- Tier 2: evaluator functions for Langfuse.run_experiment -----------------


def eval_faithfulness(*, input, output, expected_output=None, metadata=None, **kw):  # noqa: A002, ARG001
    """Whether the summary is free of any material faithfulness error.

    Scored 1 or 0 rather than as a ratio, so that a run's mean reads as the share
    of its summaries that carry no material error — the same statement the hand
    labels make. Tying the two to one definition is what lets the calibration
    number say anything about this score.
    """
    source, summary = _source_of(input), _text(output)
    if not source or not summary:
        return None
    verdict, _ = ask("faithfulness", source=source[:120000], summary=summary)
    material, comment = faithfulness_verdict(verdict)
    return Evaluation(
        name="t2_faithfulness",
        value=0.0 if material else 1.0,
        data_type="NUMERIC",
        comment=comment,
        metadata=judge_meta("faithfulness"),
    )


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
    verdict, usage = ask(
        "fabricated",
        model=FABRICATED_MODEL,
        source=source[:120000],
        summary=summary,
    )
    invented, comment = verdict_of("fabricated", verdict)
    return Evaluation(
        name="t2_fabricated",
        value=0.0 if invented else 1.0,
        data_type="NUMERIC",
        comment=comment,
        metadata={
            **judge_meta("fabricated", FABRICATED_MODEL),
            "invented": len(invented),
            "compression": len(verdict["findings"]) - len(invented),
            "cost": usage.get("cost") or 0,
        },
    )


def jev_meta():
    """The pin recorded beside every JEV score."""
    return {"judge_model": JEV_MODEL, "judge_prompt": f"jev-supported@{jev_version()}"}


# Tier 2 judges selectable per run. JEV is the default and costs cents; Opus
# with FABRICATED is for finalists, at ~$3 a 50-item run. The old FAITHFULNESS
# evaluator is kept for its banked scores but is no longer offered here.
JUDGES = {"jev": [eval_jev], "opus": [eval_fabricated], "none": []}


# --- the task under evaluation ----------------------------------------------


def make_task(model_id, prompt_key):
    """Summarise one dataset item with a candidate model.

    Goes through `EvalLLMClient`, so the call is the bot's own: instrumented
    agent, system instruction, thinking level, and the cost wrapper that puts a
    price on the same trace as the quality scores.

    Nothing is caught here, unlike the screening task. An empty summary is a
    verdict in screening — Tier 1 books it as a language failure — but in the
    compare stage it would be handed to a judge as if the model had answered.
    """
    prompt = dedent(PROMPTS[prompt_key]).strip()

    async def task(*, item, **kwargs):  # noqa: ARG001
        text = _source_of(item.input)
        language = (item.input or {}).get("target_language", "Russian")
        return await summarize(model_id, prompt, text, language)

    return task


# --- commands ---------------------------------------------------------------


def cmd_run(model_id, limit, dataset_name, prompt_key, *, tier2="jev"):
    """One compare run, with the Tier 2 judge named by `tier2` (see `JUDGES`).

    Every run gets the free Tier 1 scores from the Langfuse rule whatever the
    judge; `none` generates only, so a judge can be added to the run later.
    """
    client = Langfuse()
    dataset = client.get_dataset(dataset_name)
    items = list(dataset.items)[: limit or None]
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
    # report about a bad model. Screening only guards the total case (every item
    # at compression 0); nothing catches the partial one, so say it here, where
    # there is still a sweep to stop.
    failed = [r for r in result.item_results if _text(r.output).startswith("Error:")]
    if failed:
        print(
            f"\n  WARNING: {len(failed)}/{len(result.item_results)} items failed to "
            f"generate. Their Tier 1 scores describe the error text, not a summary.",
        )
        print(f"  first: {_text(failed[0].output)[:200]}")
    return result


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
        print(f"{row['id']}  src={len(source):6d}ch sum={len(summary):5d}ch")
        print(f"   t2_faithfulness = {faith.value:.3f} | {faith.comment[:100]}")
        print()


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "smoke"

    if command == "smoke":
        smoke(int(args[1]) if len(args) > 1 else 2)
    elif command == "run":
        tier2 = next(
            (a.split("=", 1)[1] for a in args if a.startswith("--judge=")),
            "jev",
        )
        args = [a for a in args if not a.startswith("--judge=")]
        cmd_run(
            args[1],
            int(args[2]) if len(args) > 2 else 0,
            args[3] if len(args) > 3 else SCREEN_DATASET,
            args[4] if len(args) > 4 else PROMPT_KEY,
            tier2=tier2,
        )
    else:
        print(f"unknown command: {command}")
        raise SystemExit(2)
