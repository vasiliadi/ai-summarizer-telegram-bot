# Evaluation

How summarization quality is measured: the Langfuse dataset built from real traces, the scoring
tiers, the judges, and the harness in `scripts/eval/`.

Nothing here is imported by the bot — these are operational scripts, run by hand.
`architecture.md` owns the bot itself, including *how* it emits the traces this is built on;
read its **Tracing** bullet before changing anything that produces trace data.
The operator's setup and run steps live in `scripts/eval/README.md`; edit them there, and keep the
why here.

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

### `anthropic/claude-opus-5.5` in the registry is never evaluated

It is registered for the rare reference summary a user picks by hand, not as a production
candidate, and it is expensive. Do not sweep it, judge it, or put it in a report or a
comparison; leave it out of any re-check of the registered models. It is also the
`FABRICATED` judge, and a judge scoring its own output fails the family rule under *Choosing
a judge model*. `stage2.py` enforces it against `judge.FABRICATED_MODEL`: `sweep` refuses the
id, and `discover_runs` skips its runs, so `report` and `judge` never see one.

### Everything runs over OpenRouter, and models are named by their OpenRouter id

The harness never consults `config.MODEL_SPECS`. Model ids are passed as arguments, always,
with no default list — requiring a model to be registered before it can be evaluated would
invert the tool.

**Do not add a default list back.** The set worth evaluating is different every time, and in
steady state a new model shows up on its own — vendors do not ship on the same day — so the
normal invocation is one id, and a constant would be stale the week after it was written.

The bot reaches every model over OpenRouter as well, through the same client, so a candidate
is measured on the route it would be served on.

**Never derive an OpenRouter id by prefixing a vendor name.** The catalog carries `:free` and
`:batch` siblings next to the plain id, so a computed id can silently select a different model
and bill for it. `stage2.py sweep` validates every id against the catalog and refuses to start
otherwise, printing the near-misses.

### A candidate's route

Nothing below needs the model to be in `config.MODEL_SPECS`, and it should not be added until
the end:

1. **One compare run.** `stage2.py sweep <openrouter-id> ...` summarises the 50 items of
   `summarization-compare-v1` through `eval_client.summarize`. The run gets the Tier 1 scores
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
   or renaming one does — see the registry bullet in `architecture.md`. Set `supports_files`
   from a document probe, not from the catalog (`architecture.md`, *Modality routing*).
6. **Sweep thinking levels** on the chosen model only, and expect to decide it on cost and
   latency rather than quality, because adjacent levels rarely separate.

Track cost and latency beside quality throughout; quality alone always picks the most expensive
configuration. Below ~30 items report gross failure rates only, never rankings. Keep the dataset
afterwards as a regression gate for prompt edits, not only for model launches.

### The candidate summarises through the bot's client; the judges do not

`eval_client.py` holds `LLM`, an `LLMClient` on the bot's own `config.openrouter_client`, and
the one `THINKING_LEVEL` every run uses. `LLMClient` never consults the model registry, so an
unregistered candidate runs on it unchanged, through the same traced call the bot makes: the
generation records what OpenRouter charged, and the request carries the bot's instructions and
thinking level. A candidate's cost and latency are half of the question, so they have to be
produced on the bot's own terms.

**An experiment task must be `async def` and reach the model through
`eval_client.summarize`.** `run_experiment` awaits the task inside its own running event loop,
and `LLMClient.run` is a blocking call: made directly, it would hold the loop for the whole
generation, so items would run one at a time and no timeout could end a hang. `summarize` hands
the call to a worker thread and awaits its answer. The context is copied into the thread, so the
generation still nests under the experiment item.

The **judges** stay on their own HTTP calls in `judge.py`, deliberately. Opus needs structured
output against a JSON schema, which `LLMClient` does not do and the bot never asks for, and JEV
is not a chat model at all. What a judge spends is a cost of running the evaluation, not a
property of the model being ranked, so it does not belong on the candidate's trace either.

