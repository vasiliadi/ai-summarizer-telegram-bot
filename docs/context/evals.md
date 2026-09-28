# Evaluation

How summarization quality is measured: the Langfuse dataset built from real traces, the scoring
tiers, the judges, and the harness in `scripts/eval/`.

Nothing here is imported by the bot — these are operational scripts, run by hand.
`architecture.md` owns the bot itself, including *how* it emits the traces this is built on;
read its **Tracing** bullet before changing anything that produces trace data.

## What this is for

**The registry is the output of evaluation, not its input.** New models appear and existing
ones change constantly, so the question this answers is *should this model be in
`config.MODEL_SPECS` at all* — run a candidate through the harness first, then decide whether to
add it. It also re-checks models already registered, and gates prompt edits against regression,
but candidate screening is the primary use.

**It is a filter, not a ranking.** The harness removes models that are certainly unfit and puts
cost, length and a fabrication signal beside the rest; a person decides between the survivors by
reading them. Only Tier 1 — deterministic — drops a model. No judge sets a floor, because no
judge could be certified per summary against a human reader (see *Rejected*).

### Everything runs over OpenRouter, and models are named by their OpenRouter id

The harness never consults `config.MODEL_SPECS`. Model ids are passed as arguments, always,
with no default list — requiring a model to be registered before it can be evaluated would
invert the tool.

**Do not add a default list back.** The set worth evaluating is different every time, and in
steady state a new model shows up on its own — vendors do not ship on the same day — so the
normal invocation is one id, and a constant would be stale the week after it was written.

One route for every model also keeps results comparable, and the price of that is accepted
deliberately: a model the bot reaches through its own provider is evaluated over OpenRouter
instead, so its numbers sit very slightly off the bot's real behaviour. Comparing models to
each other is unaffected.

**Never derive an OpenRouter id by prefixing a vendor name.** The catalog carries `:free` and
`:batch` siblings next to the plain id, so a computed id can silently select a different model
and bill for it. `stage2.py sweep` validates every id against the catalog and refuses to start
otherwise, printing the near-misses.

### A candidate's route

Nothing below needs the model to be in `config.MODEL_SPECS`, and it should not be added until
the end:

1. **One compare run.** `stage2.py sweep <openrouter-id> ...` summarises the 50 items of
   `summarization-compare-v1` through `eval_client.EvalLLMClient`. The run gets the Tier 1 scores
   from the Langfuse rule for free and JEV's `t2_jev_weakest` from the default Tier 2 evaluator,
   about two cents. The summaries themselves cost roughly $0.02–$1.10 a run, depending on the
   model's price.
2. **Read `stage2.py report`.** `t1_pass` below 95% drops the model. JEV sets no floor: its
   median weakest-bullet probability and the share of summaries below `JEV_FLAG_BELOW` are read
   against the other candidates, the production model above all; `--all-pairs` adds a paired
   sign test per item.
3. **Opus on the finalists only.** `stage2.py judge opus <openrouter-id> ...` adds
   `t2_fabricated` (Opus 5.5, `FABRICATED` prompt) to the existing runs, about $3 a model, no
   regeneration. The report then prints each finalist's *invented* share.
4. **Read the survivors live**, weighing the invented share against `run $` and compression. A
   longer summary that keeps more detail counts in a model's favour.
5. **Then decide, and only then edit `config.py`.** Adding an id needs no migration; removing
   or renaming one does — see the registry bullet in `architecture.md`. A model registered under
   the `google` provider keeps its native id there, without the vendor prefix.
6. **Sweep thinking levels** on the chosen model only, and expect to decide it on cost and
   latency rather than quality, because adjacent levels rarely separate.

Track cost and latency beside quality throughout; quality alone always picks the most expensive
configuration. Below ~30 items report gross failure rates only, never rankings. Keep the dataset
afterwards as a regression gate for prompt edits, not only for model launches.

### The candidate summarises through the bot's client; the judges do not

`eval_client.py` holds `EvalLLMClient` and the one `THINKING_LEVEL` every run uses. It
subclasses `LLMClient` and overrides only `build_model`, so a run goes through the instrumented
path and records cost and thinking level while the base class's registry lookup (which would
raise `KeyError` for a candidate) is bypassed. A candidate's cost and latency are half of the
question, so they have to be produced on the bot's own terms.

**An experiment task must be `async def` and reach the model through
`eval_client.summarize`.** `run_experiment` awaits the task inside its own running event loop,
while `LLMClient.run` ends in pydantic-ai's `run_sync`, which drives a loop itself — calling it
from there raises `RuntimeError: This event loop is already running` on *every* item, before a
single request leaves the machine. `summarize` hands the call to a worker thread, which has no
running loop, so `run_sync` builds its own and the bot's synchronous path is reused rather than
reimplemented. The context is copied into the thread, so the generation span still nests under
the experiment item and the cost wrapper still finds it. The failure is cheap and looks
expensive to diagnose: every item fails in seconds and is recorded as an error output.

The **judges** stay on their own HTTP calls in `judge.py`, deliberately. Opus needs structured
output against a JSON schema, which `LLMClient` does not do and the bot never asks for, and JEV
is not a chat model at all. What a judge spends is a cost of running the evaluation, not a
property of the model being ranked, so it does not belong on the candidate's trace either.

## The harness

| File | Purpose |
|---|---|
| `_bootstrap.py` | Loads `.env`, puts `src/` on the import path, returns Langfuse REST credentials |
| `eval_client.py` | `EvalLLMClient`, `summarize` with its generation timeout, and `THINKING_LEVEL` |
| `langfuse_api.py` | The only place that calls the Langfuse REST API. v4 endpoints, rate-limit aware |
| `tier1_evaluator.py` | Tier 1 deterministic scorers. Uploaded to Langfuse, **executed there** |
| `install_tier1.py` | Uploads the above. Its preflight is the only way to see the evaluator crash |
| `judge.py` | The two Tier 2 judges (JEV, Opus `FABRICATED`) and the compare-run task. Imported, not run |
| `stage2.py` | The command line: `sweep`, `report`, and `judge`, which adds a judge to existing runs |
| `rebuild_datasets.py` | Rebuilds the dataset from a raw harvest. Destructive; needs `--yes-wipe` |

