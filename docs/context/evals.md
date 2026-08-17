# Evaluation

How summarization quality is measured: the Langfuse datasets built from real traces, the
scoring tiers, the judges, and the harness in `scripts/eval/`.

Nothing here is imported by the bot — these are operational scripts, run by hand.
`architecture.md` owns the bot itself, including *how* it emits the traces this is built on;
read its **Tracing** bullet before changing anything that produces trace data.

## What this is for

**The registry is the output of evaluation, not its input.** New models appear and existing
ones change constantly, so the question this answers is *should this model be in
`config.MODEL_SPECS` at all* — screen a candidate first, then decide whether to add it. It
also re-checks models already registered, and gates prompt edits against regression, but
candidate screening is the primary use.

### Everything runs over OpenRouter, and models are named by their OpenRouter id

The harness never consults `config.MODEL_SPECS`. Model ids are passed as arguments, always,
with no default list — requiring a model to be registered before it can be screened would
invert the tool.

**Do not add a default list back.** The set worth screening is different every time: today's
candidates are not tomorrow's, and the current batch is large only because this is the first
pass over a registry that had never been evaluated. In steady state a new model shows up on
its own — vendors do not ship on the same day — so the normal invocation is one id, and a
constant would be stale the week after it was written.

One route for every model also keeps results comparable, and the price of that is accepted
deliberately: a model the bot reaches through its own provider is screened over OpenRouter
instead, so its numbers sit very slightly off the bot's real behaviour. Comparing models to
each other — which is what screening is for — is unaffected.

**Never derive an OpenRouter id by prefixing a vendor name.** The catalog carries `:free` and
`:batch` siblings next to the plain id, so a computed id can silently select a different model
and bill for it. `stage1.py run` validates every id against the catalog and refuses to start
otherwise, printing the near-misses.

Where a model's registry id differs from its OpenRouter id — a provider whose native ids carry
no vendor prefix — `stage1.py`'s `REGISTRY_ID` maps the two and the run records
`registry_model_id` in its metadata, so a screening result ties back to a production model
without anyone having to know the mapping.

### A candidate's route

Nothing below needs the model to be in `config.MODEL_SPECS`, and it should not be added until
the end:

1. **Screen it.** `stage1.py run <openrouter-id>` — no registry entry needed.
   `eval_client.EvalLLMClient` subclasses `LLMClient` and overrides only `build_model`, so the
   run still goes through the instrumented path and records cost and thinking level, while the
   base class's registry lookup (which would raise `KeyError` for a candidate) is bypassed.
2. **Promote a survivor to Tier 2/3.** `judge.py` never touches the registry either, so
   `judge.py run <candidate-id>` produces its outputs and attaches the Tier 2 evaluators, and
   `judge.py pairwise <run-a> <run-b>` duels it against an incumbent. A model that clears
   screening belongs here — screening only proves it is not broken, and the ranking is Tier
   2/3's job.
3. **Then decide, and only then edit `config.py`.** Adding an id needs no migration; removing
   or renaming one does — see the registry bullet in `architecture.md`. A model registered
   under the `google` provider keeps its native id there, and `REGISTRY_ID` gains a row.

### Both stages summarise through the same client; the judge does not

`eval_client.py` holds `EvalLLMClient` and the single `THINKING_LEVEL` both stages read, and
that sharing is the point rather than tidiness. A candidate's cost and latency are half of the
question being answered — quality alone always picks the most expensive configuration — so the
compare stage has to produce them on the same terms screening did. Two stages holding their own
copy of the thinking level would drift, and the drift would look like a property of the model.

**An experiment task must be `async def` and reach the model through
`eval_client.summarize`.** `run_experiment` awaits the task inside its own running event loop,
while `LLMClient.run` ends in pydantic-ai's `run_sync`, which drives a loop itself — calling it
from there raises `RuntimeError: This event loop is already running` on *every* item, before a
single request leaves the machine. `summarize` hands the call to a worker thread, which has no
running loop, so `run_sync` builds its own and the bot's synchronous path is reused as the bot
runs it rather than reimplemented asynchronously beside it. `to_thread` copies the context, so
the generation span still nests under the experiment item and the cost wrapper still finds it.