Skipping `LLMClient` also skips its OpenRouter attribution, so `judge._post` sets
`HTTP-Referer`/`X-Title` by hand from `config.OPENROUTER_APP_URL`/`OPENROUTER_APP_TITLE`
(`architecture.md`, *OpenRouter calls identify the app*); any new direct OpenRouter call must
do the same. The candidate path inherits them from `config.openrouter_client`. Eval
spend is deliberately *not* separated from the bot's in OpenRouter's app ranking — it is this
repo's spend, and a second referer would split it into a second Top Apps entry.

## The harness

| File | Purpose |
|---|---|
| `_bootstrap.py` | Loads `.env`, puts `src/` on the import path, returns Langfuse REST credentials |
| `eval_client.py` | `LLM`, `summarize` with its generation timeout, and `THINKING_LEVEL` |
| `langfuse_api.py` | The only place that calls the Langfuse REST API. v4 endpoints, rate-limit aware |
| `tier1_evaluator.py` | Tier 1 deterministic scorers. Uploaded to Langfuse, **executed there** |
| `install_tier1.py` | Uploads the above. Its preflight is the only way to see the evaluator crash |
| `judge.py` | The two Tier 2 judges (JEV, Opus `FABRICATED`) and the compare-run task. Imported, not run |
| `stage2.py` | The command line: `sweep`, `report`, and `judge`, which adds a judge to existing runs |
| `rebuild_datasets.py` | Rebuilds the dataset from a raw harvest. Destructive; needs `--yes-wipe` |

The commands are in `scripts/eval/README.md`.

**The harness is tested but sits outside the 100% coverage rule.** `tests/test_eval_*.py` cover
what fails silently — the seam with `src/` (`eval_client` on `LLMClient`), the Tier 1
checks and their portability, how each judge's answer becomes a score, and the report's
arithmetic — and the pytest hook runs them on any change under `scripts/eval/`. The CLI entry
points and thin network wrappers (`install_tier1.py`, `main()`, `wipe`/`push`, `report`/`sweep`)
are untested on purpose, so `[tool.coverage.run]` measures `src/` only and the project's 100%
stays about the bot. To see the harness's own coverage:

```bash
uv run pytest tests/test_eval_*.py --cov=scripts/eval
```

**A run is always the whole dataset.** The report reads the newest run per candidate, so a short
probe run made after a full one would replace it there; there is no item limit to pass.

**Generation times out after 10 minutes, so one hung item cannot stall a sweep.**
`eval_client.summarize` runs each generation on a **daemon** thread and waits
`GENERATION_TIMEOUT` (600 s); a stuck item is stored as a named `TimeoutError` and the run
finishes. Sweeps did hang on the candidate generation under pydantic-ai; whether the `openai`
client can still hang is untested, so keep the guard. It must be a daemon thread:
`asyncio.to_thread` uses the default executor, whose threads are joined at interpreter exit, so
a timeout around it would only move the hang to shutdown. A worker that returns after its item
timed out may find the experiment's loop closed; its answer is dropped quietly. To see where a
live sweep is stuck: `sudo "$(which uvx)" py-spy dump --pid <pid>` (macOS needs `sudo`).

**Wait a minute after a run before reading its report.** Langfuse ingests experiment items and
scores asynchronously, taking tens of seconds, so a report read straight after a run shows fewer
items or scores than were written — which looks exactly like a judge that silently failed.
`report` flags missing items itself (below); for scores, check the `JEV scored N of 50` and
`Opus scored N of 50` footnotes before trusting a row.

### A run can lose items on the way to Langfuse

A compare item reaches Langfuse as OpenTelemetry spans, exported in batches. A batch that
fails to export is dropped, logged once (`Failed to export spans batch`), and the run carries
on: the lost items simply never exist. At the SDK's default 5 s timeout one sweep lost three
`anthropic/claude-haiku-5.5` items this way, and nothing but a judge scoring 47 of 50 showed it.
`config` therefore gives the client 30 s (`LANGFUSE_TIMEOUT` overrides it), which the SDK
passes on to the span exporter. The harness inherits it: the SDK keeps one resource manager
per public key, so the `Langfuse()` in `judge.run` reuses the one `config` built.

