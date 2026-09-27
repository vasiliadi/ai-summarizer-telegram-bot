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
2. **Compare** — the survivors over the 50-item set on the calibrated faithfulness judge.
   Candidates that cleared screening go in here alongside the incumbents.
3. **Read the survivors live.** The harness is a **filter, not a ranking** (settled
   2026-09-26): it removes models that are certainly unfit — broken language or script, no
   list, invented facts — and the user judges readability and overall quality by using the
   survivors. Measured on three strong models, every automated axis tried so far (faithfulness,
   coarse omission questions) passed all three alike, so no automated number was going to pick
   between good models anyway.
4. **Sweep thinking levels** on the chosen model only, and expect to decide it on cost and latency
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
| `judge.py` | The Tier 2 LLM judge; runs outside Langfuse. One compare run per invocation |
| `stage2.py` | The compare stage — the sweep and the report over `t2_*` |
| `calibrate.py` | Faithfulness judge-vs-human agreement. Gates the compare stage |
| `rebuild_datasets.py` | Rebuilds both datasets from a raw harvest. Destructive; needs `--yes-wipe` |

```bash
uv run python scripts/eval/install_tier1.py     # after every edit to tier1_evaluator.py
uv run python scripts/eval/stage1.py report     # free, read-only
uv run python scripts/eval/stage1.py failures   # free — which items failed, and why
uv run python scripts/eval/stage2.py report     # free, read-only
uv run python scripts/eval/stage1.py run <openrouter-id> ...   # COSTS MONEY
uv run python scripts/eval/judge.py smoke 2     # COSTS MONEY: judge calls
uv run python scripts/eval/stage2.py sweep <openrouter-id> ... # COSTS MONEY: a compare run each
```

Anything that only reads is free. A full screening sweep is 25 items × every model swept,
roughly **$1**; judge calls are the expensive part. Re-scoring Tier 1 never costs anything —
the summaries already exist as trace outputs, so a broken scorer is repaired by reinstalling it
and recomputing, not by re-generating.

### Harness runs report to Sentry as `production`, and that is left alone deliberately

Every script here imports `config` from `src/`, whose `sentry_sdk.init` sets no `environment` —
so the SDK defaults to `production` — and enables `LoggingIntegration(capture_sentry_logs=True)`,
which forwards stdlib `ERROR` records. Langfuse logs a failed evaluator at `ERROR`, so **a sweep
run from a laptop raises Sentry issues in the bot's production stream**, tagged
`environment: production` with `server_name` set to the developer's machine.

Do not diagnose these as bot defects. Tell them apart by `sys.argv` in the event's extra data:
a harness event carries `scripts/eval/...`, and `Users Impacted` is 0. Issues of this kind have
been raised and closed as noise.

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

**Langfuse keeps traces, observations and scores for 30 days on this plan, then deletes them —
hand labels included.** Checked on 2026-09-26: the oldest surviving trace was from 2026-08-28,
and every screening and compare experiment, every judge verdict (`cal_*`), every Tier 1 score and
all 50 hand labels (`h_faithful`, `h_pairwise`) were gone. Datasets and their items survived.
Nothing warned. So "banked in Langfuse" means banked for a month: anything that must outlive
that — hand labels above all, since they cost days rather than dollars — has to be exported to a
local file or written into a dataset item's fields. The calibration numbers recorded below are
the only surviving record of those rounds, and `calibrate.py agreement` can no longer reproduce
them.

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
- **The deprecated routes are switched off on 2026-11-16, and the SDK still calls one of them.**
  Checked against Langfuse's migration page on 2026-09-26: the REST calls in `scripts/eval/`
  are already on the replacements (`v2/observations`, `v3/scores`, `experiments` +
  `experiment-items`, `v2/datasets`, `v2/evaluators`). But `Langfuse.run_experiment` — in the
  pinned 4.14.4 and in 4.15.6, the latest at the time — links every item to its run through
  `POST /dataset-run-items`, which is on the list. It catches the failure and only logs
  *"Failed to create dataset run item"*, so after the cutoff a sweep would complete, write its
  traces and scores, and **never appear as an experiment**: `stage1.py report` and
  `stage2.py report` would say no runs exist. Before sweeping after mid-November, check the SDK
  changelog for a release that moved off the route, bump to it, and confirm a one-item run shows
  up in `GET /experiments`. `GET /traces` is deprecated too; read traces as
  `v2/observations` rows grouped by `traceId`.
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

### The key-facts checklist: the reference `t2_coverage` was meant to score against, now retired

**Retired on 2026-09-26: `scripts/eval/checklists.py` and the `KEY_FACTS` prompt were deleted.**
No checklist ever reached a dataset, so `t2_coverage` never produced a value, and the coverage
judge (`COVERAGE`, `eval_coverage`) was removed the same day. **Tier 2 is now faithfulness
only** (no-filler was removed the same day, see *Tier 2 and Tier 3*); every later mention of `t2_coverage` in this file is history. Two binary-question
rounds (under *JEV* below) found that coarse omission questions do not separate candidates either,
so omission currently has no metric. The history below is kept so the approach is not rebuilt
without its lessons — the recoverable code is in git history.

Coverage is the hard part of reference-free summarization, and the checklist is what converts
it into a reference-based problem without anyone writing a gold summary: a strong model extracts
the atomic facts a summary must not omit, a human edits the list, and it is stored as the item's
`expected_output`. Per-fact entailment is an easy judgement; "is this summary complete?" is not.
The cost is paid once per **item**, not once per run. `scripts/eval/checklists.py` did the
generating, reviewing and writing.

- **The hand-review step is load-bearing, not decoration.** `eval_coverage` returns `None` while
  an item has no checklist, which is visibly missing data. A *wrong* checklist mis-scores every
  model at once and looks like a result. `push` therefore writes only entries marked
  `"reviewed": true` unless `--all` overrides it, and generation goes to a working file under
  `temp/` rather than straight to the dataset.
- **Checklists are keyed by content digest, not by dataset item id.** The same source is
  `cmp-<digest>` in the compare set and `scr-<digest>` in the screening subset, so one reviewed
  list is written to both items and the 25 shared sources are reviewed once. This is what the
  strict-subset property in `rebuild_datasets.py` is *for*.
- **A dataset item has no partial update.** `POST /dataset-items` upserts by id, so writing
  `expected_output` means re-sending `input`, `metadata`, `source_trace_id`,
  `source_observation_id` and `status` alongside it. Omit one and it is gone, with no error and
  no way to restore it — which is why `push` reads each item, changes exactly one field, and
  then reads it back to verify.
- **Facts are extracted in the language of the source**, which is usually not the summary's
  language. Translating the checklist at build time would bake a translation error into the
  reference everything downstream is measured against, and the judge is already told that
  wording and language need not match.