The failure is cheap and looks expensive-to-diagnose: 150 items fail in about 15 seconds, each
recorded as an empty output, which is indistinguishable from a model that answered nothing.
`stage1.py report` therefore refuses a verdict for any run whose every item scored
`t1_compression` 0 — that is the runner failing, not a model, and scoring it 0% eliminated all
six registered models in one pass before the guard existed.

The **judge** stays on its own HTTP call in `judge.py`, deliberately. It needs a forced tool
call against a JSON schema, which `LLMClient` does not do and the bot never asks for, so routing
it through the seam would mean adding structured output to `src/llm.py` for a request production
never makes. What the judge spends is a cost of running the evaluation, not a property of the
model being ranked, so it does not belong on the candidate's trace either. `ask` returns
OpenRouter's `usage` and every caller discards it; totalling the evaluation's own bill from
there is unbuilt, not rejected.

## Staged execution

Do not run the full grid. Model × thinking level × prompt strategy is a large space and most
of it decides nothing, so the work is staged and each stage narrows the next:

1. **Screen** — the candidates over the 25 screening items at one fixed thinking level, Tier 1
   only, no judge calls. Drops any model failing outright.
2. **Compare** — the survivors over the 50-item set with the full scorer suite: Tier 2 per
   dimension and Tier 3 pairwise with order swap. Candidates that cleared screening go in
   here alongside the incumbents; this is where the ranking is actually decided.
3. **Sweep thinking levels** on the winner only, and expect to decide it on cost and latency
   rather than quality, because adjacent levels rarely separate.

Track cost and latency beside quality throughout; quality alone always picks the most
expensive configuration. Below ~30 items report gross failure rates only, never rankings.
Keep the dataset afterwards as a regression gate for prompt edits, not only for model launches.

## The harness

| File | Purpose |
|---|---|
| `_bootstrap.py` | Loads `.env`, puts `src/` on the import path, returns Langfuse REST credentials |
| `eval_client.py` | `EvalLLMClient` and the shared `THINKING_LEVEL`. Both stages summarise through it |
| `langfuse_api.py` | The only place that calls the Langfuse REST API. v4 endpoints, rate-limit aware |
| `tier1_evaluator.py` | Tier 1 deterministic scorers. Uploaded to Langfuse, **executed there** |
| `install_tier1.py` | Uploads the above. Its preflight is the only way to see the evaluator crash |
| `stage1.py` | The screening stage — sweep, report, and per-item failures |
| `judge.py` | The Tier 2/3 LLM judge; runs outside Langfuse |
| `calibrate.py` | Judge-vs-human agreement. Gates the compare stage |
| `rebuild_datasets.py` | Rebuilds both datasets from a raw harvest. Destructive; needs `--yes-wipe` |

```bash
uv run python scripts/eval/install_tier1.py     # after every edit to tier1_evaluator.py
uv run python scripts/eval/stage1.py report     # free, read-only
uv run python scripts/eval/stage1.py failures   # free — which items failed, and why
uv run python scripts/eval/stage1.py run <openrouter-id> ...   # COSTS MONEY
uv run python scripts/eval/judge.py smoke 2     # COSTS MONEY: judge calls
```

Anything that only reads is free. A full screening sweep is 25 items × every model swept,
roughly **$1**; judge calls are the expensive part. Re-scoring Tier 1 never costs anything —
the summaries already exist as trace outputs, so a broken scorer is repaired by reinstalling it
and recomputing, not by re-generating.

## Where state lives

State is split across three places, and only one of them is the repository.

| What | Where |
|---|---|
| Scripts, Tier 1 evaluator source | `scripts/eval/` (tracked) |
| Prompts, datasets, score configs, evaluators, rules, runs, scores | Langfuse (server) |
| Raw trace harvest (`obs.json`), ad-hoc probes | untracked, local only |