```bash
uv run python scripts/eval/install_tier1.py     # after every edit to tier1_evaluator.py
uv run python scripts/eval/stage2.py report [--all-pairs]  # free, read-only
uv run python scripts/eval/stage2.py sweep <openrouter-id> ... [--judge=jev|opus|none]  # COSTS MONEY: a compare run each
uv run python scripts/eval/stage2.py judge jev [<openrouter-id> ...]    # ~2 cents a run: JEV where missing
uv run python scripts/eval/stage2.py judge opus <openrouter-id> ...     # ~$3 a run: Opus FABRICATED on finalists
```

**A run is always the whole dataset.** The report reads the newest run per candidate, so a short
probe run made after a full one would replace it there; there is no item limit to pass.

**A sweep can hang forever on one item, so generation times out after 10 minutes.** Sweeps have
stopped at 49 of 50 items, on sources of very different lengths, with every socket in
`CLOSE_WAIT` and CPU at zero. A `py-spy dump` of the live process (`sudo "$(which uvx)" py-spy
dump --pid <pid>`; macOS needs `sudo`) showed one worker thread in `LLM.run` → `agent.run_sync` →
pydantic-ai's own event loop, idle in `select()` — the **candidate generation**, not the judge.
Unconfirmed hypothesis: `run_experiment(max_concurrency=4)` puts each task on a thread,
`run_sync` builds a new loop there, and all of them share `config.openrouter_provider` and its one
async HTTP pool, which can deadlock across event loops. The bot calls `run_sync` in a similar
way, so if this is the cause it is not harness-only, and a fix belongs in `src/llm.py` — the root
cause is still **open**. The harness side is handled: `eval_client.summarize` runs each
generation on a **daemon** thread and waits `GENERATION_TIMEOUT` (600 s), so a stuck item is
stored as a named `TimeoutError` and the run finishes. It had to be a daemon thread:
`asyncio.to_thread` uses the default executor, whose threads are joined at interpreter exit, so a
timeout around it would only move the hang to shutdown. A timed-out item shows in the run's
failed-items warning and fails Tier 1, like any other failed item.

**Wait a minute after a run before reading its report.** Langfuse ingests experiment items and
scores asynchronously — a posted score was absent six seconds after `flush()` and present twenty
seconds later — so a report read straight after a run shows fewer items or scores than were
written, which looks exactly like a judge that silently failed. Check that `n` equals the dataset
size before trusting a row.

Anything that only reads is free. Re-scoring Tier 1 never costs anything — the summaries already
exist as trace outputs, so a broken scorer is repaired by reinstalling it and recomputing, not by
re-generating. Only Tier 2 spends money on a re-score.

### Harness runs report to Sentry as `production`, and that is left alone deliberately

Every script here imports `config` from `src/`, whose `sentry_sdk.init` sets no `environment` —
so the SDK defaults to `production` — and enables `LoggingIntegration(capture_sentry_logs=True)`,
which forwards stdlib `ERROR` records. Langfuse logs a failed evaluator at `ERROR`, so **a sweep
run from a laptop raises Sentry issues in the bot's production stream**, tagged
`environment: production` with `server_name` set to the developer's machine.

Do not diagnose these as bot defects. Tell them apart by `sys.argv` in the event's extra data:
a harness event carries `scripts/eval/...`, and `Users Impacted` is 0.

Threading a `SENTRY_ENVIRONMENT` through `config.py` was proposed and **declined** — it is a
change to production code at 100% coverage for a developer-only annoyance. The consequence is
accepted rather than overlooked: these issues **recur on every sweep** and are closed as noise.
Revisit only if harness noise starts masking a real production alert.

## Where state lives

State is split across three places, and only one of them is the repository.

| What | Where |
|---|---|
| Scripts, Tier 1 evaluator source | `scripts/eval/` (tracked) |
| Prompts, datasets, score configs, evaluators, rules, runs, scores | Langfuse (server) |
| Raw trace harvest (`obs.json`), ad-hoc probes | untracked, local only |

**On the free Hobby plan the public API sees only the last 30 days.** The limit is "30 days data
access", an access window, not deletion: older experiments, scores and hand labels come back
empty from every route while the UI still shows them. So the data exists, the harness cannot read
it, and nothing warns. Datasets and their items are unaffected. The paid Core tier raises the
window to 90 days. So "banked in Langfuse" means readable by the scripts for a month: anything
that must outlive that — hand labels above all, since they cost days rather than dollars — has
to be exported to a local file the day it is made.

The part that surprises people: `tier1_evaluator.py` **never runs on your machine**. Langfuse
stores the source and executes it on its own infrastructure when an experiment item arrives.
The local file is only the source uploaded by `install_tier1.py`.

## Working with the Langfuse API

**Use the `langfuse` skill.** It carries the CLI, the current API reference and the version
migration guides, and it is the authority on endpoint shapes and SDK usage — do not implement
from memory, and do not restate its contents here. API surfaces change; a copy in this file
would go stale silently.

What belongs here is only what the skill cannot know:

- **`scripts/eval/langfuse_api.py` is the only place that calls the REST API**, apart from the
  dataset rebuild. Add reads there rather than scattering `requests` through the scripts.
- **This project is already on the v4 data model.** Ingestion is OTel via the pinned SDK, the
  one evaluation rule targets `experiment`, and no blob-storage, PostHog or Mixpanel export is
  configured, so the export migration does not apply. Trace-level input/output is deprecated
  product-wide and nothing in `src/` sets it — see the **Tracing** bullet in `architecture.md`.
