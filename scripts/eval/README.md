# Evaluating models

`scripts/eval/` is an optional harness for deciding whether a new model belongs in
`MODEL_SPECS`. It summarises a fixed set of real sources with a candidate over OpenRouter, the
same way the bot does, and scores the results in [Langfuse](https://langfuse.com). It is a
**filter, not a ranking**: it drops models that are plainly broken and puts cost, length and a
fabrication signal beside the rest, and you choose between the survivors by reading them.

Each candidate gets three kinds of score:

- **Tier 1**: deterministic checks that Langfuse runs on every run for free. The summary has
  to be in Cyrillic, contain no letters from a foreign script, and be a list where a list was
  asked for. The harness evaluates Cyrillic summaries only. A model passing under 95% of items
  is dropped.
- **JEV** (`~typesafe/jev-latest`): asks, bullet by bullet, whether the source supports the
  claim. It costs about $0.02 a run and is read against the other candidates, never
  against a threshold.
- **Opus** (`anthropic/claude-opus-5.5`): lists every claim the source does not support,
  sorted into *invented* and *compression*. Only *invented* counts against the model. It
  costs about $3 a run, so it is run on finalists only.

## Setup

The harness needs the bot's full `.env` (see [.env](../../README.md#env) in the root README):
every script imports `src/config.py`, which fails at import on any missing required variable.
On top of that, all three `LANGFUSE_*` variables must be set — `LANGFUSE_BASE_URL` included,
even though the bot can run without it. Then set up the
Langfuse project once:

1. **Collect traces.** Run the bot with Langfuse tracing on until it has summarised a few
   dozen webpages and transcripts. The dataset is built from real traffic.
2. **Create an empty dataset** named `summarization-compare-v1` in the Langfuse UI.
3. **Fill it** from a fresh export of traced generations. The Langfuse API only returns the
   last 30 days on the free plan. The export command comes from the
   [Langfuse CLI](https://langfuse.com/docs), which needs Node.js:

   ```bash
   npx langfuse-cli api observations list --type GENERATION --fields core,io --json > obs.json
   uv run python scripts/eval/rebuild_datasets.py --yes-wipe obs.json
   ```

   The script picks up to 50 sources (fewer when a stratum lacks candidates), split across YouTube transcripts, audio transcripts and
   webpages. `--yes-wipe` is required because the script first deletes everything already in
   the dataset.
4. **Create the Tier 1 evaluator** in the Langfuse UI: a code evaluator named exactly
   `tier1-on-experiments`, plus an evaluation rule that runs it on experiments. The rule's
   filter must name the `summarization-compare-v1` dataset, because it scores only the
   datasets it names. Then upload the real code:

   ```bash
   uv run python scripts/eval/install_tier1.py
   ```

   Re-run it after every edit to `scripts/eval/tier1_evaluator.py`. Langfuse runs this code on
   its own servers, not on your machine, and a crash there shows nowhere else: this script's
   preflight check is the only place it is reported.

## Running

Models are named by their OpenRouter id, for example `vendor/model`. The harness checks every id
against the OpenRouter catalog before spending anything.

```bash
uv run python scripts/eval/install_tier1.py     # after every edit to tier1_evaluator.py
uv run python scripts/eval/stage2.py report [--all-pairs]  # free, read-only
uv run python scripts/eval/stage2.py sweep <openrouter-id> ... [--judge=jev|opus|none]  # COSTS MONEY: a compare run each
uv run python scripts/eval/stage2.py judge jev [<openrouter-id> ...]    # ~2 cents a run: JEV where missing
uv run python scripts/eval/stage2.py judge jev --rescore [<openrouter-id> ...]  # ~2 cents a run: JEV on every item again
uv run python scripts/eval/stage2.py judge opus <openrouter-id> ...     # ~$3 a run: Opus FABRICATED on finalists
```

Wait about a minute after a run before reading the report, because Langfuse ingests scores
asynchronously. Include the model you use now in the sweep, so candidates are compared against
it. On 50 items a gap between two averages can be noise: `--all-pairs` adds a per-item sign
test for every pair of models, which shows whether one really beats another. Harness runs
import the bot's config, so if Sentry is set up, their errors appear in your production stream.
