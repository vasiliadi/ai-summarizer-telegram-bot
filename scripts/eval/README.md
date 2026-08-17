# STG-138 evaluation harness

Offline quality evaluation for the summarizer: run the registered models over a
dataset of real traced content, score the results, and compare. Nothing here is
imported by the bot — these are operational scripts, run by hand.

**Read `docs/context/evals.md` before changing anything here.** This file covers
what to run; that one covers why, and holds the traps that are expensive to
rediscover. The methodology and its staged plan live in Linear **STG-138**.

## Files

| File | Purpose |
|---|---|
| `_bootstrap.py` | Loads `.env`, puts `src/` on the import path, returns Langfuse REST credentials |
| `langfuse_api.py` | The only place that calls the Langfuse REST API. v4 endpoints, rate-limit aware |
| `tier1_evaluator.py` | Tier 1 deterministic scorers. Uploaded to Langfuse, **executed there** |
| `install_tier1.py` | Uploads the above. Its preflight is the only way to see the evaluator crash |
| `stage1.py` | §7 stage 1 — sweep every model, Tier 1 only, no judge calls; report; failures |
| `judge.py` | Tier 2/3 LLM judge (`anthropic/claude-sonnet-5`), runs outside Langfuse |
| `rebuild_datasets.py` | Rebuilds both datasets from a raw harvest. Destructive; needs `--yes-wipe` |

## Usage

```bash
uv run python scripts/eval/install_tier1.py     # after editing tier1_evaluator.py
uv run python scripts/eval/stage1.py report     # free, read-only
uv run python scripts/eval/stage1.py failures   # free — which items failed, and why
uv run python scripts/eval/stage1.py run        # COSTS MONEY: one call per item per model
uv run python scripts/eval/judge.py smoke 2     # COSTS MONEY: judge calls
```

Run `install_tier1.py` after **every** edit to `tier1_evaluator.py`. Its preflight
executes the source against sample data, which is the only place a crash in the
evaluator is ever reported — at runtime the same crash is silent.

## Cost

Anything that only reads is free. Anything that generates or judges is not:

- a full stage-1 sweep is 25 items × every registered model, roughly **$1**;
- judge calls are the expensive part — budget those with §7 in front of you.

Re-scoring Tier 1 never costs anything: the summaries already exist as trace
outputs, so a broken scorer is fixed by reinstalling it and recomputing, not by
re-generating.

## Langfuse v4

Every read goes through `langfuse_api.py` and uses a v4 endpoint. Langfuse Cloud
removes the v3 endpoints on **2026-11-16**, so do not reintroduce
`GET /datasets/{name}/runs/{runName}`, `GET /traces/{id}` or `GET /observations`
— the replacements are `GET /experiments` + `GET /experiment-items` (with
`fields=io,scores`) and `GET /v2/observations`. The semantics that changed with
them are in `docs/context/evals.md`.