The part that surprises people: `tier1_evaluator.py` **never runs on your machine**. Langfuse
stores the source and executes it on its own infrastructure when an experiment item arrives.
The local file is only the source uploaded by `install_tier1.py`.

## Working with the Langfuse API

**Use the `langfuse` skill.** It carries the CLI, the current API reference and the version
migration guides, and it is the authority on endpoint shapes and SDK usage — do not implement
from memory, and do not restate its contents here. API surfaces change; a copy in this file
would go stale silently.

What belongs here is only what the skill cannot know:

- **`scripts/eval/langfuse_api.py` is the only place that calls the REST API.** Add reads
  there rather than scattering `requests` through the scripts.
- **This project is already on the v4 data model.** Ingestion is OTel via the pinned SDK, the
  one evaluation rule targets `experiment`, and no blob-storage, PostHog or Mixpanel export is
  configured, so the export migration does not apply. Trace-level input/output is deprecated
  product-wide and nothing in `src/` sets it — see the **Tracing** bullet in
  `architecture.md` for the constraint that keeps it that way.
- **Read experiment results from the experiment endpoints, never by joining traces.**
  Evaluator scores attach to the **observation**, so filtering scores by experiment id returns
  nothing for them and reads exactly like the evaluator never fired. Requesting the score and
  IO field groups on the experiment's items returns both inline, which is one call per page
  instead of a run fetch plus a trace fetch per item plus a separate score sweep.

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

| | UI Prompt Experiment | `scripts/eval/stage1.py` |
|---|---|---|
| Who calls the model | Langfuse, via an LLM Connection | your code, locally |
| Prompt source | the Langfuse mirror | `src/prompts.py` directly |
| Code path | Langfuse's request builder | `llm.LLMClient` — the bot's path |
| Thinking level | not applied | `build_settings` applies it |
| Cost | Langfuse's own pricing | `OpenRouterCostReporter`, what OpenRouter charged |
| Gemini | over the OpenRouter connection | native `GoogleModel` |
| `environment` | `langfuse-prompt-experiment` | `sdk-experiment` |
| Tier 1 | fires | fires |
| Tier 2/3 | not possible | `run_experiment(evaluators=[…])` |
| In git | no | yes |

The script screens candidates as well as incumbents, so the UI is not needed for that. It
stays useful for eyeballing prompt wording by hand. If a UI run is compared against a script
run, check first that the **Langfuse prompt mirror** has not drifted from `src/prompts.py` —
otherwise the two were asked different questions. The mirror stores `prompt_version` in its
`config` for exactly this: compare it against `prompts.prompt_version(key)`. Tell the two
kinds of run apart by `environment` — `langfuse-prompt-experiment` for UI, `sdk-experiment`
for the script.

A UI run cannot go through `LLMClient`, so it has no cost wrapper, no thinking level, and
routes Gemini over OpenRouter — it measures a call the bot never makes. Use it to eyeball
prompt wording; use the script for anything that feeds a decision. Note also that UI runs are
named `Prompt … on dataset …`, so `stage1.py`'s `stage1 / ` prefix filter skips them.

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

Do **not** re-add a `Language` prompt referenced by composition, as an earlier hand-built
version did. It freezes into the prompt what the dataset needs as a per-item variable, so a run
cannot mix target languages, and Langfuse then refuses to delete it while any dependent version
survives. Storing `prompt_version(prompt_key)` in the prompt's `config` is what ties a Langfuse
version back to the repo revision it was copied from; nothing else records it.

## Datasets are built from traces, and the content type is not one of the fields

Two Langfuse datasets hold screened trace content: `summarization-screen-v1` (25 items) is a
strict subset of `summarization-compare-v1` (50), so the per-item key-facts checklist that
serves as `expected_output` is written once rather than twice. Item `input` is
`{content, target_language}` and nothing else — those are the two prompt variables, and an
`inputSchema` on both datasets rejects an item missing either. `prompt_key` rides in `metadata`,
not `input`: an experiment picks one prompt and runs it over every item, so the originating
trace's strategy fills no variable and would sit in `input` as a dead key.