`report` compares each run's item count with the dataset size and marks a short run
`INCOMPLETE`, footnoted `N of 50 dataset items missing from the run`, so it can win no column.
Re-sweep the candidate: the missing items were generated and paid for, but cannot be recovered.
Straight after a run the same note can mean ingestion has not caught up; wait a minute and
read again before re-sweeping.

Anything that only reads is free. Re-scoring Tier 1 never costs anything — the summaries already
exist as trace outputs, so a broken scorer is repaired by reinstalling it and recomputing, not by
re-generating. Only Tier 2 spends money on a re-score.

### Harness runs report to Sentry as `eval`

Every script here imports `config` from `src/`, which initialises Sentry from the bot's `.env`
and enables `LoggingIntegration(capture_sentry_logs=True)`. So a sweep reports to the bot's
Sentry project: the OpenAI integration captures a candidate's `RateLimitError`, and Langfuse's
`Item N failed` log line arrives at `ERROR`. One rate-limited candidate (a provider's shared
pool returning 429) raised about a hundred events in a single sweep.

`_bootstrap.load()` sets `SENTRY_ENVIRONMENT=eval`, overriding `.env`, before anything imports
`config`. The SDK reads that variable at `init`, so harness events are filed under `eval` and an
alert rule can leave them out. Sentry stays on because a harness crash is still worth recording;
the per-item failures are already in the report as `N of 50 items failed to generate`.
Without the tag, tell harness events apart by `sys.argv` in the event's extra data: they carry
`scripts/eval/...`, and `Users Impacted` is 0.

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
  dataset rebuild. Add reads there rather than scattering `requests` through the scripts. The SDK
  covers datasets and experiments; scores, evaluators and evaluation rules go over REST because
  the SDK does not wrap the routes this project needs.
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

Two traps:

- The public API **rate-limits** — 30 requests per window, and a 429 carries
  `details.retryAfterSeconds` — and that retry delay must be **obeyed**. Blind
  exponential backoff does not converge, because every retry spends another request. An
  unchecked rate-limit response also falls through `.json().get("data", [])` as an empty list,
  indistinguishable from a model that genuinely scored nothing.
- Paginate on the cursor the response actually returns, `meta.cursor`. Guessing a plausible field
  name (`meta.nextCursor` does not exist) yields `None` and silently truncates a sweep at the first
  page.

## Running an experiment: UI vs script

Both produce experiments the Tier 1 rule scores, but they measure different things. The
difference that generates all the others: **through the UI, Langfuse calls the model; through
the script, your code does.**

| | UI Prompt Experiment | `scripts/eval/stage2.py sweep` |
|---|---|---|
| Who calls the model | Langfuse, via an LLM Connection | your code, locally |
| Prompt source | the Langfuse mirror | `src/prompts.py` directly |
| Code path | Langfuse's request builder | `llm.LLMClient` — the bot's path |
| Thinking level | not applied | sent as `reasoning.effort` |
| Cost | Langfuse's own pricing | what OpenRouter charged, from the reply's `usage.cost` |
| `environment` | `langfuse-prompt-experiment` | `sdk-experiment` |
| Tier 1 | fires | fires |
| Tier 2 | not possible | `run_experiment(evaluators=[…])` |
| In git | no | yes |

A UI run has neither OpenRouter's cost nor a thinking level — it measures a call the bot never makes. Use
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
the trace's summary — never to the model's thinking, which is often in English — and skips a
trace with no `target_language`. No language is named, so any
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
Replicate audio transcript are therefore all tagged `text`, and no field distinguishes
them — the stratum has to be inferred from the content, by **two** tests, not one. A YouTube
transcript arrives in subtitle format, hard-wrapped to ~34-character lines. The other two are
both single blobs, so line width cannot separate them; what does is that `parsing.py` returns
markup (Exa HTML, Tavily markdown) while WhisperX returns its segments joined into plain prose
with a leading space. Testing only for wrapping silently files every audio transcript under
`web_article`, which is a stratum label that looks plausible in the UI and is wrong.