- **Langfuse switches the deprecated routes off on 2026-11-16, and the SDK still calls one of
  them.** The REST calls in `scripts/eval/` are already on the replacements (`v2/observations`,
  `v3/scores`, `experiments` + `experiment-items`, `v2/datasets`, `v2/evaluators`). But
  `Langfuse.run_experiment` — in 4.14.4 and 4.15.6 — links every item to its run through
  `POST /dataset-run-items`, which is on the list. It catches the failure and only logs *"Failed
  to create dataset run item"*, so after the cutoff a sweep would complete, write its traces and
  scores, and **never appear as an experiment**: `stage2.py report` would say no runs exist.
  **Before sweeping after the cutoff**, check the SDK changelog for a release that moved off the
  route, bump to it, and confirm a one-item run shows up in `GET /experiments`. `GET /traces` is
  deprecated too; read traces as `v2/observations` rows grouped by `traceId`.
- **Read experiment results from the experiment endpoints, never by joining traces.** Evaluator
  scores attach to the **observation**, so filtering scores by experiment id returns nothing for
  them and reads exactly like the evaluator never fired. Requesting the score and IO field groups
  on the experiment's items returns both inline — but see the seven-score cap under *API shapes*.

Two traps cost a session each and are worth carrying:

- The public API **rate-limits** and answers with a retry delay that must be **obeyed**. Blind
  exponential backoff does not converge, because every retry spends another request. An
  unchecked rate-limit response also falls through `.json().get("data", [])` as an empty list,
  which is indistinguishable from a model that genuinely scored nothing — that produced a
  *different table on each run* until it was fixed.
- Paginate on the cursor the response actually returns. Guessing a plausible field name yields
  `None` and silently truncates a sweep at the first page.

## Running an experiment: UI vs script

Both produce experiments the Tier 1 rule scores, but they measure different things. The
difference that generates all the others: **through the UI, Langfuse calls the model; through
the script, your code does.**

| | UI Prompt Experiment | `scripts/eval/stage2.py sweep` |
|---|---|---|
| Who calls the model | Langfuse, via an LLM Connection | your code, locally |
| Prompt source | the Langfuse mirror | `src/prompts.py` directly |
| Code path | Langfuse's request builder | `llm.LLMClient` — the bot's path |
| Thinking level | not applied | `build_settings` applies it |
| Cost | Langfuse's own pricing | `OpenRouterCostReporter`, what OpenRouter charged |
| `environment` | `langfuse-prompt-experiment` | `sdk-experiment` |
| Tier 1 | fires | fires |
| Tier 2 | not possible | `run_experiment(evaluators=[…])` |
| In git | no | yes |

A UI run has no cost wrapper and no thinking level — it measures a call the bot never makes. Use
it to eyeball prompt wording; use the script for anything that feeds a decision. If a UI run is
compared against a script run, check first that the prompt mirror has not drifted from
`src/prompts.py`: the mirror stores `prompt_version` in its `config` for exactly this. UI runs are
named `Prompt … on dataset …`, so the report's `stage2 / ` prefix filter skips them.

## Prompts: a hand-maintained mirror, for experiments only

Two chat prompts named exactly after the `prompt_key`s (`basic_prompt_for_transcript`,
`key_points_for_transcript`) hold a copy of what `src/prompts.py` sends, so a Langfuse Prompt
Experiment can run a strategy over a dataset against any model. `src/prompts.py` stays the
source of truth and the bot never calls `get_prompt` — that keeps prompts in the repo, puts no
network fetch on the request path, and leaves `prompts.prompt_version` as the pin a trace
carries. Edits are made in the UI when a template changes; they are rare enough that a sync
script was **rejected** as machinery for a once-a-quarter edit.

Four things about the shape are load-bearing, and none announce themselves when broken — the
experiment just renders every dataset item identically:

- `type` is `chat` and is **immutable after creation**. A prompt created as `text` can never
  become one; it has to be deleted and recreated, losing its version history.
- The system message is `SYSTEM_INSTRUCTION` with `{language}` rewritten to
  `{{target_language}}`. Langfuse substitutes double braces only, so a single-brace placeholder
  is copied through as literal text rather than failing loudly.
- Two separate `user` messages — the strategy template, then `{{content}}` alone — because
  `summarize_text` sends the prompt and the content as two parts. Concatenating them into one
  message measures a call the bot never makes.
- Variable names must equal the dataset item's input keys (`content`, `target_language`;
  `prompt_key` selects the prompt rather than filling a variable). Langfuse resolves a variable
  only against a key of the same name, so renaming either side breaks every run.

Do **not** add a `Language` prompt referenced by composition. It freezes into the prompt what
the dataset needs as a per-item variable, so a run cannot mix target languages, and Langfuse then
refuses to delete it while any dependent version survives. Storing `prompt_version(prompt_key)`
in the prompt's `config` is what ties a Langfuse version back to the repo revision it was copied
from; nothing else records it.

## The dataset is built from traces, and the content type is not one of the fields

`summarization-compare-v1` holds 50 items of screened trace content, built by
`rebuild_datasets.py` from a raw harvest. Item `input` is `{content, target_language}` and
nothing else — those are the two prompt variables, and an `inputSchema` rejects an item missing
either. `prompt_key` rides in `metadata`, not `input`: an experiment picks one prompt and runs it
over every item, so the originating trace's strategy fills no variable.
**Only traces whose own summary is in Cyrillic are harvested**: `t1_language_match` measures
the Cyrillic share, so an item in another language would fail Tier 1 on a correct summary.
`rebuild_datasets.py` applies Tier 1's own test (`_cyrillic_ratio` against `CYRILLIC_FLOOR`) to
the `text` parts of the trace's output — the `thinking` parts are skipped, since they are often
in English — and skips a trace with no `target_language`. No language is named, so any
Cyrillic-script target qualifies, while the `FABRICATED` prompt still states one fixed language.

**The Tier 1 rule fires only on the datasets its filter names.** `tier1-on-experiments` filters
on `datasetId any of` — the compare dataset's id — plus `isExperimentItemRootSpan`. A new
dataset gets no Tier 1 scores until its id is added (`PATCH /v2/evaluation-rules/{id}` with the
whole `filter` array; send only the fields to change), and nothing warns: the report simply shows
no `t1_*` columns. Take a dataset's id out of the filter before deleting the dataset — what the
rule does with the id of a deleted dataset is unknown. The API has no dataset delete; that is UI
only.

