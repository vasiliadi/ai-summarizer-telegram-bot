# STG-138 evaluation harness

Offline quality evaluation for the summarizer: run the registered models over a
dataset of real traced content, score the results, and compare. Nothing here is
imported by the bot — these are operational scripts, run by hand.

The methodology lives in Linear **STG-138**; the settled facts and the traps
live in `docs/context/architecture.md` under the Langfuse section. Read that
before changing anything here.

## Where state lives

State is split across three places, and only one of them is this directory.

| What | Where |
|---|---|
| Scripts, evaluator source | this directory (tracked) |
| Prompts, datasets, score configs, evaluator, rules, runs, scores | Langfuse (server) |
| `obs.json` raw harvest, ad-hoc probes | untracked, local only |

The evaluator is the part that surprises people: `tier1_evaluator.py` **never
runs on your machine**. Langfuse stores the source and executes it on its own
infrastructure when an experiment item arrives. The local file is only the
source you upload with `install_tier1.py`.

## Files

| File | Purpose |
|---|---|
| `_bootstrap.py` | Loads `.env`, puts `src/` on the import path, returns Langfuse REST credentials |
| `langfuse_api.py` | The only place that calls the Langfuse REST API. v4 endpoints, rate-limit aware |
| `tier1_evaluator.py` | Tier 1 deterministic scorers. Uploaded to Langfuse, executed there |
| `install_tier1.py` | Uploads the above. Its preflight is the only way to see the evaluator crash |
| `stage1.py` | §7 stage 1 — sweep every model, Tier 1 only, no judge calls; and the report |
| `judge.py` | Tier 2/3 LLM judge (`anthropic/claude-sonnet-5`), runs outside Langfuse |
| `rebuild_datasets.py` | Rebuilds both datasets from a raw harvest. Destructive; needs `--yes-wipe` |

## Usage

```bash
python scripts/eval/install_tier1.py          # after editing tier1_evaluator.py
python scripts/eval/stage1.py run             # costs money: one call per item per model
python scripts/eval/stage1.py report          # free, read-only
python scripts/eval/judge.py smoke 2          # costs money: judge calls
```

`stage1.py run` drives `llm.LLMClient`, the same path the bot uses, so each run
records cost, token usage and thinking level. A hand-rolled HTTP call records
none of those and leaves the run showing `$0.00`.

## Cost

`stage1.py report`, and anything else that only reads, is free. Everything that
generates or judges is not:

- a full stage-1 sweep is 25 items x every registered model, roughly $1;
- judge calls are the expensive part — budget those with §7 in front of you.

Re-scoring Tier 1 never costs anything: the summaries already exist as trace
outputs, so a broken scorer is fixed by reinstalling it and recomputing, not by
re-generating.

## Langfuse v4

Every read goes through `langfuse_api.py` and uses a v4 endpoint. Langfuse Cloud
removes the v3 endpoints on **2026-11-16**, so do not reintroduce
`GET /datasets/{name}/runs/{runName}`, `GET /traces/{id}`, or `GET /observations`
— the replacements are `GET /experiments` + `GET /experiment-items` (with
`fields=io,scores`) and `GET /v2/observations`. See the Langfuse section of
`docs/context/architecture.md` for the semantics that changed with them.