A Castro transcript is a fourth source with **no stratum of its own**: it is one line per
utterance, and the one episode measured (2026-10-02) averaged 64 characters a line without
timestamps — just over the 60 below which `stratum_of` calls a transcript YouTube. Timestamps,
when Castro has them, add about 8 characters a line, so `stratum_of` files such an episode under
`audio_transcript`; one without them can land in either stratum, by its line width. Each line opens with that
timestamp and a speaker label (`[00:16] Speaker: …`), which neither other transcript shape
has, if a rebuild needs to tell them apart.

The strata are not balanced and that is **accepted**, not an oversight to fix: real traffic is
mostly transcripts, so `web_article` gets 5 items, under the ≥8–10 per cell a ranking needs. A
*web-article-specific* claim is anecdote until the stratum is seeded, while `yt_transcript` and
`audio_transcript` carry enough items to rank models. A rebuild needs a fresh harvest: traces
older than 30 days are outside the API window.

### A harvest holds two trace shapes

`rebuild_datasets.py` reads a generation's `input` and `output` as JSON, and what is in them
depends on what traced the call. Langfuse's `openai` drop-in records the request's `messages` —
`[system, user]`, the user `content` a list of `{"type": "text", "text": …}` parts — and the
reply as one `{"role": "assistant", "content": …}` object, with no thinking in it (observed
2026-10-02). pydantic-ai recorded `parts` with a `content` key on both sides, thinking parts
included. `content_of` and `summary_of` read both, because a harvest's 30-day window can span
the switch; a row in neither shape is skipped without a word, like any unparsable row. The
`parts` branch is dead once no pydantic-ai trace is left inside the window.

Two screening filters earn their keep on real traffic: content under ~1500 characters, and
degenerate output from `AudioTranscriber.transcribe` when WhisperX mis-decodes audio — a
distinct failure from the documented empty-transcript case, and one that reaches the model as
content rather than being dropped. Detect it by **compression ratio**, not by any single
character's share: the failures repeat a multi-character sequence, so no one character
dominates, while they compress to ~0.03 of their size against ~0.14 for the densest real item.

## Tier 1: binary sub-checks, never weighted points

Every rule in `prompts.py` is stated as an absolute — "Respond in {language}" has no
60%-credit reading — so a weighted composite would invent numbers and hide *which* rule broke.
The Langfuse code evaluator `tier1-on-experiments` emits `t1_language_match` and `t1_script_clean`
(BOOLEAN), `t1_compression` (NUMERIC) and the derived `t1_pass`, which ANDs the binary checks.
The report drops a model scoring `t1_pass` on under **95%** of items (`stage2.PASS_THRESHOLD`) —
at most two failures in 50. A looser floor would pass a model that leaks foreign script into a
few percent of its summaries, which is enough to be unusable; strong models score 100%. Three
judgements are deliberate:

- The language check passes at **70%** Cyrillic letters, not 95%. Correct output still carries
  Latin proper nouns, so a stricter floor rejects good summaries while adding nothing against a
  model that answered in the wrong language outright.
- **`t1_script_clean` catches what the ratio cannot: a stray foreign-script letter inside Cyrillic
  prose.** It fails on any letter outside Latin (with its extensions), Greek and Cyrillic; two CJK
  characters in a 2,000-letter summary move the ratio by 0.1%. Latin stays allowed — names and
  terms are legitimate — and Greek for symbols such as μ or Δ.
- `t1_compression` is a **diagnostic with no threshold**. Judges reward length, so the length
  column belongs beside every quality score; gating on it would let a model win by truncating.