The trap when harvesting: a trace's tag is the **Telegram** `content_type`, which is `text` for
a URL as much as for a pasted paragraph. A YouTube transcript, a web article and a
Replicate-rescued audio transcript are therefore all tagged `text`, and no field distinguishes
them — the stratum has to be inferred from the content, by **two** tests, not one. A YouTube
transcript arrives in subtitle format, hard-wrapped to ~34-character lines. The other two are
both single blobs, so line width cannot separate them; what does is that `parsing.py` returns
markup (Exa HTML, Tavily markdown) while WhisperX returns its segments joined into plain prose
with a leading space. Testing only for wrapping silently files every audio transcript under
`web_article`, which is a stratum label that looks plausible in the UI and is wrong.

The strata are not balanced and that is **accepted**, not an oversight to fix: real traffic is
mostly transcripts, so `web_article` gets 5 items, under the ≥8–10 per cell a ranking needs. A
*web-article-specific* claim is anecdote until the stratum is seeded, while `yt_transcript` and
`audio_transcript` carry enough items to rank models. A rebuild needs a fresh harvest: traces
older than 30 days are outside the API window.

Two screening filters earn their keep on real traffic: content under ~1500 characters, and
degenerate output from `AudioTranscriber.transcribe` when WhisperX mis-decodes audio — a
distinct failure from the documented empty-transcript case, and one that reaches the model as
content rather than being dropped. Detect it by **compression ratio**, not by any single
character's share: the observed failures repeat a multi-character sequence, so one of the two
sat at 27% on its most common character and slipped a 30% threshold, while both compress to
~0.03 of their size against ~0.14 for the densest real item.

## Tier 1: binary sub-checks, never weighted points

Every rule in `prompts.py` is stated as an absolute — "Respond in {language}" has no
60%-credit reading — so a weighted composite would invent numbers and hide *which* rule broke.
The Langfuse code evaluator `tier1-on-experiments` emits `t1_language_match`, `t1_script_clean`
and `t1_bullet_count` (BOOLEAN), `t1_compression` (NUMERIC) and the derived `t1_pass`, which ANDs
the applicable binary checks. The report drops a model scoring `t1_pass` on under **95%** of
items (`stage2.PASS_THRESHOLD`) — at most two failures in 50. A 70% floor suits checks that only
catch outright breakage, but `t1_script_clean` fails an item on one stray character, and 70% would
pass `tencent/hy3`, which leaked CJK into ~6% of its summaries — enough to be unusable. Strong
models score 100%. Four judgements are deliberate:

- The language check passes at **70%** Cyrillic letters, not 95%. Correct output still carries
  Latin proper nouns, so a stricter floor rejects good summaries while adding nothing against a
  model that answered in the wrong language outright.
- **`t1_script_clean` catches what the ratio cannot: a stray foreign-script letter inside Cyrillic
  prose.** It fails on any letter outside Latin (with its extensions), Greek and Cyrillic.
  `tencent/hy3` wrote `近` and `复杂` into two of 32 summaries that the ratio passed at 0.973 and
  0.928. On a sample of 326 summaries it fired 3 times, all real. Latin stays allowed by decision
  — names and terms are legitimate — and Greek for symbols such as μ or Δ.
- `t1_compression` is a **diagnostic with no threshold**. Judges reward length, so the length
  column belongs beside every quality score; gating on it would let a model win by truncating.
- `t1_bullet_count` is emitted **only** for `key_points_for_transcript`, the one strategy that
  asks for bullets. Scoring `basic_prompt_for_transcript` zero there would penalise it for
  obeying its own prompt. So `t1_pass` ranks models **within** a strategy and must never be used
  to compare the two strategies.

**A failed generation fails Tier 1, and that is not the model's fault.** `run_experiment` stores
a task that raised as `Error: {exc}` and the Tier 1 rule scores that English string as a language
failure, so one errored item costs a model 2 points of `t1_pass`, and a provider that errors on a
few items can push a good model under the floor. `judge.run` prints a warning with the count;
read it, and the report's footnotes, before believing a Tier 1 failure.

### Three checks were removed, deliberately

**`t1_no_preamble`, `t1_no_artifacts` and `t1_bullet_purity` were removed** and should not be
reinstated without new evidence. Across 150 scored items they produced three hits and none of
them changed a decision: a markdown heading before the list, and two substring matches on
ordinary words. The false positive is the general lesson — a check that greps for the word
"transcript" fires on any summary whose *subject* is transcription, so a Tier 1 check must key
on something the content cannot legitimately contain. Tier 1 screens for outright breakage only
— wrong language, wrong script, no list where a list was asked for.

### Write portable Python in `tier1_evaluator.py`

It is executed on Langfuse's infrastructure, whose interpreter version this project neither
controls nor observes, so syntax gated on a recent Python breaks the whole evaluator into a
`SyntaxError` — no scores, and indistinguishable from a rule that never fired. This is not
hypothetical: `ruff format` rewrote `except (TypeError, ValueError):` into PEP 758's
`except TypeError, ValueError:` because the repo sets `target-version = "py314"`, which parses
on 3.14 and on nothing older. The evaluator therefore catches bare `Exception` in `_number`,
deliberately. Check any new syntax against an older interpreter, and treat `install_tier1.py`'s
preflight as the gate — it is the only thing that reports the failure.

`Score` and `EvaluationResult` are injected by that runtime and must **not** be defined or
imported, which makes every type checker report them as undefined. `ty` and `pyrefly` exclude
the directory; Pylance/Pyright is suppressed **per line**, because a file-level
`reportUndefinedVariable=false` also hides a typo'd local name — verified, a misspelled
`_cyrillic_ratio` went unreported under it. Keep the suppression narrow: a real error here is
invisible at runtime, so the editor is one of only two places it ever shows.

### A code evaluator receives every metadata value as a string, and a crash inside it is silent

`ctx.observation.metadata` is a flattened merge of OTel resource attributes, the dataset item's
metadata and the run's own metadata, and *every* value in it — item metadata included — arrives
stringified: `char_length` is `"19845"`, not `19845`, even though the dataset item stores a JSON
number. Arithmetic on such a value raises `TypeError`, which discards the whole
`EvaluationResult` — including the scores already built before the failing line. Nothing
surfaces this: the rule still reports `status: "active"`, the run completes, and the only symptom
is that no score appears. **Coerce every metadata value before using it as a number.**