The trap when harvesting: a trace's tag is the **Telegram** `content_type`, which is `text` for
a URL as much as for a pasted paragraph. A YouTube transcript, a web article and a
Replicate-rescued audio transcript are therefore all tagged `text`, and no field distinguishes
them — the stratum has to be inferred from the content, by **two** tests, not one. A YouTube
transcript arrives in subtitle format, hard-wrapped to ~34-character lines. The other two are
both single blobs, so line width cannot separate them; what does is that `parsing.py` returns
markup (Exa HTML, Tavily markdown) while WhisperX returns its segments joined into plain prose
with a leading space. Testing only for wrapping silently files every audio transcript under
`web_article`, which is a stratum label that looks plausible in the UI and is wrong.

The strata are not balanced and that is **accepted**, not an oversight to fix: nine days of real
traffic yielded only 5 `web_article` items in total (2 of the 25 screening items), under the
≥8–10 per cell the plan asks for, and no amount of further harvesting changes it. The
consequence to keep stating is narrow — a *web-article-specific* claim is anecdote until the
stratum is seeded — while `yt_transcript` and `audio_transcript` carry enough items to rank
models. Do not re-raise this as a blocker.

Two screening filters earn their keep on real traffic: content under ~1500 characters, and
degenerate output from `AudioTranscriber.transcribe` when WhisperX mis-decodes audio — a
distinct failure from the documented empty-transcript case, and one that reaches the model as
content rather than being dropped. Detect it by **compression ratio**, not by any single
character's share: the observed failures repeat a multi-character sequence, so one of the two
sat at 27% on its most common character and slipped a 30% threshold, while both compress to
~0.03 of their size against ~0.14 for the densest real item.

## Tier 1: binary sub-checks, never weighted points

Every rule in `prompts.py` is stated as an absolute — "Respond in {language}" has no
60%-credit reading — so a weighted composite would invent numbers and hide *which* rule broke,
which is the only thing the screening stage needs to know. The Langfuse code evaluator
`tier1-deterministic` emits `t1_language_match` and `t1_bullet_count` (BOOLEAN),
`t1_compression` (NUMERIC) and the derived `t1_pass`, which ANDs the applicable binary checks.
Screening drops a model scoring `t1_pass` on under 70% of items. Three judgements are
deliberate:

- The language check passes at **70%** Cyrillic letters, not 95%. Correct output still carries
  Latin proper nouns, so a stricter floor rejects good summaries while adding nothing against a
  model that answered in the wrong language outright.
- `t1_compression` is a **diagnostic with no threshold**. Judges reward length, so the length
  column belongs beside every quality score; gating on it would let a model win by truncating.
- `t1_bullet_count` is emitted **only** for `key_points_for_transcript`, the one strategy that
  asks for bullets. Scoring `basic_prompt_for_transcript` zero there would penalise it for
  obeying its own prompt. So `t1_pass` ANDs one check for that strategy and two for the other,
  which means it ranks models **within** a strategy and must never be used to compare the two
  strategies — that is Tier 3's job.

### Three checks were removed, deliberately

**`t1_no_preamble`, `t1_no_artifacts` and `t1_bullet_purity` were removed** in evaluator v4 and
should not be reinstated without new evidence. Across 150 scored items they produced three
hits and none of them changed a decision: a markdown heading before the list, and two
substring matches on ordinary words. The false positive is the general lesson — a check that
greps for the word "transcript" fires on any summary whose *subject* is transcription, so a
Tier 1 check must key on something the content cannot legitimately contain.

The one genuine defect they caught was a model emitting its internal reasoning block into the
summary, and the settled judgement is that **Tier 2 is the right place to catch that**: a
judge reading a summary that contains a reasoning block will mark it unfaithful, while a
coarse screen gains nothing from one item in 25. Tier 1 now screens for
outright breakage only — wrong language, no list where a list was asked for. Style and
prompt-obedience belong to the judges.