**Tier 1 screens for outright breakage only — wrong language, wrong script.** Checks for a
preamble, artifacts, bullet purity and a minimum bullet count were removed because none ever
changed a decision; a format problem is visible the moment the survivors are read. Do not add a
check without evidence it would drop a model, and key it on something the content cannot
legitimately contain — a grep for "transcript" fires on any summary *about* transcription.

A failed generation also fails Tier 1 (see *A failed task is stored* under *API shapes*); read
`judge.run`'s warning and the report's footnotes before believing a Tier 1 failure.

### Write portable Python in `tier1_evaluator.py`

It is executed on Langfuse's infrastructure, whose interpreter version this project neither
controls nor observes, so syntax gated on a recent Python breaks the whole evaluator into a
`SyntaxError` — no scores, and indistinguishable from a rule that never fired. Ruff targets
`py314`, so `ruff format` rewrites `except (TypeError, ValueError):` into PEP 758's
`except TypeError, ValueError:`, which parses on nothing older; that is why `_number` catches
bare `Exception`. Check any new syntax against an older interpreter, and treat
`install_tier1.py`'s preflight as the gate — it is the only thing that reports the failure.

`Score` and `EvaluationResult` are injected by that runtime and must **not** be defined or
imported, which makes every type checker report them as undefined. `ty` and `pyrefly` exclude
the directory; Pylance/Pyright is suppressed **per line**, because a file-level
`reportUndefinedVariable=false` also hides a typo'd local name. Keep the suppression narrow: a
real error here is invisible at runtime, so the editor is one of only two places it ever shows.

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

- **A check that depends on the strategy must branch on `run_prompt_key` from the run
  metadata, not the item's `prompt_key`.** No check does now, but `judge.run` still records
  `run_prompt_key`. An experiment applies one strategy to every item, while an item's `prompt_key` records the
  strategy of the trace it was *harvested* from; the dataset mixes strategies, so the two
  disagree. Spelling it `prompt_key` in run metadata neither works nor fails — the evaluator
  reads run metadata off `ctx.observation` and item metadata off `ctx.experiment`, so a
  misnamed key overrides nothing and the check silently uses the wrong strategy.
- **Evaluators live on `v2/evaluators`; the old `unstable/evaluators` route returns 404.**
  `POST /v2/evaluators` always creates a *new* evaluator at version 1, bound to no rule, so
  re-posting the name would upload the code and score nothing. A new version is a `PATCH` of the
  existing evaluator with `type` and every definition field; rules always use the latest
  version, so the rule needs no edit. `install_tier1.py` finds the evaluator by its name,
  `tier1-on-experiments`.

### One evaluator, not one per score

Splitting `tier1-on-experiments` into one evaluator per score was **deferred**. An evaluator
cannot read scores other evaluators wrote, so `t1_pass` would recompute every check anyway, and
each evaluator is a self-contained blob, so shared helpers would be copied and diverge. If one
crashing check becomes a problem, wrap each check in `try/except` instead — but `t1_pass` must
**not** silently become the conjunction of whichever checks survived.

## Tier 2: the judges

Two judges, both in `judge.py`, selected per run through `judge.JUDGES` (`jev`, `opus`, `none`):

| | JEV | Opus `FABRICATED` |
|---|---|---|
| Model | `~typesafe/jev-latest` | `anthropic/claude-opus-5.5`, effort `medium` |
| Score | `t2_jev_weakest`: P(supported) of the weakest bullet | `t2_fabricated`: 1 clean, 0 if anything invented |
| Cost | ~$0.02 a 50-item run | ~$2.60–2.80 a 50-item run, ~$0.06 a call |
| Used on | every candidate (default in `sweep`) | finalists only (`stage2.py judge opus`) |
| Read as | comparative signal, no floor | invented share, no floor |

Every score carries its pin in metadata — `judge_model` and `judge_prompt` (`<name>@<hash>` of the
prompt and schema). **Editing a prompt, question or schema moves the pin** and unpins it from
every banked score. The hash covers the exact string, which is why `pyproject.toml` exempts
`scripts/eval/` from `E501`: reflowing a prompt to fit the line length would repin the judge.

