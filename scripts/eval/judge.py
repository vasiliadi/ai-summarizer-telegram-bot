"""STG-138 Tier 2 / Tier 3 judge runner.

Runs outside Langfuse deliberately. Langfuse's managed LLM-as-a-judge asks for
structured output via `response_format`, which OpenRouter drops on Anthropic
models (the model answers in prose and nothing errors); it calls chat/completions,
where the half-price `:batch` ids 404; and it sees one item at a time, so pairwise
has nowhere to put the second summary. Forced tool calls work on the same route,
so the judge lives here.

Tier 2 plugs into `Langfuse.run_experiment` as evaluator functions, so scores are
attached to the dataset run automatically. Tier 3 compares two runs and posts its
own scores, because no evaluator can see more than one run.

Judges count; the ratio is computed here. Asking a model for `0.71` invites
arithmetic slips no prompt wording fixes.

    python judge.py run minimax/minimax-m3 2
    python judge.py pairwise <run-a> <run-b>
    python judge.py smoke 3

The judge is synchronous `anthropic/claude-sonnet-5`. OpenRouter's half-price
`:batch` ids were tried and dropped: submission returned a batch id but the
poll/results cycle never delivered, and half price does not justify a second
unproven transport. Do not rebuild it on price alone.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from hashlib import sha256

import _bootstrap
from langfuse import Langfuse
from langfuse.experiment import Evaluation

REPO = _bootstrap.load()

from prompts import PROMPTS, SYSTEM_INSTRUCTION

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


def _get(url, timeout=120):
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
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

    Sends the prompt and the content as two user parts and the system
    instruction separately, mirroring `summary.summarize_text`. It does **not**
    go through `llm.LLMClient`, so pydantic-ai's thinking effort and the
    OpenRouter cost wrapper are absent — fine for ranking prompts and models,
    not a substitute for the bot's own path when thinking level is the variable.
    """
    from textwrap import dedent

    prompt = dedent(PROMPTS[prompt_key]).strip()

    def task(*, item, **kwargs):  # noqa: ARG001
        content = _source_of(item.input)
        language = (item.input or {}).get("target_language", "Russian")
        body = {
            "model": model_id,
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "system",
                    "content": dedent(
                        SYSTEM_INSTRUCTION.format(language=language),
                    ).strip(),
                },
                {"role": "user", "content": prompt},
                {"role": "user", "content": content},
            ],
        }
        payload = _post(CHAT_URL, body)
        return payload["choices"][0]["message"].get("content") or ""

    return task


# --- commands ---------------------------------------------------------------


def cmd_run(model_id, limit, dataset_name, prompt_key):
    client = Langfuse()
    dataset = client.get_dataset(dataset_name)
    items = list(dataset.items)[: limit or None]
    print(f"{model_id} over {len(items)} items of {dataset_name} ({prompt_key})")

    result = client.run_experiment(
        name=f"{model_id} / {prompt_key}",
        data=items,
        task=make_task(model_id, prompt_key),
        evaluators=TIER2,
        max_concurrency=4,
        metadata={"candidate_model": model_id, "prompt_key": prompt_key},
    )
    client.flush()
    print(f"\nrun: {result.run_name}")
    for row in result.item_results:
        scores = {e.name: e.value for e in row.evaluations}
        print(f"  {str(row.item.id)[:18]:20s} {len(_text(row.output)):5d}ch  {scores}")
    return result


def _run_outputs(dataset_name, run_name):
    """Map dataset item id -> that run's output text."""
    from urllib.parse import quote

    import requests

    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    # Run names carry the model id, so they contain slashes and spaces; without
    # encoding, "minimax/minimax-m3 / ..." becomes extra path segments and 404s.
    path = f"{quote(dataset_name, safe='')}/runs/{quote(run_name, safe='')}"
    response = requests.get(f"{base}/api/public/datasets/{path}", auth=auth, timeout=60)
    if response.status_code != 200:
        msg = f"run {run_name!r}: HTTP {response.status_code}"
        raise RuntimeError(msg)
    run = response.json()
    out = {}
    for row in run.get("datasetRunItems", []):
        trace = requests.get(
            f"{base}/api/public/traces/{row['traceId']}",
            auth=auth,
            timeout=60,
        ).json()
        # The trace id travels with the output: a pairwise score has to hang off
        # something, and the natural anchor is run A's trace for that item.
        out[row["datasetItemId"]] = (_text(trace.get("output")), row["traceId"])
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
    import subprocess

    for name in TEMPLATES:
        print(f"judge prompt {name}: v{judge_version(name)}")
    out = subprocess.run(
        [
            "npx",
            "-y",
            "langfuse-cli",
            "--env",
            ".env",
            "api",
            "observations",
            "list",
            "--type",
            "GENERATION",
            "--limit",
            str(limit),
            "--fields",
            "core,io",
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=True,
    ).stdout
    rows = json.loads(out[out.index('{"status"') :])["body"]["data"]
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