Scores written before v4 still carry the removed names, so a report must tolerate their presence
in old runs and their absence in new ones; the score configs are kept for exactly that reason,
and `stage1.py report` says so when a run's stored `t1_pass` predates the change.

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
number and the dataset-items API returns one. Arithmetic on such a value raises `TypeError`,
which discards the whole `EvaluationResult` — including the scores already built before the
failing line. Nothing surfaces this: the rule still reports `status: "active"`, the run
completes, and the only symptom is that no score appears. This cost a full session to find, so
**coerce every metadata value before using it as a number**.

The one place the failure is visible is `POST /unstable/evaluators`, whose preflight executes
the source against sample data and returns `422 evaluator_preflight_failed` with the exception
and line number — which makes reinstalling the evaluator the cheapest way to test it, and means
a rule that went active earlier is **not** evidence the code still runs, since preflight only
sees whatever sample it was given.

Two consequences for scoring runs:

- Branch on `run_prompt_key` from the run metadata, not the item's `prompt_key`. An experiment
  applies one strategy to every item, while an item's `prompt_key` records the strategy of the
  trace it was *harvested* from; on a mixed dataset the two disagree and the bullet check
  silently applies to the wrong items. `summarization-screen-v1` has 24 items from
  `key_points_for_transcript` and 1 from `basic_prompt_for_transcript`, so this is live, not
  hypothetical. The evaluator prefers `run_prompt_key` and falls back to the item.
  The obligation runs the other way too: the Tier 1 rule fires on **every** experiment, compare
  runs included, so any runner calling `run_experiment` must put `run_prompt_key` in its run
  metadata. Spelling it `prompt_key` there does not work and does not fail either — the
  evaluator reads run metadata off `ctx.observation` and item metadata off `ctx.experiment`, two
  different places, so a misnamed key overrides nothing and simply leaves the fallback to
  decide. The symptom is a `t1_bullet_count` that looks perfectly plausible and was computed
  against the wrong strategy.
- Re-POSTing an evaluator under the same name creates a new **version** and every rule bound to
  that name follows it automatically — the rule's stored evaluator `id` changes to the new
  version's id. There is no separate update route, and no need to touch the rule.

### One evaluator, not one per score

Splitting `tier1-deterministic` into one evaluator per score was considered and **deferred**,
not overlooked. The argument for splitting is real (the `char_length` crash destroyed the
already-computed scores along with the one that failed), but the price is higher than it looks:

- `t1_pass` cannot survive the split. An evaluator's context is its own observation and
  experiment item; it cannot read scores other evaluators wrote. A standalone `t1_pass` would
  have to recompute every check internally — restoring the same monolith and the same single
  point of failure, just for the aggregate — or stop being a stored score and become a
  report-time calculation.
- Each evaluator is a self-contained source blob with no imports between them, so `_text`,
  `_lines`, `_is_bullet`, `_cyrillic_ratio` and `_number` would be copied into each. One fix
  becomes many edits and many reinstalls, and divergence between the copies is silent.
- Splitting only helps when one check's *input* breaks, which is the `char_length` case. A
  change to the `ctx` shape itself breaks every evaluator identically either way.

The cheaper equivalent, if this is revisited: keep one evaluator and wrap each check in
`try/except`. Whatever is done, `t1_pass` must **not** silently become the conjunction of
whichever checks survived — a partial failure has to suppress it or label it, or the score
quietly changes meaning.

What makes deferring safe is that **re-scoring Tier 1 costs no tokens**. The summaries are
already trace outputs, so a broken scorer is repaired by recomputing over existing traces —
either through Langfuse's backfill (Traces table → `Actions` → `Evaluate`, requires the v4
preview toggle; documented for observation-level, **unverified** for a code evaluator on an
experiment target) or by running the same source locally and posting scores through the API.
Only Tier 2/3 spend money on a re-score.

## Tier 2 and Tier 3: the judges

Both live in `scripts/eval/judge.py`, a local runner that posts scores back through the API into
the same score table as the `t1_*` scores and any human annotations — which is what keeps the
calibration comparison a query rather than a spreadsheet. The reasons differ per tier, and
conflating them is a mistake worth not repeating:

- **Structured output works.** `response_format: json_schema` returns clean schema-conforming
  JSON on Anthropic over OpenRouter, with and without `provider: {require_parameters: true}`,
  so nothing on that account stops a Langfuse-managed Tier 2 judge. `judge.py` uses a forced
  tool call (`tools` + `tool_choice`) instead, because that is what the banked scores were
  produced with — not because the alternative is broken.
  When a provider *appears* to silently ignore a documented parameter, check its status page
  before writing the behaviour down: from the client side an incident and a missing feature
  look identical, and this bullet once carried a constraint that was really an outage.
- **An evaluator sees one item.** Its context is that item's `input`, `output`, `expected_output`
  and metadata; there is no mapping source for a second run's output. So **Tier 3 pairwise cannot
  be an evaluator of either kind**, whatever the judge model. This constraint is structural and
  is the one that genuinely forces a local runner.
- **Tier 2 stays local by choice, not by constraint.** Faithfulness, coverage and no-filler are
  per-item single-observation judgements, so they would fit a managed evaluator, and on an
  `experiment` target it can read `expected_output` — the key-facts checklist coverage needs. Two
  things are given up by moving them, and both are load-bearing rather than stylistic: the
  **judge counts and the runner divides** (a managed evaluator's output definition is one numeric
  `score` plus reasoning, so asking the model for `0.71` directly is exactly the arithmetic slip
  that design removed), and `judge_version` **pins the prompt and schema by hash** so banked
  comparisons stay valid, whereas a managed evaluator is versioned by Langfuse and that version
  would have to be copied into run metadata by hand. The Ragas library evaluators are not a
  shortcut here either: their `Faithfulness` takes `context`/`answer` and is RAG-shaped, while
  this project's definition counts claims, is translation-aware (Russian summary, possibly
  English source) and explicitly does not penalise omission. Revisit the trade, do not assume it
  was forced.

### The judge model

The current id is the `JUDGE_MODEL` constant in `judge.py`; what matters is the two
constraints behind it, which outlive any particular model.

**The judge's family must not appear in the candidate pool.** A judge scoring its own family
favours it, and with several families competing that bias can decide the ranking outright.
**And the judge must outrank the candidates** — judging mid-tier output with a mid-tier model
measures the judge's ceiling, not the candidate. Re-check both whenever a candidate from the
judge's family is screened; that is the event that invalidates the choice.

The judge is pinned by model id, reasoning effort and judge-prompt hash — **not** by
temperature, which frontier models increasingly reject outright. Calibration against hand
labels may still revise the choice — 20–30 labelled outputs, iterate the judge prompt until
agreement reaches ~80% or Cohen's kappa passes 0.6 — but nothing else should.

### Three details of the judge are load-bearing

The judge **counts** (claims, entailed facts) and the runner computes the ratio, because a model
asked directly for `0.71` makes arithmetic slips no prompt wording fixes. Each schema declares
its **verdict field before `reasoning`**, since models emit in declared order and it is the long
reasoning string that runs into `max_tokens` — a truncated call then still carries the answer.
And OpenRouter does not enforce `required` on this route, so a missing field has to be caught
explicitly rather than trusted. Pairwise runs **both orders and discards disagreements**; the
discard rate is itself a judge-quality signal.

### Calibration runs before the compare stage, not after

`scripts/eval/calibrate.py` measures the judge against hand labels: raw agreement plus Cohen's
kappa, targeting ~80% / kappa >0.6. A Tier 2/3 ranking means nothing until this passes, so it
gates stage 2 rather than reviewing it. It is also **cheapest before any Tier 2/3 score is
banked** — every judge-prompt revision moves `judge_version` and unpins banked comparisons, so
iterating now costs nothing and iterating later destroys real work.

Four things about it are load-bearing:

- **The judge prompts and schemas are imported from `judge.py`, never restated.** Calibration
  has to measure the prompt production actually uses; a copy would drift and the agreement
  number would then describe nothing.