**JEV's `judge_model` is an alias; `judge_model_version` is the judge.** JEV is asked for as
`~typesafe/jev-latest`, and OpenRouter names the snapshot that answered in the reply's `model` —
`typesafe/jev-1.13-20260917` on 2026-09-30, for both the alias and `typesafe/jev-1.13`, which is
itself an alias. Each JEV score records that snapshot as `judge_model_version`. **When the alias
moves, rescore**: `stage2.py judge jev --rescore` scores every compare item again (well under a
dollar), and the report reads the newest score per observation, so the old ones are superseded
rather than deleted. Plain `judge jev` only fills missing scores, so without the rescore a report
mixes two judges. `stage2.py report` prints which snapshots scored it (`JEV answered as ...`) and
warns, per candidate, once more than one appears; a score with no version is shown as
`unrecorded` and counts as a judge of its own. Everything measured on JEV below — the question
wording, `JEV_FLAG_BELOW` — was measured on 1.13 and would need re-checking on a new snapshot.

The judges run locally rather than as Langfuse-managed evaluators **by choice, not constraint**.
An LLM-as-a-judge evaluator returns one typed score plus reasoning, so it could not carry Opus's
`findings[]`. A decision-model evaluator can call Jev, but its questions are fixed when it is
saved, one score each (Langfuse docs, 2026-10-07): it cannot ask one question per bullet of a
summary whose length varies, the weakest-bullet score would still need our code, and TypeSafe's
32k-token input cap applies there too. Either kind would replace the pin by hash with Langfuse's
own versioning. Revisit the trade; do not assume it was forced.

### JEV: the cheap screen on every candidate