The one place the failure is visible is the evaluator update (`PATCH /v2/evaluators/{id}`, run by
`install_tier1.py`), whose preflight executes the source against sample data and reports the
exception and line number — which makes reinstalling the evaluator the cheapest way to test it,
and means a rule that went active earlier is **not** evidence the code still runs.

Two consequences for scoring runs:

- **Branch on `run_prompt_key` from the run metadata, not the item's `prompt_key`.** An
  experiment applies one strategy to every item, while an item's `prompt_key` records the
  strategy of the trace it was *harvested* from; the dataset mixes strategies, so the two
  disagree and the bullet check silently applies to the wrong items. The evaluator prefers
  `run_prompt_key` and falls back to the item. So any runner calling `run_experiment` must put
  `run_prompt_key` in its run metadata; spelling it `prompt_key` there neither works nor fails —
  the evaluator reads run metadata off `ctx.observation` and item metadata off `ctx.experiment`,
  so a misnamed key overrides nothing and leaves a plausible `t1_bullet_count` computed against
  the wrong strategy.
- **Evaluators live on `v2/evaluators`; the old `unstable/evaluators` route returns 404.**
  `POST /v2/evaluators` always creates a *new* evaluator at version 1, bound to no rule, so
  re-posting the name would upload the code and score nothing. A new version is a `PATCH` of the
  existing evaluator with `type` and every definition field; rules always use the latest
  version, so the rule needs no edit. `install_tier1.py` finds the evaluator by its name,
  `tier1-on-experiments`.

### One evaluator, not one per score

Splitting `tier1-on-experiments` into one evaluator per score was considered and **deferred**.
The argument for splitting is real (the `char_length` crash destroyed the already-computed
scores along with the one that failed), but `t1_pass` cannot survive it — an evaluator cannot
read scores other evaluators wrote, so it would have to recompute every check, restoring the same
single point of failure — and each evaluator is a self-contained blob, so the shared helpers would
be copied into each and diverge silently. The cheaper equivalent, if this is revisited: keep one
evaluator and wrap each check in `try/except`. Whatever is done, `t1_pass` must **not** silently
become the conjunction of whichever checks survived. Deferring is safe because re-scoring Tier 1
costs no tokens.

## Tier 2: the judges

Two judges, both in `judge.py`, selected per run through `judge.JUDGES` (`jev`, `opus`, `none`):

| | JEV | Opus `FABRICATED` |
|---|---|---|
| Model | `typesafe/jev-1.13` | `anthropic/claude-opus-5.5`, effort `medium` |
| Score | `t2_jev_weakest`: P(supported) of the weakest bullet | `t2_fabricated`: 1 clean, 0 if anything invented |
| Cost | ~$0.02 a 50-item run | ~$2.60–2.80 a 50-item run, ~$0.06 a call |
| Used on | every candidate (default in `sweep`) | finalists only (`stage2.py judge opus`) |
| Read as | comparative signal, no floor | invented share, no floor |

Every score carries its pin in metadata — `judge_model` and `judge_prompt` (`<name>@<hash>` of the
prompt and schema). **Editing a prompt, question or schema moves the pin** and unpins it from
every banked score. The hash covers the exact string, which is why `pyproject.toml` exempts
`scripts/eval/` from `E501`: reflowing a prompt to fit the line length would repin the judge.

The judges run locally rather than as Langfuse-managed evaluators **by choice, not constraint**.
Both are per-item judgements and would fit. Two things would be given up: the **judge reports and
the runner decides** (a managed evaluator returns one numeric score plus reasoning, so it could not
carry Opus's `findings[]` or JEV's per-bullet probabilities), and the pin by hash, which a managed
evaluator would replace with Langfuse's own versioning copied into run metadata by hand. Revisit
the trade; do not assume it was forced.

### JEV: the cheap screen on every candidate