- **Both dimensions are hand-labelled in a Langfuse annotation queue, and its items must point
  at the ROOT span.** A screening trace holds four observations, and only the choice between
  them decides whether the measurement means anything. The root span's output is the clean
  summary, byte-identical to what the judge is given. The GENERATION nested inside it holds the
  model's reply *as parts*, with a reasoning model putting a `thinking` part in front of the
  `text` one — annotate that and the human reads a different artefact than the judge scores and
  sees reasoning the judge never sees. Nothing complains either way; the wrong pick simply
  produces an agreement number about nothing.
- **Pairwise has no existing object to point at**, because a queue item is one object and the
  comparison needs two summaries side by side — the constraint that stopped Tier 3 being an
  evaluator. `calibrate.py setup` writes one purpose-built span per pair, source as input and
  both summaries as output, and the blinding lives in its metadata as the only record of which
  model was shown as A. They are free, named `calibration pair`, and never read as bot traffic.
- **One queue holds both dimensions.** The Hobby plan allows exactly one annotation queue, and
  no API route updates a queue's score configs after creation — so it has to be created with
  every config it will ever need. A queue missing one simply never offers that channel in the
  UI. Mis-setting a channel on the wrong kind of item is harmless: agreement maps observations
  back to sample items, and a label on an observation outside that mapping is ignored.
- **The sample is derived, not stored** — items sorted by id and dealt round-robin across the
  screening runs. Agreement is only comparable across prompt revisions when the items stay
  fixed, and a stored manifest would drift from the runs it names.
- **Pairwise labelling is blind, and the blinding is per item.** Which model appears as A is
  derived from a hash of the item id, so the layout reproduces without a manifest while no
  vendor can be tracked down the file. These labels *become the standard the judge is measured
  against*, so a preference leaking into them is not a bias in one score — it is a bias baked
  into the target. Verdicts are stored canonically (A always means the first model), so a human
  label and a judge label are the same kind of statement.

An `INCONSISTENT` pairwise verdict is the judge **abstaining**, not disagreeing: the two orders
contradicted each other, so there is no opinion to compare. Those are excluded from agreement
and kappa and reported as a discard rate, exactly as the compare stage discards them. Counting
them against the judge would understate agreement and quietly merge position bias with error.

The generated labelling file is markdown containing *summaries that are themselves markdown*,
so a parser keyed on a `## ` prefix alone reattributes verdicts to headings the model wrote.
`labels` accepts a heading only when it names a known sample item. The failure mode is a
dropped label that reads as an unlabelled item, not as an error.

## API shapes that cost real time to rediscover

Installing a code evaluator through the unstable API has a shape trap worth keeping: on
`POST /unstable/evaluators` the `prompt` and `outputDefinition` fields are llm-as-judge-only and
are rejected outright for `type=code`, while on `POST /unstable/evaluation-rules` the evaluator
reference needs `type: "code"` and `mapping` must be **omitted entirely** — an empty array is
rejected just as a populated one is, and leaving `type` off makes the request validate as
llm-as-judge and demand a mapping. The evaluator reference also needs `name` and `scope`
alongside `id` and `type`; sending only the id fails validation. The server fills the omitted
`mapping` in with defaults, so a rule read back after creation shows six entries — that is
expected, not drift. A rule returning `status: "active"` means its preflight ran the code
**once, against sample data**; it does not mean the code survives real data, so treat `422` from
a later `POST /unstable/evaluators` as the authoritative crash report.

Three more:

- Tier 2 evaluators attach through `Langfuse.run_experiment(evaluators=[…])` rather than by
  posting scores by hand — the run wires each `Evaluation` to the right item.
- A Langfuse score **requires a target**. Passing `trace_id=None` fails with a bare
  `Bad request` while the calling code still prints success, so a pairwise score has to be
  anchored to something — run A's trace for that item is the natural choice.
- Dataset run names embed the model id, so they contain `/` and spaces and must be URL-encoded
  into REST paths or the segments split and the request 404s.