JEV (TypeSafe's "System One") is not an LLM: it returns typed decisions — here a yes/no — each
with a probability, and generates no text. **$0.042 per M input tokens, output free.** It cannot
be called on `chat/completions` (400: *"is a decisions model … Use the /api/alpha/decisions
endpoint"*), but **OpenRouter accepts TypeSafe's protocol on `POST /api/alpha/decisions`** with
the ordinary key, so the harness reaches it with `urllib` and needs no SDK support. The body is
`{model, state, questions}`; each question is `{type: "noul", instructions, criteria: {true,
false}}` and the reply is `answers[name].noul`, the probability of true. **Identical calls do not
return identical probabilities** (observed 2026-09-30 on `typesafe/jev-1.13-20260917`: single
bullets move by a few hundredths, occasionally more), so a JEV median that differs by a point or
two between candidates, or between a score and its rescore, is noise.

How it is asked, and why each choice holds:

- **One question per bullet, the source whole in `state`.** Asked once whether a whole summary is
  faithful, JEV ranks barely above chance: finding one wrong claim in a long source is a search,
  not a decision. `state` holds the source alone; with the summary in it too, long sources
  overflow JEV's input. **Never truncate the source** — every claim from the missing half would
  look unsupported.
- **All bullets in one call.** It gives practically the same probabilities as one call per bullet
  at about a tenth of the bill, since every call pays for the source again.
- **The shortest positive question** (`JEV_SUPPORTED`: *"Is this claim supported by the source?
  The claim may be a translation."*). JEV follows the question's wording and ignores the
  criteria: asked whether a claim is *invented*, with criteria mapping `true` to supported, it
  answered the question as worded, so its probabilities came out inverted. Keep the question and
  the criteria pointing the same way. Longer instructions only made it doubt
  every bullet more without catching more errors.
- **The weakest bullet stands for the summary**, since one invented claim is enough to mislead and
  an average would let ten sound bullets hide it. `JEV_FLAG_BELOW = 0.6` was the best balance on
  42 hand-labelled summaries and is a reading aid for the report's `jev<0.6` column, not a gate.

**It is a coarse screen; Opus is what separates finalists.** Read comparatively, JEV orders
candidates roughly as Opus does, but it rarely invents a fault and **under-rates real ones** — on
some models it flagged almost nothing where Opus found invented claims in a fifth of summaries.

### Opus `FABRICATED`: the finalists' judge

`FABRICATED` asks for every claim the source does not support, each sorted into one of two kinds:
**invented** — no basis in the source or the source says otherwise (a name, number, date, event or
actor it does not have; done stated as not done) — and **compression** — merged, generalised,
re-emphasised, slightly over- or understated, rounded, with "when a claim could be either, it is
compression". Only *invented* fails the summary; compression is counted in the score's metadata
and comment and moves nothing, because whether it matters is a reader's taste.

**Why this judge is trusted.** A human reader checked its *invented* findings against the full
sources and agreed with every one checked; what they had rejected in earlier Opus verdicts was
what this prompt sorts as compression. It is **not certified**: there is no blind sample.

**Why only on finalists.** ~$3 a candidate adds up across a queue: ten candidates is more than
the bot's own monthly token spend.

Three details of the call are load-bearing:

- **The judge enumerates; it never returns a count.** A model that declares a number before its
  reasoning commits to it before it has thought, and a truncated reply loses the grounds for a
  number already asserted. An enumerated list loses only its tail, and the runner counts.
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
totals it. **Never quote a judge's cost from the catalog — measure a round.** The catalog's
relative prices have been wrong every time they were checked, mostly because reasoning tokens
eat the saving.

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

Each of these was built, measured and removed; the measurements are in git history. Do not
rebuild one without new evidence.

- **Coverage via a key-facts checklist.** Neither a model nor a human could cut a fact list to a
  cap consistently, and the facts pulled toward figures and names while the product asks for
  ideas. The harness evaluates a model under the product prompt, so labels belong on its
  summaries, not on a competing reference.
- **Omission by binary questions** (main takeaway, major topics, …). Every competent summary
  passes them, so they cannot rank candidates. Omission currently has no metric.
- **A filler/padding judge.** Never calibrated, and padding is visible the moment a survivor is
  read.
- **Pairwise readability judging.** Never calibrated. Pairwise can never be a Langfuse evaluator,
  which sees one item; readability is judged by reading the survivors. If it is retried: a
  pairwise judge decides on whatever the prompt fails to exclude (accuracy and length crept in),
  so read the judge's own reasons on its disagreements before paying for a round.
- **Faithfulness with a severity gate** (material/minor findings, fail on *material*). Most of
  its material flags were not errors to a human reader — the line between distortion and
  compression is taste. `FABRICATED` replaced it by failing only on invented facts.
- **Cheaper Opus substitutes**: Sonnet 5 under-reports real errors; `gpt-5.6-sol-pro` invents
  them and costs the same; `gpt-6-luna` is cheap and wrong. JEV as a whole-summary judge ranks
  near chance.
- **A one-question "anything invented?" prompt (`INVENTED`).** It caught every error but flagged most clean
  summaries too, mixing real fabrications with compression — what `FABRICATED`'s two kinds sort.
- **Certifying a judge per summary against hand labels.** Labellers did not converge on
  distortion versus compression, so no judge sets a floor. If labels are made again, adjudicate
  every judge-vs-labeller disagreement against the full source, not a passage a model picked.
- **A separate cheaper screening stage.** The compare run already carries Tier 1 and a two-cent
  judge, so a second step saved nothing.

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
  floor. Until every returned item has a `t1_pass` score, the row is marked `INCOMPLETE`,
  its Tier 1 percentage is withheld, and it is excluded from kept candidates and best-value
  highlighting. A footnote gives Tier 1 score coverage, including zero scores; an empty run
  is incomplete too.
- **A mean never ranks a model, so `--all-pairs` exists.** With 50 items a few points between
  two means can be noise. The flag adds, per Tier 2 score, a sign test over *per-item* deltas
  for every pair of candidates on the same items — controlling for item difficulty is worth
  roughly 3–4× the sample size. Two models 0.02 apart on a mean can split evenly per item, and an
  invented share of 14% against 27% is not yet significant. Use it before choosing between
  finalists; it is off by default because the
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
  these traces.
- **Tier 2 scores are read from `v3/scores` by name**, not from the experiment items — see the
  seven-score cap under *API shapes*. Backfill merges this same complete lookup by observation
  id before deciding which items need a paid judge, so an omitted inline score cannot trigger
  duplicate evaluation. The read starts at the earliest discovered run's `startTime`
  (`fromTimestamp`), since no score predates the run it scores.

## API shapes that cost real time to rediscover

- **The experiment-items read returns at most seven scores per item**, dropping the rest
  silently, so the report would show "-" for scores that exist. `stage2.py` reads Tier 2 scores
  by name from `v3/scores` and merges them in; inline scores still serve Tier 1.
- **The experiment endpoints take a dataset id, not its name, and require `fromStartTime`.**
  `GET /experiments` and `GET /experiment-items` both reject a call without `fromStartTime`, and
  experiments are filtered by `datasetId`, so a name is resolved through `GET /v2/datasets/{name}`
  first. A `fields` group that is not requested is **absent** from the response, not `null`.
- **Nothing in v4 deletes an experiment.** `experiments` and `experiment-items` expose `list`
  only. The deprecated v3 `DELETE /datasets/{name}/runs/{runName}` returns **200** and clears the
  run from the v3 view, but the v4 experiment and its items survive. Plan for junk runs to be
  superseded by newer ones rather than removed.
- **A score's value: the OpenAPI spec and the live API disagree, and the live one wins.** The spec
  declares `CategoricalScore.value` a *number* with the label in `stringValue`; `GET /v3/scores`
  actually returns `value: "A"` with `stringValue` absent. BOOLEAN is the same shape. The decoder still prefers `stringValue` for a categorical score, so
  it keeps working if the API starts honouring the spec, or on a route that already does. Reading only
  one field yields `None` or `0` for every verdict, which looks exactly like a judge that never
  ran. `langfuse_api.score_value(row)` is the one decoder; do not read `value` off a score row
  directly, and do not "correct" it to match the spec.
- **`subject` is its own `fields` group on `GET /v3/scores` and must be requested.** Without it a
  score row carries **no target at all**, and code mapping scores back to items matches nothing.
  Scores returned *inline* by `fields=core,scores` on `GET /experiment-items` carry `subject`
  without being asked.
- **A score's `metadata` and `comment` are the `details` field group on `GET /v3/scores`.**
  `core,subject` returns neither, and asking for `metadata` is a 400 — the groups are `core`,
  `details`, `subject` and `annotation`. The report reads JEV's `judge_model_version` this way.
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
  (`/api/v1/credits`), not the key (`/api/v1/key`): a call carrying a full-size source can need
  more than a few dollars of headroom.
- **A failed task is stored, not lost, and a partly failed run reads as a bad model.**
  `run_experiment` catches whatever the task raises, writes `Error: {exc}` into the item's output
  and skips that item's Tier 2 evaluators. The Tier 1 rule still scores the English error string
  as a language failure, so each errored item costs a model 2 points of `t1_pass`, and a run that
  lost most items to `402` reads as a plausible verdict about a model that never answered. The
  error is stored in Langfuse only: the SDK logs `Item N failed` and
  **drops the item from the returned `item_results`** (reproduced on 2026-10-01 against the locked
  SDK), so no `Error:` output ever reaches the caller. `judge.run` therefore counts failures as the
  dataset's items missing from `item_results`, plus empty outputs, and warns while there is still a
  sweep to stop; `stage2.py report` reads the stored outputs, so its footnote sees them too.
- **A Langfuse score requires a target.** Passing `trace_id=None` fails with a bare `Bad request`
  while the calling code still prints success. `stage2.py judge` anchors a backfilled score to the
  experiment item's observation (the item's `id`), exactly as `run_experiment` does — the trace
  alone would be missing from the experiment-items read.
- **Dataset run names embed the model id**, so they contain `/` and spaces and must be URL-encoded
  into REST paths or the segments split and the request 404s.