- **A checklist item is a key point — an idea — not an atomic fact, and the list has no cap.**
  The first generation (`key_facts@dc7a8a2c22ec`) asked for "one event, one figure, one named
  actor" under a hard cap of 12. Both halves failed, and a blind check measured it: Opus, given
  the full source and the generated list under that same criterion with no quota, decided
  KEEP/DROP per fact for the five lists the user had hand-reviewed. **Of 17 distinct drop
  decisions the two agreed on 2**, both obvious logistics (how to enable a module, a demo QR
  code). The 79% raw agreement (55/70) is base rate: both keep nearly everything. Opus itself
  kept 11–14 of 14 without a quota, kept all 14 on one list, and named 1–3 *missing* points on
  every list — the criterion "a reader would be misinformed to miss" admits almost any true
  statement, so neither reader can cut to a cap consistently. That is not a review defect.
  - **The granularity was wrong for the product.** `key_points_for_transcript` asks for bullets
    that each "capture a distinct, significant idea"; the checklist asked for facts, and
    atomicity pulls toward whatever atomises easily — figures and names. Opus tagged **39 of 82
    facts (48%) as supporting detail**. The worst list (`271deb99e66d`, a panel discussion) was
    9 details of 12, nearly all survey percentages, while the points Opus listed as missing were
    the panel's closing consensus and its one worked example. A good key-points summary of it
    would score badly for doing what the product asks.
  - **The cap was set by what summaries do now, not by what they are for.** The earlier case
    for 12: summary length barely follows source length — across the 25 duel items the source
    grows **7×** between the shortest and longest eight (median 6,340 → 44,164 characters) while
    summaries grow **1.54×** and **1.24×** — so a checklist scaled with the source gives an
    unattainable ceiling. That describes the candidates, not a constraint: the bot splits long
    replies across messages (`split_entities` in `src/services.py`), and the product prompt
    says to use "as many bullets as needed to cover it faithfully". The bot's use is deciding
    whether a 40-minute or three-hour source is worth the time, which needs completeness that
    grows with the source. **Low coverage on long sources is therefore a finding about the
    candidates, not a flaw in the metric**, and it is the one this metric exists to surface.
  - **The criterion is relative to the source, not to the reader.** "Would I learn anything
    new?" is how the bot is used, but it depends on what the reader already knows, which no
    model can see. The prompt asks for everything a reader would need to have learned what the
    source has to say.
  - **The prompt now asks for ideas, one per line, ordered most important first**, admits a
    detail only when it *is* the point (a deal's price in a story about the deal), merges
    restatements, and states there is no target count. Order is kept so coverage of the top N
    stays computable without reintroducing a cap. `checklists.py` kept only the lower bound
    of 5, as a warning, since the product prompt also asks for at least five bullets.
  - **The pilot** (`key_facts@e08331f46483`, the same six sources): **33–49 points** on
    21k–71k-character sources, $0.47 for six. Density follows content, not length — 38 points
    on a 21k practical guide, 36 on a 71k webinar. Enumerations (fraud types, warning signs)
    come out as one point each, and some lines still join an idea to its figure ("… with about
    70% saying so"); whether coverage can answer those cleanly is unmeasured.
  - **Two consequences.** A mean `t2_coverage` across items now mixes very different
    denominators, so read it banded by `chars` or `stratum`, as before. And the review surface
    grows from ~12 to ~40 lines a list, so the review asks per line "is this an idea the source
    puts forward?" and per list "is anything central missing?" — not what to cut, which is the
    judgement measured above to be unshared.
  - **The first 50-list generation and the five reviews made on it are void**, kept as
    `temp/key_facts.v1-capped.json` and `temp/checklist-review.v1-capped.md`. `generate` refuses
    to mix lists built under two prompt versions, so the old file had to move aside.
  - **The uncapped key-points list was rejected on reading it.** The pilot read as a table of
    contents — every enumerated item and segment of a source as its own line — with much of it
    useless to someone deciding whether to watch. The user's framing, which ends the checklist
    line of work: the stage evaluates the *chosen model* under the existing product prompt, so
    labels belong on the summaries it generated, not on a reference that amounts to a second,
    competing summary. `KEY_FACTS` and `checklists.py` were deleted afterwards; nothing
    was ever pushed to the datasets.
- **Generation costs about $0.06–0.08 per item, not the cents a short prompt suggests.** 48 items
  came to **$2.79** on Opus under the capped prompt, and the uncapped pilot to **$0.47** for six.
  The output is a few dozen short sentences; the bill is mostly the *source*, up to
  120k characters of it at input rates. Anything priced per item here scales with source length,
  so estimate from the corpus rather than from the reply. `generate` discards the usage `ask`
  returns, so the number came from the credit balance either side of the run — the same gap the
  compare report has.

## Tier 1: binary sub-checks, never weighted points

Every rule in `prompts.py` is stated as an absolute — "Respond in {language}" has no
60%-credit reading — so a weighted composite would invent numbers and hide *which* rule broke,
which is the only thing the screening stage needs to know. The Langfuse code evaluator
`tier1-on-experiments` emits `t1_language_match`, `t1_script_clean` and `t1_bullet_count` (BOOLEAN),
`t1_compression` (NUMERIC) and the derived `t1_pass`, which ANDs the applicable binary checks.
Screening drops a model scoring `t1_pass` on under 70% of items. Three judgements are
deliberate:

- The language check passes at **70%** Cyrillic letters, not 95%. Correct output still carries
  Latin proper nouns, so a stricter floor rejects good summaries while adding nothing against a
  model that answered in the wrong language outright.
- **`t1_script_clean` catches what the ratio cannot: a stray foreign-script letter inside Russian
  prose.** It fails on any letter outside Latin (with its extensions), Greek and Cyrillic. Added
  2026-09-26 after `tencent/hy3` wrote `近` and `复杂` into two of 32 summaries that the ratio passed
  at 0.973 and 0.928. On the local sample it fired 3 times in 326 summaries, all real: those two,
  and one production summary (a `ל` in "видео о ל watermelon", not in the source). Latin stays
  allowed by decision — names and terms are legitimate — and Greek for symbols such as μ or Δ.
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

The one place the failure is visible is the evaluator update (`PATCH /v2/evaluators/{id}`, run
by `install_tier1.py`), whose preflight executes the source against sample data and reports the
exception and line number — which makes reinstalling the evaluator the cheapest way to test it, and means
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
- **Evaluators moved from `unstable/evaluators` to `v2/evaluators`, and the old route now returns
  404** (found 2026-09-26). Semantics changed with it: `POST /v2/evaluators` always creates a
  *new* evaluator at version 1, bound to no rule, so re-posting the name — which used to add a
  version — would now upload the code and score nothing. A new version is a `PATCH` of the
  existing evaluator with `type` and every definition field; rules always use the latest
  version, so the rule needs no edit. The live evaluator is named `tier1-on-experiments`, not the
  `tier1-deterministic` the old script posted, and `install_tier1.py` finds it by that name.

### One evaluator, not one per score

Splitting `tier1-on-experiments` into one evaluator per score was considered and **deferred**,
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

**Tier 2 is faithfulness alone since 2026-09-26.** `t2_no_filler` was removed: it was never
calibrated, so in a filter it would drop models on a judgement nobody had checked, and padding
is visible the moment the user reads a survivor. The harness keeps only checks that are either
deterministic (Tier 1) or calibrated (faithfulness).

**Tier 3 pairwise was removed on 2026-09-26**, along with `stage2.py duels` and the pairwise half
of `calibrate.py`. It never calibrated (best round 78% / κ 0.23), its hand labels were deleted
with everything else older than 30 days, and readability is a judgement the user makes by
reading the survivors — with candidate models changing constantly, a judge would need
recalibrating as often as the field moves. The Tier 3 sections below are history, kept so the
approach is not rebuilt without its lessons.

Both lived in `scripts/eval/judge.py`, a local runner that posts scores back through the API into
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
- **Tier 2 stays local by choice, not by constraint.** Faithfulness is a per-item
  single-observation judgement, so it would fit a managed evaluator. Two
  things are given up by moving them, and both are load-bearing rather than stylistic: the
  **judge reports and the runner decides** (a managed evaluator's output definition is one numeric
  `score` plus reasoning, so asking the model for `0.71` directly is exactly the arithmetic slip
  that design removed — and it could not carry the faithfulness `findings[]` at all, since that
  needs a list the runner gates on rather than a number), and `judge_version` **pins the prompt
  and schema by hash** so banked
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

**Calibration decides the judge model; it does not assume it.** `calibrate.py judge [<model>]`
takes a candidate judge as an argument, and running it once per candidate measures each against
the *same* hand labels. Every score carries the judge pin — model plus prompt hash — in its
metadata, which is what keeps two judges' verdicts separable: they write the same score names,
so without that grouping the second run silently overwrites the first and the comparison it was
run for is unreadable. `agreement` reports each pin as its own block.

Take the higher number, and when the cheaper judge clears the bar, **use it and spend the
difference on dataset items** — more items buy more statistical power than a better judge does.
One calibration round is small next to a compare stage, so measuring a second judge is cheap
relative to the decision it settles. Weigh it against the *whole* Tier 2/3 bill, not against the
round. Note the second constraint still binds: a judge below the candidates' tier measures its
own ceiling, so "cheaper" has a floor that a mid-tier model does not clear here.

**That floor was reached, and it decided the current pin.** The banked round has Opus 5 at
**88% agreement / kappa 0.65 — PASS** on faithfulness over 24 comparable items, against Sonnet 5
at 64% / 0.32 on the prompt it was run with. Sonnet was also probed on the *current* prompt and
reached roughly 75% / 0.19, so the redesign did not rescue it. `JUDGE_MODEL` is therefore Opus,
and the spend-the-difference rule simply does not arise when the cheap judge fails the gate.

The failure was one-directional and worth recognising again elsewhere: both models stayed clean
on **all 17** summaries the labels call faithful, so neither invents faults. They separated only
on the 7 the labels reject, where Opus found a material error in 4–5 and Sonnet in 1 — Sonnet
located the same passages but graded them `minor`. A weaker judge here does not hallucinate
problems; it **under-rates real ones**, which looks like agreement on the easy majority and
collapses on the cases that decide a ranking.

**A third judge was screened and rejected: `openai/gpt-5.6-sol-pro`.** On the *same* prompt pin as
the Opus round it reached **80% / kappa 0.56 — NOT CALIBRATED**, clearing the agreement bar and
missing the kappa one. It is the closest any alternative has come, and it still should not be used,
for two reasons that are worth separating.

**Its errors point the wrong way, and it breaks the property the paragraph above records.** Opus's
three disagreements are all *misses* — a fault the labels record and it did not. sol-pro has one
miss and **four false alarms**: it called four of the seventeen hand-accepted summaries unfaithful.
So "neither invents faults" held for the two Anthropic judges and does **not** generalise. Those
failures are not interchangeable: a judge that misses faults under-detects and punishes nobody, and
a judge that invents them **penalises good models in the ranking**, which is the thing the score
exists to produce. Weigh the direction of the errors, not only the agreement number — on agreement
alone sol-pro at 80% looks like a near-miss, and on error direction it is the worse instrument.

**And it is not cheaper, measured.** The price card says $2/$10 per M against Opus's $5/$25, so
2.5× — and the round came to **$0.057 per call against Opus's $0.058**. No saving at all: the
cheaper token price was spent on roughly 2.5× more tokens, almost certainly reasoning. This is the
second time a price card has misled here (Sonnet promised 5× and gave 2.2×), and the second time
in the more expensive direction. **Never quote a judge's cost from the catalog — measure a round.**

A useful consequence: the candidate pool keeps `openai/gpt-5.6-luna`. Adopting an OpenAI judge
would have forced it out under the family rule, and that trade — a permanent per-request saving on
a candidate, for a one-off saving on judging — was only ever worth making if the judging saving was
real. It was not.

**Quote the banked round, not a probe.** Probing the same items ahead of the round gave 92% /
0.78, and the round gave 88% / 0.65 — one item (`scr-11e822219c80`) graded `material` in the probe
and `minor` in the round. That item flipped on Sonnet too, so severity near the boundary is
unstable *per run* on both models, and a single round is a sample rather than a model's ceiling.
Cheap probes are still the right way to decide whether a round is worth paying for; they are just
not the number to record.

**Judge spend is measured, not estimated.** `_call_body` sets `usage: {include: true}`, so
OpenRouter prices every call and `ask` returns that alongside the verdict; `run_judge` totals it
and prints what the round actually cost. Do not reconstruct a bill from a price table written
down here — vendor prices move, and one of them is on a dated introductory rate.

#### JEV: reachable without pydantic-ai, and what one round of binary questions showed

`typesafe/jev-1.13` (TypeSafe's "System One" model) is not an LLM: it returns typed decisions —
a choice among at most 255 options, a yes/no, a rubric score — each with a probability, and
generates no free text. **$0.042 per M input tokens, output free.** It cannot be called on
`chat/completions` (400: *"is a decisions model … Use the /api/alpha/decisions endpoint"*), but
**OpenRouter accepts TypeSafe's own protocol on `POST /api/alpha/decisions`** with the ordinary
OpenRouter key, so the harness reaches it with the same `urllib` it uses for Opus and needs no
pydantic-ai bump. The body is `{model, state, questions}`, where `state` is any JSON (here
`{source, summary}`) and each question is `{type: "noul", instructions, criteria: {true, false}}`;
the reply is `answers[name].noul`, the probability of true. Several questions go in one call.
Three identical calls returned identical probabilities. (pydantic-ai's `TypeSafeModel` wraps the
same protocol through `typesafe-sdk`, which posts to `/v1/systemone` on `api.typesafe.ai`.)

**The context limit is real and falls inside this corpus.** A 48k-character source plus summary
was 20,797 input tokens and fit; sources of 53k, 79k and 157k characters returned
`max_tokens_exceeded`. So anything given the whole source covers roughly the shorter 85–90% of
production items and nothing past ~50k characters.

**One round, 2026-09-26: seven binary questions on 25 production summaries**, JEV against Opus
(`key_points_for_transcript` traces, one per distinct source, spread 1k–157k characters). Cost
**$0.0076** for JEV's 22 calls against **$2.15** for Opus's 25 plus three re-runs. There were no
hand labels, so this measures agreement between two judges, not either one's accuracy.
- **The omission questions barely vary on the production model.** Opus answered true on 22–24 of
  24 for `main_takeaway`, `major_topics`, `ending_covered`, `advice_kept` and `worth_time`, and the
  few falses were partly the question's fault: a skipped sponsor segment was reported as a missing
  major topic and a promoted course as dropped advice. A question with no negatives cannot rank
  models; `worth_time` and `ending_covered` had none.
- **A bare yes/no reintroduces the faithfulness failure.** Opus called 8 of 24 summaries
  unsupported, and several of its reasons argue themselves out of the flag ("… is consistent",
  "slight distortion but largely supported"). This is the count-before-reasoning problem the
  enumerating faithfulness prompt fixed; a binary question has no severity gate to put back.
- **JEV ranks in Opus's direction but is not calibrated to it.** AUC against Opus's verdicts was
  0.79 (`no_unsupported`, 7 negatives), 0.84 (`distinct_bullets`, 3) and 0.75–1.00 on questions with
  a single negative; at the 0.5 threshold it said true on 20 of 21 for `no_unsupported`. Negatives
  this few make every one of those numbers soft.
- **Opus returned malformed tool calls on 5 of 25** with a seven-object schema — once the other
  six answers nested as XML text inside the first field, once a single field only — and one of
  three re-runs failed again. OpenRouter does not enforce `required`; validate before scoring.

**Round 2, same day: the revised questions do not separate models.** Five questions (`worth_time`
dropped for never varying, `no_unsupported` dropped because faithfulness stays with the calibrated
enumerating judge; sponsor reads, ads and promotion excluded explicitly) on 24 production sources
of 1k–44k characters, each summarised twice: by whichever model the user had selected in the bot
when the trace was recorded (the trace's own output), and by `openai/gpt-6-luna` through
`eval_client.summarize`. **"Production" is not one model**: the bot lets the user switch, and the
traces' GENERATION observations show `openai/gpt-5.6-luna` on 24 of the 32 sampled sources,
`meta/muse-spark-1.2` on 7 and `thinkingmachines/inkling` on 1. The trace itself carries no model
id; it sits on the observation. **Opus answered true on all five questions
for all 48 summaries** — zero negatives, so no paired difference between the two models on any
question — even though luna's summaries are ~23% shorter (median 2,188 against 2,844 characters).
JEV's mean probabilities were within 0.06 between the two models on every question. Excluding
promotion removed round 1's false negatives and left nothing behind them.

What that settles: on sources under ~45k characters, "does the summary keep the main takeaway, the
major topics, the ending, the advice, without repeating itself" is passed by any competent
key-points summary, so it cannot rank candidates. Where models differ is finer — which points,
how accurately, how readably — which is what faithfulness and pairwise measure. Two gaps remain
untested and both bias toward passing: sources over 45k characters were excluded (round 1's only
plausible real omissions were on 35k and 53k sources), and the 8 sources dropped for malformed
Opus replies may not be random. Cost: luna $0.027 for 32 summaries, JEV $0.017 for 62 calls, Opus
$3.35 for 55 usable verdicts — **Opus returned malformed tool calls on roughly one call in four**,
often the same summary on retry.

A third arm, `tencent/hy3`, on the same sources: its summaries are the shortest of the three
(median 1,708 characters against luna's 2,188 and the traces' 2,844), and on the 17 sources where
Opus returned valid verdicts for all three models it drew **2 negatives in 85 answers** — one
repeated pair of bullets, one dropped piece of usage advice — against 0 for the other two. Two
negatives on 17 sources is not a ranking. hy3 cost $0.094 for 32 summaries, JEV $0.0095, and Opus
$1.17, with 7 of 24 replies malformed again.

**The calibrated faithfulness judge on the same three arms** (pin `8f66738fe8e7`, unchanged since
calibration, 24 sources, 72 verdicts, $3.08 by the credit balance against $3.52 the calls reported):

| arm | pass | material | minor | borderline |
|---|---|---|---|---|
| traces (mostly `gpt-5.6-luna`) | 22/24 | 2 | 24 | 51 |
| `openai/gpt-6-luna` | 23/24 | 1 | 18 | 29 |
| `tencent/hy3` | 23/24 | 1 | 39 | 39 |

No arm separates on the gated score: paired, each pair of arms splits 1–2 or 1–1 on the items
only one of them passes. The one visible difference is below the gate — hy3 draws the most
`minor` findings while writing the shortest summaries — and `minor` was never calibrated, so it
is a lead, not a result. Read together with the binary rounds: on sources under ~45k characters
the three are indistinguishable on everything measured, which makes price and readability the
remaining axes. Per M tokens at the time: `gpt-6-luna` $0.10/$0.50, `hy3` $0.13/$0.53,
`gpt-5.6-luna` $0.20/$1.20.

### Three details of the judge are load-bearing

The judge never returns a verdict already reduced to one number — faithfulness enumerates and the
runner gates — because a model asked directly for `0.71` makes arithmetic slips no prompt wording
fixes (the retired coverage judge counted entailed facts for the same reason). Those schemas declare their **verdict field before
`reasoning`**, since models emit in declared order and it is the long reasoning string that runs
into `max_tokens` — a truncated call then still carries the answer. And OpenRouter does not
enforce `required` on this route, so a missing field has to be caught explicitly rather than
trusted. Pairwise runs **both orders and discards disagreements**; the discard rate is itself a
judge-quality signal.

### Faithfulness enumerates; it does not count

The faithfulness schema is the exception to the ordering above, and calibration is what forced
it. Declaring a count ahead of the reasoning makes the model commit to a number **before it has
thought**, and the number cannot then be revised: across 25 hand-labelled items one verdict's own
reasoning ended *"Re-checking, all claims are supported; retracting to 0 unsupported"* while the
stored count stayed 1, and another wrote *"Actually hard to find clear unsupported claims"*
under a count of 2. The reasoning that would explain the number was then truncated at the
900-character comment cap, so the count could be neither justified nor audited. That single
defect produced most of one judge's false positives.

So the judge returns `findings[]` — each entry carrying the claim, what the source actually says,
a `severity` and a `type` — and **the runner applies the gate**. An empty list is a clean verdict.
Truncation now loses the tail of a list rather than the grounds for a number already asserted.

Three consequences worth keeping:

- **Only `material` moves the score.** `minor` and `borderline` are recorded and deliberately do
  not, because the hand labels tolerate a real-but-immaterial error and reject a changed meaning.
  Gating inside the prompt instead would let one nitpick decide the verdict with nothing left to
  inspect afterwards.
- **There is no claim total to divide by, and asking for one was tried.** The model supplied it
  erratically — absent entirely on one call, and **6** against the previous prompt's **15** on the
  very same summary. A denominator that reflects how finely the model chose to slice the summary,
  and that sometimes fails to arrive, cannot carry a quality score. `t2_faithfulness` is therefore
  **1 or 0**, so a run's mean reads as the share of its summaries free of a material error — the
  same statement the hand labels make, which is what lets the calibration number say anything
  about the score at all.
- **The severity boundary is the hard part, and prose alone does not convey it.** Tightening the
  wording moved nothing measurable. Adding a worked minor/material pair as a few-shot example was
  tried and **removed**: it produced no net gain — one item gained, another lost — while
  contaminating a calibration item by handing the judge its answer. Do not re-add examples drawn
  from the calibration set; the set is 25 items, so one of them is worth four points of agreement.

### Comprehensibility is substance; elegance is not

Now that Tier 3 judges readability alone, this distinction carries more weight rather than less —
it is what keeps "better to read" from collapsing into "sounds nicer". The prompt tells the judge
to ignore which summary sounds more confident and to give no credit for polish that does not help
a reader understand. What it does count is language a reader has to fight (clumsy translation,
mangled syntax, phrasing that leaves the meaning in doubt) and points so compressed that the
thread between them has to be reconstructed: **a point the reader cannot extract has not been
delivered**, whether the obstacle is bad syntax or missing connective tissue.

Translationese is a live failure mode here, since summaries are Russian while sources usually are
not, so discounting it entirely would blind the one dimension meant to catch it.

The labeller has to apply the same line, and the cost of not doing so is now measured rather than
hypothetical: **a whole round was spent, twice, on a dimension where the two sides were asked
different questions**, and it read as a miscalibrated judge for as long as nobody compared the
instructions. **Specification comes before calibration.** Tuning a prompt against disagreements
is what calibration is for, but only once both sides are asked the same thing — and the cheapest
way to check that is to read the judge's own reasoning on the disagreements before touching
anything, because it states the criterion it applied.

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
- **Name the dimension being re-measured: `judge [<model>] [faithfulness|pairwise]`.** Prompts
  move one dimension at a time, so a whole-round re-run pays to re-score a dimension whose prompt
  has not changed — and it does not merely waste the money. Severity near the boundary is
  unstable per run, so the second round *replaces* a banked, quoted result with a different
  number for the same prompt. The two arguments are order-independent; omitting the dimension
  keeps the old both-dimensions behaviour.
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
  model was shown as A. They are free, named `calibration pair`, and never read as bot traffic. Those traces are keyed by the duel they were built from, not only by
  the item: change `PAIR_A`/`PAIR_B` and `setup` writes fresh ones and pulls the previous duel's
  items out of the queue, because a trace from another duel answers a different question while
  looking identical in the UI.
- **Pick the calibration duel by which axis the spec is least sure of**, not by which models
  matter most commercially. Two models a reader rates equally mostly produce TIE, which inflates
  chance agreement and collapses kappa; two that differ on a criterion the prompt already
  handles carefully test nothing. Holding the well-specified axis roughly fixed — length, say —
  and varying the newest one is what makes 25 labels informative.
- **One queue holds both dimensions.** The Hobby plan allows exactly one annotation queue, and
  no API route updates *or deletes* a queue after creation. A queue missing a config simply
  never offers that channel, on any item, with nothing to say why. Mis-setting a channel on the
  wrong kind of item is harmless: agreement maps observations back to sample items, and a label
  on an observation outside that mapping is ignored.
- **The UI *can* attach a score config to an existing queue** — verified, and it takes effect
  immediately with the queue's items and their statuses intact. So a queue built short of a
  config is fixed in its settings; it never has to be deleted and rebuilt. The API restriction
  above is an API restriction only, and `setup` creating a queue with every config it will need
  stays the rule for a *new* queue rather than a repair procedure.
- **Labels survive the queue.** A label is a score on an observation; the queue is only a work
  list pointing at observations. Deleting and rebuilding the queue therefore loses no labelling
  — the rebuilt items come back `PENDING` while their scores stay in the score table and keep
  mapping. Verified with 25 `h_faithful` labels in hand.
- **The sample is derived, not stored** — items sorted by id and dealt round-robin across the
  screening runs. Agreement is only comparable across prompt revisions when the items stay
  fixed, and a stored manifest would drift from the runs it names.
- **Pairwise labelling is blind, and the blinding is per item.** Which model appears as A is
  derived from a hash of the item id, so the layout reproduces without a manifest while no
  vendor can be tracked down the file. These labels *become the standard the judge is measured
  against*, so a preference leaking into them is not a bias in one score — it is a bias baked
  into the target. Verdicts are stored canonically (A always means the first model), so a human
  label and a judge label are the same kind of statement.
- **The unflip has been verified against real labels, and the blinded view is not the result.**
  The stored `columns_flipped` matched the value derived from the item id on all 50 spans, and
  unflipping scored 11/22 against the judge where leaving it raw scored 8/22. The trap is
  reading the *blinded* tally as a preference: 25 labels came out **12 / 12 / 1 TIE** as shown
  and **19 / 5 / 1** once canonical. The even split is evidence the blinding worked, nothing
  more — quote the canonical figures, never the as-shown ones.
- **Read only the current duel's spans.** A previous duel's spans survive forever, nothing in v4
  deletes an observation, and they carry the same `dataset_item_id` — so an unfiltered read maps
  a label about two *other* models onto this comparison. `setup` filters on `run_a`/`run_b` when
  it enqueues and `agreement` now filters the same way on the way back out.
- **A skewed marginal collapses kappa exactly as a TIE-heavy one does.** The duel above ran
  19/5/1, and that lopsidedness pushed chance agreement to ~57% against an observed 50%, giving a
  **negative** kappa. The guidance to avoid two models a reader rates equally is only half the
  rule: *any* strongly unbalanced label distribution starves kappa, so pick a duel the labeller
  will split somewhere near evenly, in either direction.

An `INCONSISTENT` pairwise verdict is the judge **abstaining**, not disagreeing: the two orders
contradicted each other, so there is no opinion to compare. Those are excluded from agreement
and kappa and reported as a discard rate, exactly as the compare stage discards them. Counting
them against the judge would understate agreement and quietly merge position bias with error.

### Tier 3 ranked readability, not overall quality (removed)

**Pairwise must not weigh factual accuracy, and the prompt used to open by demanding
it.** That single line — *"Weigh faithfulness to the source first"* — is what made Tier 3
uncalibratable, and it is worth understanding rather than just fixing, because the failure was
invisible in every individual verdict.

The two dimensions are deliberately **orthogonal**. `h_faithful` asks whether the source supports
the claims, per summary. `h_pairwise` asks which summary is better to *read* — style, coherence,
comprehensibility. Scoring accuracy in both counts the same defect twice, and worse, it lets
accuracy dominate the comparison so completely that the readability signal never surfaces: a
judge told to rank faithfulness first will decide almost every pair on the first criterion and
never reach the second.

That is exactly what the banked round shows. The labeller applied the split as designed; the
judge obeyed its prompt; nine of eleven disagreements have the judge citing a factual error in
the summary the labeller preferred on style. **Both sides were internally consistent and
answering different questions**, which is why a stronger judge made the number worse rather than
better — Opus simply found more of the errors it had been told to rank on.

Three consequences follow, and the second is easy to miss:

- **The source is still shown to the pairwise judge**, because dense and disconnected cannot be
  told apart without knowing what was being condensed. The prompt therefore has to say what the
  source is *not* for, or the judge starts checking claims against it again by default.
- **`t3_pairwise_win` no longer means "better summary".** It means "better to read", so it cannot
  by itself rank candidates the way the compare stage was originally written to expect. A ranking
  now has to combine it with `t2_faithfulness` rather than read Tier 3 as the
  verdict. The score name predates this and is now misleading; renaming it would orphan any
  banked score from its history, so it is left alone deliberately — read this paragraph, not the
  name.
- **A summary in the wrong language does not lose the duel for being in the wrong language.** The
  judge had been disqualifying it on its own initiative — *"a reader of the intended output gets
  nothing"* — which is the double-counting rule again from a different direction: `t1_language_match`
  already scores output language, per summary and binary, so deciding a duel on it both counts the
  defect twice and ends the comparison before readability is reached. The labeller applies the
  same line and preferred an English summary over a badly written Russian one. The prompt now says
  so explicitly, because left unsaid the judge supplies the disqualification itself.

  This is a **specification** decision, not a preference about output language: the bot must still
  answer in the language asked for, and `t1_language_match` is where that is enforced and where a
  failure like minimax's 8% drift rate shows up.

#### Density is a cost, and this is the defect a prohibition does not fix

Excluding accuracy left a second leak of the same shape, found by re-reading the eleven
disagreements after the rewrite: **six were decided on how much of the source each summary
retained**, a seventh cited it as a secondary reason, and only two turned on the criteria the
prompt actually lists. Retained substance is `t2_coverage`'s question, measured per summary
against a fixed checklist, so weighing it here is the double-count again — and the prompt did not
forbid it, having forbidden only claim-checking. It now forbids both, and says the source is not
an inventory to score omissions against.

`PAIRWISE` still tells the judge that coverage "is measured separately, per summary, against a
fixed checklist", which stopped being true when the coverage judge was removed. It is left as is
on purpose: the instruction it supports — do not weigh how much each summary retained — is still
the right one, and editing the sentence would move the pairwise pin (`ccc8bc85092a`) for no
change in what the judge is asked to do. Reword it the next time the prompt changes for a real
reason.

The direction of the disagreement is the part worth keeping, because a prohibition alone would
not have fixed it. In all six the judge named the *denser* summary as the one that retained more
and picked it; the labeller picked the other one every time. Across the whole duel the labeller
preferred the longer model 19–5, and the judge preferred the shorter one in 9 of the 11
disagreements. So the two sides were not disagreeing about how much was kept — they were
disagreeing about whether packing it in is a virtue:

- **The judge treated density as a virtue**, crediting facts-per-line and forgiving length when
  the payload justified it — *"A is longer but earns it."*
- **The labeller treated density as a cost**, which is what the prompt's own Coherence bullet
  already said: a stack of noun phrases reads as fragments *however much it contains*.

The rule was therefore already in the prompt and lost to a criterion nothing ruled out. The fix
is not another prohibition but an explicit statement that density is a cost — plus the note that
economy and density are not the same thing, since cutting the words that carried the connection
between two points is damage, not concision.

**The general lesson, now on its third instance: what the pairwise judge decides on is whatever
the prompt fails to exclude.** Accuracy, output language and retained coverage each arrived this
way, each looked like a miscalibrated judge, and each was found the same way — by reading the
judge's own stated reasons on the disagreements rather than by tuning wording. Do that read
before paying for any round.

### The round that produced this: pairwise was not calibrated on either judge

These are the numbers the mismatch above produced, kept because they are what a
criterion-mismatch looks like from the outside — near-chance agreement, negative kappa, and a
*stronger* judge scoring worse:

| judge | agreement | kappa | inconsistent |
|---|---|---|---|
| Sonnet 5 | 50% | −0.05 | 12% |
| Opus 5 | **39%** | **−0.09** | **28%** |

Neither is evidence about judge quality on the question Tier 3 is now asking, and neither is a
baseline to improve on: the prompt they were run under has been replaced, so `judge_version`
moved and both are unpinned. Re-measure before concluding anything.

The 28% discard rate looked like a **second, independent** defect: on seven pairs the judge
contradicted itself when the order was swapped, which is position sensitivity rather than
criterion mismatch, and it more than doubled when the judge got stronger. It was not independent.
Fixing the specification took it to 8% without anything addressing position bias directly — so a
high discard rate here meant the *comparison* was under-determined, not that the judge was
careless. A judge asked a question its instructions cannot settle will answer it differently in
the two orders.

### The round that measured the rewritten prompt: better on every axis, still not calibrated

Same 25 hand labels, same judge model, three specification fixes later
(`pairwise@ccc8bc85092a`):

| judge / prompt | agreement | kappa | inconsistent |
|---|---|---|---|
| Opus 5, accuracy-first | 39% | −0.09 | 28% |
| Sonnet 5, accuracy-first | 50% | −0.05 | 12% |
| **Opus 5, readability** | **78%** | 0.23 | **8%** |
| Sonnet 5, readability | 50% | **0.29** | **60%** |

Agreement doubled, the discard rate fell to a third, and kappa went from negative to positive —
and the verdict is still **NOT CALIBRATED**, because 0.23 is nowhere near 0.6. Understanding why
those two facts sit together is the whole lesson of this round.

**The marginal is degenerate.** The judge answered A on 22 of 25 and B once; the labeller answered
A 19 times, B 5 and TIE once. Two raters who both almost always say A agree often by construction:
chance agreement alone is about 72% here, so 78% observed buys almost nothing above it. **Raw
agreement passed the ~80% bar while kappa says the number is uninformative** — which is exactly
why the target is stated as both, and why quoting agreement alone would have declared this
calibrated.

All five disagreements are the same shape: `human=B` or `TIE` against `judge=A`. The judge never
picks the second model where the labeller does.

**Length bias was the obvious suspect and the data clears it.** Telling a judge that density is a
cost could plausibly push it into preferring whichever summary is longer, and the candidate that
won 22 times is systematically the longer one. It did not happen. Mean A/B character ratio where
the judge says A is **1.23**, against **1.26** where the labeller says A — indistinguishable. The
judge's single B came on the item where A was **1.75×** longer, the opposite of a length
preference. And the labeller's own B verdicts average **1.32**, so those are not "the shorter one
wins" either; they are cases where the extra length stopped paying for itself.

So the prompt is not over-corrected, and the judge tracks the labeller across the easy majority.
What it cannot do is call the five hard ones, and **this duel does not contain enough of them to
certify anything either way**. That is the duel-selection rule biting from the other side: a
19/5/1 split starves kappa whichever direction it leans, and picking this pair for varying the
newest criterion did not make the labeller split evenly on it.

**A better round on this duel cannot fix this.** The next move for Tier 3 is a duel the labeller
splits closer to evenly, which costs 25 fresh hand labels and about $2.80 of judge time — not
another prompt revision. Until then Tier 3 stays uncalibrated and a ranking rests on
`t2_faithfulness`.

#### Do not read that table's kappa column across rows

Sonnet on the rewritten prompt scores kappa **0.29 against Opus's 0.23**, and it costs less than
half as much per call. Reading the column downward says take Sonnet. That is wrong, and the reason
is worth holding onto because the table itself does not show it.

Sonnet discarded **60%** of the pairs. Its kappa is computed on the **10 verdicts that survived**,
Opus's on 23 — different samples, different sizes, and no basis for comparison. Sonnet's number is
higher precisely *because* what survived is balanced (3 A / 3 B / 4 TIE), and a balanced marginal
lowers chance agreement; the same property that starves Opus's kappa inflates Sonnet's. Four of
its ten consistent verdicts are TIE, so it is hedging rather than deciding.

**Kappa is only comparable between judges at comparable discard rates.** Read the discard column
first: it is the one number here that is a direct judge-quality signal, needs no hand labels at
all, and cannot be inflated by a favourable marginal.

**A tighter specification made the weaker judge worse, and that direction is the finding.** Sonnet
went from 12% discards to 60% on the rewritten prompt while Opus went from 28% to 8%. The new
prompt asks the judge to hold four exclusions at once — accuracy, output language, retained
coverage, density-as-virtue — and apply what is left. Holding them is capability-bound. So the
failure mode is not the one faithfulness showed, where a weaker judge *under-rated* real problems;
here the weaker judge does not disagree at all, it becomes **unstable**, answering differently
depending on which summary it sees first. Expect a precision-raising prompt edit to cost a weak
judge consistency, and re-check the discard rate rather than the agreement after making one.

This closes the spend-the-difference question for Tier 3 for now: the cheap judge does not clear
the bar, for a second and different reason than on faithfulness. It cost $1.24 to settle with
numbers instead of assumption, which is the right trade — do not re-litigate it from the price
table.

### Two operational traps this round exposed

- **A 402 mid-round is a reservation failure, not an empty account, and it is not the
  `openrouter_key_limit` trap recorded above.** OpenRouter reserves the *maximum possible* cost of
  a call — prompt tokens plus the whole `max_tokens` budget — against the remaining credit, so a
  balance that comfortably covers an entire round still refuses one call carrying a full-size
  source. The first round died at item 14 of 25 with $3.79 left and $19.28 of key limit unused,
  and a trivial call on the same key succeeded seconds later. Check the **credit balance**
  (`/api/v1/credits`), not the key limit (`/api/v1/key`); they are different numbers and this
  round had room in the one that gets checked first.
- **The verdicts bought before the crash survived**, because the Langfuse SDK flushes at exit even
  though `run_judge`'s own `client.flush()` never ran. Do not rely on that — but do check what
  landed before paying again. `run_judge` now skips sample items already banked under the current
  pin, filtered on the duel as well, so a killed round is resumed rather than repurchased. Editing
  the prompt moves the pin and re-runs everything, which is what makes a deliberate
  re-measurement still possible.
- **Judge spend is $0.056 per pairwise call on Opus**, measured over the 24-call resume at $1.3445;
  Sonnet is $0.025, only 2.2x cheaper rather than the 5x its price card suggests, because the bill
  is dominated by the source on input rather than by the short verdict. Two
  calls per pair, so a 25-item duel is about $2.80. That is the figure to size the round-robin
  from: seven candidates is 21 duels, ~2100 calls, on the order of **$120** — which is why the
  duel stage is a decision and not a step.

The generated labelling file is markdown containing *summaries that are themselves markdown*,
so a parser keyed on a `## ` prefix alone reattributes verdicts to headings the model wrote.
`labels` accepts a heading only when it names a known sample item. The failure mode is a
dropped label that reads as an unlabelled item, not as an error.

### The compare stage's report

`scripts/eval/stage2.py` holds what is built on top of `judge.py`: the sweep across models and
the aggregation the API does not provide. (It also held the Tier 3 round-robin driver until
pairwise was removed; mentions of duels below are history.) `sweep` validates every model id against the OpenRouter
catalog before spending anything, exactly as the screening sweep does — otherwise a typo in the
sixth id surfaces only after the first five runs are paid for.

**A mean never ranks a model here.** With 25–50 items a few points between two means is noise,
so every mean the report prints is paired with a test over *per-item* deltas — the sign test on
Tier 3 verdicts, and the same test on per-item Tier 2 deltas between two candidates. That is why
every candidate runs over the same items: controlling for item difficulty is worth roughly 3–4×
the sample size, and fifty paired items beat two hundred unpaired ones. The paired Tier 2 table
is also the cheap half of the ranking — it needs no judge call beyond the Tier 2 scores each run
already banked, so it is available before a single duel is paid for.

Five details are load-bearing:

- **A candidate is a model *and* a strategy.** `t1_pass` and the Tier 2 means rank models only
  within one strategy, so runs are keyed `<model> / <prompt_key>` throughout and a model swept
  under both strategies is two candidates that can duel each other.
- **Compare runs carry a `stage2 / ` prefix, for the same reason screening runs do.**
  `GET /experiments` returns seven fields and none of them is metadata, so which stage a run
  belongs to and which candidate produced it are readable *only* from the run name. Anything
  that discovers runs is therefore parsing names, and renaming a run orphans it from the report.
- **The bootstrap is seeded from a constant.** An unseeded interval moves on every read of the
  same banked verdicts, and that movement is indistinguishable from the data having changed.
- **The `unres` column merges two different things** — the judge abstaining because the two
  orders contradicted each other, and a call that never returned. Only the first is a
  judge-quality signal. `cmd_pairwise` banks a score for consistent verdicts *only*, so the
  report can see how many are missing but not why; `judge.py pairwise` prints the true split at
  run time. Do not read `unres` as the discard rate.
- **Pairwise scores are read from the score table, not from the experiment.** A pairwise score
  is anchored to run A's trace and carries the pair in its metadata, so filtering scores by
  experiment id returns nothing for it — the same trap as evaluator scores attaching to the
  observation.

The round-robin driver skips pairs already banked, matching on the **exact run names** their
scores carry. Re-running a candidate produces a new run name, so its pairs are duelled again —
which is what re-running it means.

### Two things the report does not print, and both change how its table reads

- **Only `t2_faithfulness` gets a paired test** (historical: the report no longer has a
  `t2_no_filler` column). `t2_no_filler` means were printed with nothing
  behind them, so they cannot rank anything and a reader of the table will not guess that from
  looking at it. Two further reasons not to read that column as a ranking: `t2_no_filler` has
  never been calibrated against hand labels the way faithfulness has, so it is a signal rather
  than a verdict; and malformed verdicts left it missing on **8 of 149** items, so its
  denominators differ per candidate (47, 46, 48) while the faithfulness column's do not.
- **There is no cost column, though cost is half the decision.** It is missing because the number
  is not obtainable from the harness rather than because nobody added it: the observation price
  fields come back `null` on the list endpoint, and `run_experiment` discards the usage `ask`
  returns. Judge spend *is* measured — `_call_body` sets `usage: {include: true}` and `run_judge`
  totals it — so the asymmetry is real: a calibration round reports what it cost and a sweep does
  not. Price a sweep from the live OpenRouter catalog, and do not write a price table down here;
  vendor prices move and at least one candidate is on a dated introductory rate.

### The first compare round, and what it settled

Three candidates over `summarization-compare-v1`, all on the same 50 items. Kept because the
paired tests are the point, not the means:

| candidate | t2_faithfulness | t2_no_filler | t1_pass | compression | latency |
|---|---|---|---|---|---|
| inkling | **0.860** | 0.875 | 100% | 0.1725 | 36.7s |
| minimax | 0.840 | 0.809 | **92%** | 0.1969 | 42.7s |
| stepfun | 0.653 | 0.804 | 100% | 0.1879 | 37.2s |

Paired sign tests on per-item `t2_faithfulness` deltas: **minimax vs inkling is 5 better / 6
worse, p = 1.000 — indistinguishable**; minimax vs stepfun 12/3, p = 0.035; stepfun vs inkling
4/14, p = 0.031. **The two means differing by 0.02 is exactly the noise the paired test exists to
catch**, and this round is the worked example: read the test, never the gap between two means.

Two findings the table does not carry on its face:

- **All 4 of minimax's `t1_pass` failures are `t1_language_match`** — it answered in English where
  Russian was asked, on **8% of 50** items. A single sub-check accounting for every failure is
  what makes `t1_pass` worth decomposing before reading it as a quality number.
- **Cost separates what the quality tests could not.** At list prices minimax was roughly 3.4×
  cheaper on output than inkling, which is the whole decision between two candidates the paired
  test calls indistinguishable — and it is precisely the column the report cannot print.

The ranking is **not** final: Tier 3 cannot contribute until pairwise calibrates.

## API shapes that cost real time to rediscover

Installing a code evaluator through the (now removed) unstable API had a shape trap, kept here
in case the v2 routes repeat it: on
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

A few more:

- **Nothing in v4 deletes an experiment.** `experiments` and `experiment-items` expose `list`
  only. The deprecated v3 `DELETE /datasets/{name}/runs/{runName}` returns **200** and clears
  the run from the v3 view, but the v4 experiment and its items survive — so a botched sweep is
  permanent and shows up in every listing afterwards. Score configs are the same shape: they
  archive, they do not delete. Plan for junk runs to be *named* rather than removed, and check
  a runner end to end on one item before sweeping a whole dataset with it.
- **A score's value: the OpenAPI spec and the live API disagree, and the live one wins.** The
  spec declares `CategoricalScore.value` a *number* (the category mapping) with the label in
  `stringValue`. What `GET /v3/scores` actually returns is `value: "A"` with `stringValue`
  absent — verified against 25 categorical hand labels. BOOLEAN is the same shape: the boolean
  in `value`, no `stringValue`. Reading only one field fails silently either way, yielding
  `None` or `0` for every verdict, which looks exactly like a judge that never ran.
  `langfuse_api.py` holds the one decoder, `score_value(row)`, covering both shapes; do not read
  `value` off a score row directly, and do not "correct" it to match the spec.
- **`subject` is its own `fields` group on `GET /v3/scores` and must be requested.** Without it
  a score row carries **no target at all** — no `observationId`, no `subject`, nothing saying
  what was scored. Any code mapping labels back to items then matches nothing and reports zero,
  which is indistinguishable from nobody having labelled anything. This cost real confusion with
  25 hand labels already saved. Note the shape differs by route: scores returned *inline* by
  `fields=core,scores` on `GET /experiment-items` carry `subject` without being asked.
- **No route updates or deletes an annotation queue.** `/annotation-queues` has GET and POST,
  `/annotation-queues/{queueId}` has **GET only** — no PATCH, no PUT, no DELETE. Only its
  *items* can be changed (`POST`, `PATCH`, `DELETE` on the items routes). So a queue created
  without a score config can never gain one through the API, and cannot be deleted through it
  either; both need the UI. Create a queue with every config it will ever need.
- Tier 2 evaluators attach through `Langfuse.run_experiment(evaluators=[…])` rather than by
  posting scores by hand — the run wires each `Evaluation` to the right item.
- **Score ingestion is asynchronous and can take longer than it looks.** A posted score was
  absent from `GET /v3/scores` six seconds after `flush()` and present twenty seconds later, so
  running `calibrate.py agreement` straight after `calibrate.py judge` reads fewer scores than
  were written and looks exactly like a judge that silently failed. Wait, or re-read, before
  concluding anything from a low count.
- **A `402` from OpenRouter usually means the API key's own limit, not an empty account.** The
  body distinguishes them: `limit_source: openrouter_key_limit` with a `remedy_hint` pointing at
  the key settings. The message reads *"This request requires more credits, or fewer max_tokens.
  You requested up to 65536 tokens, but can only afford 8028"* — OpenRouter reserves the
  **maximum possible** cost of a call, so a request is refused on `max_tokens` alone while the
  balance still shows plenty (verified with $19.51 available). Two consequences: the failure is
  per-request, so **judge calls kept working while candidate generation did not** — `_call_body`
  asks for 8000 tokens and the summariser for 65536 — and raising the key's monthly limit, not
  topping up the balance, is the fix.
- **A failed task is stored, not lost, and a partly failed run reads as a bad model.**
  `run_experiment` catches whatever the task raises and writes `Error: {exc}` into the item's
  output, then skips that item's Tier 2 evaluators — so no garbage Tier 2 score is banked, which
  is the good half. The bad half: **the Tier 1 rule still fires**, and it scores the English error
  string as a language failure. A sweep that lost 36 of 49 items to `402` therefore reported
  `t1_pass` 0.245 and `t1_language_match` 0.245 — a completely plausible verdict about a model
  that had in fact never answered. `stage1.py report` guards only the *total* case (every item at
  `t1_compression` 0); the partial case is caught by nothing, so `cmd_run` now counts items whose
  output begins with `Error:` and says so while there is still a sweep to stop.
- **A botched compare run does not have to be lived with, despite experiments being undeletable.**
  Langfuse appends a timestamp to the run name, and `discover_runs` walks newest-first with
  `setdefault`, so the freshest run per candidate wins and an earlier broken one is simply never
  read. That is what makes the documented advice — check a runner end to end on a couple of items
  before sweeping a whole dataset — cheap and safe rather than something that permanently
  pollutes the report. Do it; a 2-item probe costs cents and catches exactly this class of
  failure.
- **A judge call can come back `content_filter`, on content that explains nothing.** Opus refused
  one calibration item — a summary of a Google blog post about the Go language — returning a tool
  call with no arguments and `finish_reason: content_filter`. `_unpack` raises on the missing
  field, which is right for one call and wrong for a round: `run_judge` posts 75 scores and
  flushes only at the end, so an escaping exception discards every verdict already paid for. It
  therefore catches the refusal, drops that item, names it in the summary line, and continues.
  A dropped item has to be *named*: silently scoring fewer items than the sample holds is exactly
  what a broken runner also looks like.
- A Langfuse score **requires a target**. Passing `trace_id=None` fails with a bare
  `Bad request` while the calling code still prints success, so a pairwise score has to be
  anchored to something — run A's trace for that item is the natural choice.
- Dataset run names embed the model id, so they contain `/` and spaces and must be URL-encoded
  into REST paths or the segments split and the request 404s.