`typesafe/jev-1.13` (TypeSafe's "System One") is not an LLM: it returns typed decisions — here a
yes/no — each with a probability, and generates no text. **$0.042 per M input tokens, output
free.** It cannot be called on `chat/completions` (400: *"is a decisions model … Use the
/api/alpha/decisions endpoint"*), but **OpenRouter accepts TypeSafe's protocol on
`POST /api/alpha/decisions`** with the ordinary key, so the harness reaches it with `urllib` and
needs no pydantic-ai bump. The body is `{model, state, questions}`; each question is
`{type: "noul", instructions, criteria: {true, false}}` and the reply is `answers[name].noul`, the
probability of true. Identical calls return identical probabilities.

How it is asked, and why each choice holds:

- **One question per bullet, the source whole in `state`.** Asked once whether a whole summary is
  faithful, JEV ranked barely above chance (AUC 0.64): finding one wrong claim in a long source is
  a search, not a decision. Per bullet it reached AUC 0.75 against Opus. `state` holds the source
  alone: with the summary in it too, sources past ~50k characters returned `max_tokens_exceeded`;
  without it the longest source tried, 74k, fitted. **Never truncate the source** — every claim
  from the missing half would look unsupported.
- **All bullets in one call.** Against one call per bullet, a bullet's probability moves by a
  median of **0.000** (95th percentile 0.02, max 0.19, over 1,197 bullets) and the bill falls about
  ten times, since every call pays for the source again. The 0.19 tail can cross a fixed
  threshold, which is one more reason not to gate on one.
- **The shortest positive question** (`JEV_SUPPORTED`: *"Is this claim supported by the source?
  The claim may be a translation."*). Asked whether a claim is *invented*, with criteria written so
  `true` stayed the clean answer, JEV answered the question and ignored the polarity: AUC **0.28**.
  Longer instructions — exclusion lists, error types, a definition of a fact — made it doubt
  every bullet more without catching more errors (on 42 hand-labelled summaries: AUC **0.80** for
  the short question against 0.72 with the fact definition). JEV is not steered by being told
  more; four wordings were measured.
- **The weakest bullet stands for the summary**, since one invented claim is enough to mislead and
  an average would let ten sound bullets hide it. `JEV_FLAG_BELOW = 0.6` was the best balance on
  the 42 labels and is a reading aid for the report's `jev<0.6` column, not a gate.

**It is a coarse screen; Opus is what separates finalists.** Read comparatively, JEV ordered the
top of a 13-model queue the way Opus did and separated a model that fabricates more from the
production model (p = 0.011). But on two models it flagged 4% and 0% of summaries where Opus found
something invented in 28% and 18%. JEV rarely invents a fault and **under-rates real ones** — its
probabilities sit in a narrow band (median weakest bullet ~0.9 on clean summaries).

### Opus `FABRICATED`: the finalists' judge

`FABRICATED` asks for every claim the source does not support, each sorted into one of two kinds:
**invented** — no basis in the source or the source says otherwise (a name, number, date, event or
actor it does not have; done stated as not done) — and **compression** — merged, generalised,
re-emphasised, slightly over- or understated, rounded, with "when a claim could be either, it is
compression". Only *invented* fails the summary; compression is counted in the score's metadata
and comment and moves nothing, because whether it matters is a reader's taste.

**Why this judge is trusted.** A human reader went through the 102 findings `FABRICATED` produced
on 29 summaries (30 invented, 72 compression), checked most of the invented ones against the full
sources and agreed with every one checked — including several on summaries they had earlier
labelled clean. What they had rejected in earlier Opus verdicts was what this prompt sorts as
compression. It is **not certified** in the calibration sense: there is no fresh blind sample,
and not every invented finding was checked.

**Why only on finalists.** ~$3 a candidate is small once but adds up across a queue: ten
candidates, the size a queue reaches after a month or two of releases, is ~$30 — for a small
bot, more than its own monthly token spend.

Three details of the call are load-bearing:

- **The judge enumerates; it never returns a count.** A model that declares a number before its
  reasoning commits to it before it has thought — one verdict's reasoning ended *"retracting to 0
  unsupported"* while the emitted count stayed 1 — and a truncated reply then loses the grounds for
  a number already asserted. An enumerated list loses only its tail, and the runner counts.
- **Opus 5.5 rejects a forced tool call**: every provider OpenRouter routes it to answers 400,
  *"tool_choice: type "tool" and "any" are not supported for this model"*, and `urllib` surfaces
  only `HTTP Error 400: Bad Request` — read the body. `ask_fabricated` asks for the schema through
  `response_format: json_schema` instead, which returns clean schema-conforming JSON.
- **OpenRouter does not enforce `required`**, so a truncated or lazy reply can arrive short a
  field. `ask_fabricated` raises rather than scoring a partial; `stage2.py judge` catches it per
  item, names the item and carries on. Opus can also refuse with `finish_reason: content_filter`
  on innocuous content (once, on a summary of a Go-language blog post), which surfaces the same
  way.

**Judge spend is measured, not estimated.** Every call sets `usage: {include: true}`, so
OpenRouter prices it and the evaluator stores `cost` in the score metadata; `stage2.py judge`
totals it. **Never quote a judge's cost from the catalog — measure a round.** The card has been
wrong every time it was checked: Sonnet 5 promised 5× cheaper than Opus 5 and gave 2.2×;
`gpt-5.6-sol-pro` promised 2.5× and cost the same ($0.057 against $0.058 a call — the saving went
on reasoning tokens); Opus 5.5 promised 20% off Opus 5 and cost $0.060 a call against $0.058.

### Choosing a judge model: the two constraints

**The judge's family must not appear in the candidate pool** — a judge scoring its own family
favours it. **And the judge must outrank the candidates** — judging mid-tier output with a
mid-tier model measures the judge's ceiling. Re-check both whenever a candidate from the judge's
family is evaluated. The judge is pinned by model id, reasoning effort and prompt hash — not by
temperature, which frontier models increasingly reject outright.

**Weigh the direction of a judge's errors, not only its agreement.** A judge that misses faults
under-detects and punishes nobody; a judge that invents them **penalises good models**, which is
the thing the score exists to prevent. Sonnet 5 and JEV under-rate real errors; `gpt-5.6-sol-pro`
and `gpt-6-luna` invent them.

## Rejected, and why

Each of these was built, measured and removed. The code is in git history; the lessons are here
so none of it is rebuilt without them.

- **Coverage via a key-facts checklist (`t2_coverage`, `checklists.py`).** A strong model
  extracted the points a summary must not omit, a human edited the list, and a judge scored
  coverage against it. Neither a model nor a human could cut a list to a cap consistently (of 17
  drop decisions, the two agreed on 2), atomic facts pulled toward figures and names (48% of facts
  were supporting detail) while the product asks for ideas, and the uncapped list read as a table
  of contents. The deciding argument: the harness evaluates a model under the product prompt, so
  labels belong on its summaries, not on a competing reference. Generation cost ~$0.06–0.08 an
  item — the bill is the source, not the reply.
- **Omission by binary questions.** Two rounds of yes/no questions (main takeaway, major topics,
  ending, advice, repetition) on production summaries: in the second round Opus answered true on
  all five questions for all 48 summaries, including a model whose summaries were ~23% shorter.
  Any competent key-points summary passes them on sources under ~45k characters, so they cannot
  rank candidates. Omission currently has no metric.
- **`t2_no_filler`.** Never calibrated, so in a filter it would drop models on an unchecked
  judgement, and padding is visible the moment a survivor is read.
- **Tier 3 pairwise readability.** Never calibrated — best round 78% agreement but kappa 0.23 on
  a 19/5/1 label split. Two lessons outlive it. **What a pairwise judge decides on is whatever the
  prompt fails to exclude**: accuracy, output language and retained coverage each crept in, each
  looked like a miscalibrated judge, and each was found by reading the judge's own reasons on the
  disagreements — do that before paying for any round. And **a skewed or TIE-heavy label split
  collapses kappa** however good the judge; kappa is comparable between judges only at comparable
  discard rates. An evaluator sees one item, so pairwise can never be a Langfuse evaluator;
  readability is judged by reading the survivors.
- **Faithfulness with a severity gate (`FAITHFULNESS`, `t2_faithfulness`, Opus 5).** It
  enumerated findings graded material/minor/borderline and failed a summary on any *material*
  one, with an 85% floor. Calibrated at **88% agreement / kappa 0.65** on 24 hand-labelled items.
  When the judges' disagreements were later hand-labelled, **5 of Opus's 8 material flags were not
  errors to the labeller** — the line between distortion and compression is a reader's judgement.
  `FABRICATED` replaced it by making that line explicit and failing only on invented facts.
- **Cheaper judges for faithfulness**, all against Opus's verdicts: Sonnet 5 (64% / kappa 0.32,
  grading real errors `minor`); `gpt-5.6-sol-pro` (80% / 0.56, four false alarms, no cheaper);
  `gpt-6-luna` (caught 4 of 8 with **16** false alarms on 98 summaries, $0.145 — cheap, wrong);
  Opus 5.5 on the old prompt (no cheaper, no better: 1 of 3 errors, 4 false alarms on 22 labels).
  JEV as a whole-summary judge (AUC 0.64) and in six per-bullet variants — what survived is the
  one described above.
- **A one-question prompt (`INVENTED`).** "Does the summary state a fact the source does not
  contain", no types, any finding fails. On 42 labelled summaries it caught **all 6** errors but
  flagged 23 of 36 clean ones, a mix of real fabrications and compression artefacts that could be
  neither accepted nor rejected as a set — which is what `FABRICATED`'s two kinds sort.
- **Calibrating per summary against hand labels.** Two labelling rounds (22 and 20 summaries) and
  a dispute round. Labels made from a passage a model chose inherit the model's choice — a mention
  outside the quoted passage was labelled invented, and a passage pointing the wrong way was
  labelled clean — so **judge-vs-labeller disagreements must be adjudicated against the full
  source before they are counted**, and a review aid should find deciding passages by plain
  search, not by a model. Labellers did not converge on "distortion vs compression", so no judge
  is certified per summary and none sets a floor.
- **A separate screening stage (`stage1.py`, 25 items, Tier 1 only).** Once the compare run
  carried Tier 1 and a two-cent judge, a separate cheaper run saved nothing worth a second step.

## The report

`stage2.py report` aggregates every compare run on the dataset — what the API does not provide —
into one markdown table, readable in a terminal and pasteable into a document.

- **Layout.** One row per candidate: `t1_pass`, JEV median and share below `JEV_FLAG_BELOW`,
  Opus's invented share (`—` where Opus was not run), compression, median latency, `run $`.
  Kept candidates come first — those Opus judged by invented share, the rest by JEV median —
  and dropped ones follow, marked `— DROP`. The best value of each column among kept
  candidates is bold; higher compression counts as better, since a longer summary that keeps
  more detail is preferred.
- **Footnotes replace a coverage warning.** A row whose numbers cover fewer items than the run
  gets a numbered note: items that failed to generate (an `Error:` output, or an empty one from
  an item killed mid-generation), a judge that scored fewer items than generated, or
  generations with no price. Read them before believing a Tier 1 failure.
- **The filter is Tier 1 only.** `DROP` is `t1_pass` below `PASS_THRESHOLD`; the judges set no
  floor.
- **A mean never ranks a model, so `--all-pairs` exists.** With 50 items a few points between
  two means can be noise. The flag adds, per Tier 2 score, a sign test over *per-item* deltas
  for every pair of candidates on the same items — controlling for item difficulty is worth
  roughly 3–4× the sample size. Two models 0.02 apart on a mean have split 5 better / 6 worse
  per item, p = 1.000; and an invented share of 14% against 27% was p = 0.109, while 8% against
  27% was p = 0.022. Use it before choosing between finalists; it is off by default because the
  matrix grows with the square of the candidates (78 JEV rows for 13).
- **A candidate is a model *and* a strategy.** `t1_pass` and the Tier 2 means rank models only
  within one strategy, so runs are keyed `<model> / <prompt_key>` throughout; the strategy is
  shown only when it is not the default one.
- **Compare runs carry a `stage2 / ` prefix.** `GET /experiments` returns seven fields and none of
  them is metadata, so which candidate produced a run is readable *only* from its name. Anything
  that discovers runs parses names, and renaming a run orphans it from the report. That is also
  why `stage2.py` and its prefix keep the old stage number though only one stage is left: a new
  prefix would hide every banked run, and experiments cannot be renamed. Langfuse appends a
  timestamp, and the newest run per candidate wins, so a botched run is superseded by re-running
  the candidate rather than deleted (nothing deletes an experiment).
- **`run $` is what OpenRouter charged for the 50 summaries**, summed from each generation's
  `totalCost` — which `v2/observations` returns only when the `usage` field group is requested; it
  is absent, not `null`, otherwise. One paginated read over the run's time window, filtered to the
  run's own traces so the bot's traffic in the same window is excluded. Judge calls are not on
  these traces. Measured runs have come in well under catalog estimates ($0.12 against $0.28 for
  one model).
- **Tier 2 scores are read from `v3/scores` by name**, not from the experiment items — see the
  seven-score cap under *API shapes*.

## API shapes that cost real time to rediscover

- **The experiment-items read returns at most seven scores per item.** An item carrying five
  Tier 1 scores, a retired Tier 2 score, JEV and then `t2_fabricated` came back without the eighth,
  and the report showed "-" for scores that existed. `stage2.py` reads Tier 2 scores by name from
  `v3/scores` and merges them in; inline scores still serve Tier 1.
- **Nothing in v4 deletes an experiment.** `experiments` and `experiment-items` expose `list`
  only. The deprecated v3 `DELETE /datasets/{name}/runs/{runName}` returns **200** and clears the
  run from the v3 view, but the v4 experiment and its items survive. Plan for junk runs to be
  superseded by newer ones rather than removed.
- **A score's value: the OpenAPI spec and the live API disagree, and the live one wins.** The spec
  declares `CategoricalScore.value` a *number* with the label in `stringValue`; `GET /v3/scores`
  actually returns `value: "A"` with `stringValue` absent. BOOLEAN is the same shape. Reading only
  one field yields `None` or `0` for every verdict, which looks exactly like a judge that never
  ran. `langfuse_api.score_value(row)` is the one decoder; do not read `value` off a score row
  directly, and do not "correct" it to match the spec.
- **`subject` is its own `fields` group on `GET /v3/scores` and must be requested.** Without it a
  score row carries **no target at all**, and code mapping scores back to items matches nothing.
  Scores returned *inline* by `fields=core,scores` on `GET /experiment-items` carry `subject`
  without being asked.
- **Score configs are archived, not deleted** (`PATCH /score-configs/{id}` with
  `isArchived: true`, or Project Settings → Scores / Evaluation in the UI); the scores themselves
  are untouched. A score needs no config to be written — `t1_script_clean`, `t2_jev_weakest` and
  `t2_fabricated` have none — so a config is only worth creating for a score a human labels.
- **No API route updates or deletes an annotation queue** — `/annotation-queues/{queueId}` is GET
  only; only its items can be changed. The UI can attach a score config to an existing queue and
  can delete one. Labels are scores on observations, so they survive their queue.
- **A `402` from OpenRouter usually means the API key's own limit, not an empty account.** The
  body says `limit_source: openrouter_key_limit`. OpenRouter reserves the **maximum possible** cost
  of a call — prompt plus the whole `max_tokens` — so a request is refused on `max_tokens` alone
  while the balance shows plenty, and the failure is per request: judge calls (8,000 tokens) kept
  working while candidate generation (65,536) did not. Raising the key's monthly limit, not topping
  up the balance, is the fix. If the bot shares the key, it fails too while the limit is
  exhausted. When the body does *not* name the key limit, check the credit balance
  (`/api/v1/credits`), not the key (`/api/v1/key`) — a round once died with $3.79 left because one
  call carried a full-size source.
- **A failed task is stored, not lost, and a partly failed run reads as a bad model.**
  `run_experiment` catches whatever the task raises, writes `Error: {exc}` into the item's output
  and skips that item's Tier 2 evaluators. The Tier 1 rule still fires on the error string: a sweep
  that lost 36 of 49 items to `402` reported `t1_pass` 0.245 — a plausible verdict about a model
  that never answered. `judge.run` counts `Error:` outputs and warns while there is still a sweep
  to stop.
- **A Langfuse score requires a target.** Passing `trace_id=None` fails with a bare `Bad request`
  while the calling code still prints success. `stage2.py judge` anchors a backfilled score to the
  experiment item's observation (the item's `id`), exactly as `run_experiment` does — the trace
  alone would be missing from the experiment-items read.
- **Dataset run names embed the model id**, so they contain `/` and spaces and must be URL-encoded
  into REST paths or the segments split and the request 404s.

## Latest results (snapshot of 2026-09-28)

A snapshot, not a reference: models change and this table goes stale. Re-run the report before
acting on it. One run per model on the 50 items, thinking `medium`, `key_points_for_transcript`;
`openai/gpt-5.6-luna` was the production model.

| candidate | t1_pass | JEV median | JEV < 0.6 | invented (Opus) | compression | latency | run $ |
|---|---|---|---|---|---|---|---|
| `x-ai/grok-4.7` | **100%** | 0.93 | 0% | **8%** | 0.200 | 23.4 s | 0.75 |
| `deepseek/deepseek-v4.1-flash` | 96%¹ | **0.94** | **0%** | **10%** | **0.229** | 15.9 s | 0.16 |
| `openai/gpt-6-luna` | 98% | **0.94** | 2% | 14% | 0.171 | 19.5 s | **0.04** |
| `xiaomi/mimo-v2.6-pro` | 98% | 0.93 | 0% | 18% | 0.187 | 37.2 s | 0.17 |
| `openai/gpt-5.6-luna` (production) | 98% | 0.92 | 6% | 27% | 0.220 | 20.7 s | 0.12 |
| `z-ai/glm-5.3-flash` | 98% | 0.92 | 4% | 28% | 0.166 | **10.6 s** | 0.05 |
| `meta/muse-spark-1.3` | 96%¹ | 0.92 | 4% | — | 0.197 | 18.8 s | 0.76 |
| `upstage/solar-pro4` | 98% | 0.92 | 0% | — | 0.158 | 35.7 s | 0.09 |
| `stepfun/step-3.7-flash` | 96% | 0.89 | 12% | — | 0.202 | 14.1 s | 0.20 |
| `tencent/hy4-preview` — DROP | 92% | 0.93 | 2% | — | 0.261 | 105.6 s | 1.11 |
| `inception/mercury-2.5` — DROP | 92%² | 0.91 | 2% | — | 0.071 | 5.3 s | 0.02 |
| `xiaomi/mimo-v2.6-flash` — DROP | 76% | 0.92 | 2% | — | 0.205 | 25.1 s | 0.06 |
| `ibm-granite/granite-4.2-8b` — DROP | 62% | 0.80 | 26% | — | 0.178 | 20.6 s | 0.03 |

¹ one errored item. ² four errored items; 100% on the 46 it answered.

- **Tier 1 dropped four.** granite answered in English on a third of the items; mimo-v2.6-flash
  (20%) and hy4-preview (8%) leaked foreign-script letters; mercury-2.5's drop is its provider's
  errors, and it writes a third the length of anyone else.
- **Opus on six finalists** ($16.33), paired on invented against production: grok-4.7 11 / 2,
  **p = 0.022**; deepseek-v4.1-flash 9 / 1, **p = 0.021**; gpt-6-luna 8 / 2, p = 0.109;
  mimo-v2.6-pro p = 0.454; glm-5.3-flash 9 / 9, p = 1.000. grok and deepseek do not separate from
  each other (2 / 3, p = 1.0); deepseek writes the longest summaries at a fifth of grok's cost.
- **Next step, not yet taken:** add a finalist (deepseek-v4.1-flash and/or gpt-6-luna) to
  `config.MODEL_SPECS` and read it live in the bot.
