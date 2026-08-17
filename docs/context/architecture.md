# Architecture

Use this stable document for high-level orientation. Update it only for an architectural
change (a new component, flow, or routing/fallback rewrite) or a durable external-service
gotcha (see *Cross-cutting patterns*), not for every handoff. Read the source for function
signatures, dependencies, and environment variables; do not mirror them here.

State facts inline instead of pointing to an issue, PR, or dashboard a reader may not be
able to access. Record provider behaviour the repo cannot demonstrate as the provider's
gotcha, so readers do not search for it in the source.

- Stack → `pyproject.toml` + `README.md`

---

## What it is

A private Telegram bot that summarizes content — webpages, YouTube/Castro
links, audio, voice, video, video notes, and documents — with an LLM, and
replies with the summary in the user's chosen language. Synchronous,
polling-based (`bot.infinity_polling`); no webhooks, no async framework.

## Why this stack

Rationale for the standing infrastructure choices — mostly not derivable from
`pyproject.toml` or `README.md`. Treat each as settled unless its bullet says
otherwise; reverse one only as a deliberate decision, not incidental cleanup.

- **Synchronous polling** (see above) — no webhooks or async framework are needed
  for this workload.
- **Valkey over Redis** — Aiven offers a free managed Valkey instance (linked in
  `README.md`); that is the whole reason. **Not** a settled constraint: the client
  speaks the Redis protocol, so either server works and swapping is fair game.
- **`redis` is declared directly, never as the `limits[redis]` extra** — that extra caps the
  client below 8.0.0, so it held the whole project a major version behind. Declaring `redis`
  as a plain entry in `[project.dependencies]` is what freed it, and the extra carries nothing
  else — `limits`' Redis storage backend ships in the core package. Re-adding `limits[redis]`
  silently rolls the client back under the cap; check the extra's own requirement before
  assuming a newer `limits` has lifted it. `scripts/cron.py` builds its Modal image with
  `--only-group modal`, so the `modal` group declares `redis` a second time; the two must
  move together.
- **Gemini primary, Replicate fallback** — Replicate (WhisperX) is a transcription path,
  never a swappable summarization model. It is taken when Gemini file processing exhausts
  its retries, and as the standing route for audio whenever the selected model is
  text-only (every OpenRouter model is).
- **pydantic-ai as the provider seam** — every model call goes through `llm.py`, so the
  registry (`config.MODEL_SPECS`) is what decides which provider serves a model id.
  Adding a model from a registered provider is a registry row; adding a provider is a
  branch in `build_model` plus a dependency extra, not a rewrite of `summary.py`. Google
  and OpenRouter are registered. The `else` in `build_model` still raises for a provider
  with no builder, and is covered by a test that fabricates a spec.
  The Gemini Files API is still called directly (`services.GeminiHelper`), because
  base64-inlining a 20 MB Telegram file inflates it past the inline-request limit.
- **Dropping or renaming a model id needs an Alembic data migration in the same PR** —
  `llm.py` and `summary.py` read `MODEL_SPECS[model_id]` unguarded, so a user whose stored
  `summarizing_model` left the registry gets a `KeyError` on every message they send; the
  migration rewrites those rows onto a surviving id. That rewrite alone changes no schema,
  so `uv-guide.md`'s schema-change rule is not what requires it. *Adding* an id needs no
  migration. Moving `DEFAULT_MODEL_ID_FOR_SUMMARY` also moves `models.UsersOrm`'s
  `server_default` (pinned by `test_orm_server_defaults_match_config`) and the column's own
  default.
- **OpenRouter models are text-delivery only** — registered with `supports_audio` and
  `supports_files` both False, which is about what this bot can *deliver*, not what the
  models read. OpenRouter has no file API, so a file would have to be base64-inlined —
  the same limit that keeps Gemini on its Files API — and pydantic-ai only accepts
  wav/mp3 audio inline, while this pipeline produces Opus `.ogg`. Upstream, several
  registered models advertise audio or file input — `meta/muse-spark-1.2` advertises
  both; matching the flags to the catalog without first building an inline path breaks
  the routing.
- **Thinking levels are pydantic-ai's, translated by pydantic-ai** — the allow-list is
  its `ThinkingEffort` (`minimal|low|medium|high|xhigh`), passed to the unified `thinking`
  setting, and each provider's model maps it. This codebase owns no mapping, which is what
  a test pinning `ALLOWED_THINKING_LEVELS` to `get_args(ThinkingEffort)` protects. Two
  consequences: Gemini receives `include_thoughts=True`, hard-coded beside the level in
  pydantic-ai's Google translation, so it generates thought summaries `run` discards —
  the accepted price of owning no mapping, **do not** reintroduce `google_thinking_config`
  to dodge it. And `xhigh` is indistinguishable from `high` on both registered providers
  (Gemini has no XHIGH; OpenRouter's `reasoning.effort` stops at high), so it is offered
  for a future provider, not for a difference users can feel today.
- **PostgreSQL for persistent user data, Valkey for ephemeral rate-limit counters** —
  the two have different durability needs.
- **Modal for serverless cron** — clears the bot's own per-user daily counters in
  Valkey without running a second container. The sweep is what makes the budget a
  daily one: `limits` keys the counter without a window stamp and expires it on a
  plain 24 h TTL, so left alone each user's budget would roll over 24 h after
  their own first request of the day rather than at a shared hour. Deleting the
  keys on a schedule is what pins that hour, so the cron is load-bearing, not a
  tidy-up. Also stated in `README.md`; keep the two in step.

## Component map (`src/`)

| Module | Role |
|--------|------|
| `main.py` | `BotApp` — Telegram entry point. Command handlers + the unified `handle_message`; routes by `content_type`; top-level error → user-message mapping. `build_app(container)` wires it from the composition root and registers its handlers; the `__main__` block just calls `build_app`, `run`, `shutdown`. |
| `handlers.py` | `MessageHandlers` — per-content-type handlers. Media validation, builds `SummaryKwargs` from the user record, picks the summarize path. |
| `summary.py` | `Summarizer` — the core summarization orchestrator. Owns the input-type branching, assembles the message content, and calls the injected `LLMClient.run`. |
| `llm.py` | `LLMClient` — the provider seam. Each instance holds two pydantic-ai `Agent`s — one traced, one with instrumentation off for uploaded-file runs (see Tracing below) — plus a model cache keyed by id across providers; model, instructions and settings are resolved per run. Provider dispatch lives in `build_model` (keyed on `config.MODEL_SPECS[...].provider`, Google and OpenRouter today); `build_settings` has no provider branch at all — every provider takes the agnostic `thinking` effort, so the one provider-specific setting there is (OpenRouter usage accounting) rides on the model instead. `OpenRouterCostReporter`, the wrapper `build_model` puts around every OpenRouter model, reports cost to the trace (see Tracing below). |
| `transcription.py` | `AudioTranscriber` (Replicate WhisperX) + `YouTubeTranscriber` (orchestrator over `ApiBackend` primary → `YtDlpBackend` fallback, mirroring `parsing.py`'s `ParserBackend`). |
| `download.py` | `Downloader` — YouTube audio (yt-dlp→mp3), Castro (scrape→mp3), Telegram file fetch. |
| `parsing.py` | `WebParser` — webpage text extraction, Exa primary → Tavily fallback. |
| `services.py` | `Messenger` (Telegram send with retry + 4096-unit chunking), `QuotaManager` (rate limits), `GeminiHelper` (MIME, file upload/poll), `Tracer` (names, tags and adds settings metadata to the Langfuse trace for a message, if one is opened). |
| `container.py` | `Container` + `build_container()` — the composition root; wires every collaborator to `config`'s clients. `Container` carries only the five roots `BotApp` holds (`bot`, `quota_manager`, `tracer`, `user_repo`, `handlers`); the rest of the graph is reached through `handlers`. |
| `database.py` | `UserRepository` — users table access (SQLAlchemy + Postgres). |
| `models.py` | `UsersOrm` — the single `users` table (id, approval, per-user settings, `daily_limit`). |
| `exceptions.py` | Domain exceptions: `LimitExceededError`, `WebParseError`, `TranscriptDownloadError`, `FetchTranscriptError`. |
| `config.py` | All third-party clients (by design — see Cross-cutting patterns) + the `MODEL_SPECS` registry, labels, defaults, limits, constants. Side-effectful import (Sentry, logging, env). |
| `prompts.py` | `PROMPTS` (strategy templates) + `SYSTEM_INSTRUCTION` + `prompt_version` (short hash over both, for trace metadata). |
| `domain.py` | `PrefixedText` + `format_prefixed_summary` — source-provenance prefixing. |
| `utils.py` | Proxy pick, temp-name gen, `classify_url` (shared URL routing), `compress_audio` (ffmpeg Opus 16k mono), `clean_up`. |
| `scripts/cron.py` | Modal serverless cron — clears the bot's per-user daily request-limit counters (`RPD`) in Valkey at midnight UTC, resetting every user's daily budget. |
| `scripts/db.py` | Standalone bootstrap script — creates the `users` table via its own `Base`/engine (separate from `src/models.py`); runs `create_all` at import. |

## Request flow

```
Telegram update
  └─ BotApp.handle_message
       ├─ select_user (Postgres) ─ reject if not approved
       └─ process_message_content  ── routes by content_type ──┐
                                                               │
  handlers.py:                                                 ▼
    audio / voice ───────────────► summarize(File)
    video / video_note ──────────► download_tg(.mp4) → compress_audio(.ogg) → summarize(path)
    document ────────────────────► summarize_with_document(File, mime)
    text (treated as URL) ── classify_url ──┬─ "youtube" / "castro" ► summarize(url)
                                            └─ "web"  ► WebParser.parse → summarize_text
```

### Summarizer input branching (`summary.py:summarize`)

`utils.classify_url` is the **single** source of URL routing: `handlers.handle_url`
calls it to pick the summarize path and `summarize` calls it again to pick the
download path. Neither may re-derive the kind on its own — a second, narrower
classifier here previously let www-prefixed and uppercase-host media URLs reach
the Gemini file upload with the URL string as their file path.

- **YouTube URL** → try transcript (`YouTubeTranscriber.get_transcript`); on
  success summarize the transcript. On failure → `Downloader.download_yt`
  audio, then the file path below.
- **Castro URL** → `Downloader.download_castro` audio → file path.
- **Telegram File** → `Downloader.download_tg(.ogg)` → file path.
- **File path** → `summarize_with_file` (upload to Gemini, generate). If that
  exhausts retries → fallback: `compress_audio` → `AudioTranscriber.transcribe`
  (Replicate) → `summarize_text`.

So there are two layered fallbacks for spoken content: transcript-first for
YouTube, and Gemini-file-first with a Replicate-transcription rescue for any
audio that Gemini can't process.

Both the rescue path and the modality check below go through
`_summarize_via_transcription`; the rescue call is nested inside its own `try`
so a `RetryError` raised by the transcription path does not re-enter it.

### Modality routing

Two `ModelSpec` flags decide what a selected model is actually handed.

`supports_audio` gates the native file-upload path: a model that cannot be sent
audio takes the Replicate transcription route instead, in `summarize` and —
because `SUPPORTED_DOCUMENT_MIME_TYPES` accepts `audio/ogg` — in
`summarize_with_document`. The transcript is then summarized by the model the
user chose, so their setting still decides the wording. This is the live path
for every OpenRouter model.

`supports_files` gates the Gemini upload in `summarize_with_document`: a
document that is not audio has no text-extraction path, and the upload only ever
goes to Gemini, so the request is summarized by `DEFAULT_MODEL_ID_FOR_SUMMARY`
instead — logged at WARNING, with no user-facing message and no change to the
stored setting. The audio branch keeps precedence over it. `summarize` needs no
such check: everything reaching its file branch is audio.

## Source-provenance prefixes

Summaries from the transcript, web-parse, and Replicate-rescue paths are
prefixed with an emoji marking where the content came from
(`format_prefixed_summary`). Direct Gemini-file summaries — audio, voice,
video, video notes, documents, and any URL whose audio is downloaded and sent
to Gemini — return the raw model text with **no** prefix.

| Prefix | Source |
|--------|--------|
| 📺 | YouTube transcript via `youtube_transcript_api` (primary) |
| 📹 | YouTube transcript via yt-dlp (fallback) |
| 📝 | Audio transcription via Replicate (Gemini-file rescue path) |
| 🌐 | Webpage via Exa |
| 🕸️ | Webpage via Tavily (fallback) |

## Cross-cutting patterns

- **Constructor injection.** Collaborators arrive via
  `__init__`, wired once by `container.py`'s `build_container()` from
  `config`'s third-party clients; `main.build_app` turns the graph into the
  running `BotApp`. No module-level service singletons or method aliases
  remain. `config.py` keeps the clients by design — `container.py`, not
  `config.py`, is the composition root. Unwinding to plain functions is
  **rejected**.
- **Quota model.** `check_quota(..., quantity=0)` is a pre-check that raises when
  the daily budget is exhausted but consumes nothing; `quantity=1` consumes one
  unit. A global per-minute limit throttles by sleeping. Counters live in Valkey;
  user data lives in Postgres. The cap is the bot's own cost control, not a
  mirror of any provider's allowance: `check_quota` takes no provider, so a
  request costs one unit whichever model was chosen, and the cap stands whether
  or not that model is free. Providers bill failed calls, so quota is counted
  per attempt by design — not a double-charge bug.
- **Retries.** Network/model calls use `tenacity` `@retry`; persistent failure
  surfaces as `RetryError`, which `handle_message` maps to a user-facing
  "try again later" message. Other mapped errors: `LimitExceededError`,
  `WebParseError`. All exceptions are sent to Sentry via `capture_exception`.
- **Sentry log collection is an explicit opt-in.** `config.py` passes
  `LoggingIntegration(capture_sentry_logs=True)` to `sentry_sdk.init`; that flag is what
  forwards stdlib `logging` records to Sentry Logs, and it defaults to **off**. The
  `enable_logs=True` option that used to do this became a no-op in sentry-sdk 2.68.0 and
  is slated for removal in the next major — passing it again only logs a warning. Drop
  the integration and error capture still works while logs silently stop arriving, which
  is what `test_sentry_opts_into_log_collection` pins. `init` runs *before*
  `logging.basicConfig(force=True)` and stays unaffected: the integration patches
  `logging.Logger.callHandlers` instead of attaching a root handler, so wiping the root
  handlers does not unhook it.
- **Uploaded files are not cleaned up on failure.** After a successful `files.upload`,
  `GeminiHelper.upload_and_wait_for_file` raises on three paths — missing name, `FAILED`
  state, the uri/mime guard — and deletes nothing. Deliberate, not a leak: both callers
  attempt at most twice (`stop_after_attempt(2)` on `summarize_with_file` and
  `summarize_with_document`), the missing-name path has no handle to delete with, and
  Gemini expires uploads on its own — provider behaviour, not visible in this repo.
- **Temp-file hygiene.** Downloads/compression write UUID-named temp files in the
  CWD; `clean_up` removes them, guarded by a `PROTECTED_FILES` snapshot taken at
  startup. On shutdown `clean_up(all_downloads=True)` sweeps the rest.
- **Fragmented downloads.** `download_yt` leaves yt-dlp's `skip_unavailable_fragments` at
  its default, so a download missing a few fragments still yields usable audio. Setting it
  to `False` is **rejected**: it would turn many tolerable downloads into hard failures,
  while the rare truncated file that crashes the ffmpeg fixup is retryable — `download_yt`
  makes at most two attempts on `DownloadError` (`stop_after_attempt(2)`).
- **Settings commands** use a one-time reply keyboard + `register_next_step_handler`
  (`_prompt_choice` → `proceed_*`) and validate against the allow-lists in `config.py`.
- **Tracing (optional), text input only.** Enabled only when `LANGFUSE_PUBLIC_KEY` and
  `LANGFUSE_SECRET_KEY` are set (`config.langfuse_client`, else `None`).
  `Agent.instrument_all()` then makes pydantic-ai emit an OpenTelemetry span per model
  call, which the OTel-based Langfuse SDK ingests — no provider-specific instrumentor.
  `LLMClient` overrides that to off for any run carrying an `UploadedFile`, because
  pydantic-ai serializes the file pointer rather than the bytes behind it: Langfuse
  would get real token usage with no content — a wrong cost signal, useless for
  datasets and evaluators. **Do not re-enable it for file runs.**
  Cost is not part of what pydantic-ai hands over: it publishes its `genai-prices`
  estimate as `operation.cost`, an attribute Langfuse does not read, and that table has
  no entry for half the registered OpenRouter ids anyway. Langfuse instead prices a
  generation by matching its model id against a model definition, which the Gemini ids
  match and no `provider/model` OpenRouter id does. So `LLMClient.build_model` asks
  OpenRouter for usage accounting and wraps the model in `OpenRouterCostReporter`, which
  copies the cost OpenRouter reports it charged onto the span as `gen_ai.usage.cost` —
  the attribute Langfuse ingests as the generation's cost. It must be a wrapper *inside*
  the instrumented model: pydantic-ai closes the generation span before `run_sync`
  returns, so nothing afterwards can reach it. Drop the wrapper and every OpenRouter
  trace silently goes back to tokens with no cost, which is the number the traces exist
  to compare models on. An id carrying OpenRouter's `:free` suffix is billed at zero, so its
  span does get a `gen_ai.usage.cost`, of `0.0` — OpenRouter's own number, not a wrapper that
  stopped working. No `:free` id is registered today.
  `Tracer.observe_message` opens no span of its own, it only names and attributes
  (`trace_name="handle_message"`, tagged with the content type, plus `prompt_key`,
  `prompt_version`, `target_language` and `thinking_level` as metadata) whatever spans
  the message's model calls open. Those are metadata because nothing else carries
  them: pydantic-ai exports only the six numeric OTel model settings, so the
  string-valued thinking level never reaches a span, and the rest
  would have to be parsed back out of the prompt wording. They exist to make a
  trace filterable and replayable as an evaluation dataset item; the model id needs no
  entry, being already on the generation span. `prompt_version`
  (`prompts.prompt_version`) is a short hash over `SYSTEM_INSTRUCTION` **and** the
  strategy's own template, so the key names the strategy while the version pins the
  wording a run actually used — editing either template moves it. For the same reason
  `summarize_text` passes the prompt and the content as two parts instead of one
  concatenated string — a multi-part text prompt is still text-only, so it stays
  instrumented. Blank or whitespace-only text is the exception: it sends the prompt
  part alone, so a trace consumer must not assume a content part is present. That case
  is reachable — `AudioTranscriber.transcribe` returns `""` for audio WhisperX finds no
  segments in, such as silence or music — and an empty text part is not worth sending.
  Consequences worth knowing: the Gemini-file call is never
  traced, but a media message still is when it falls through to Replicate
  transcription, which summarizes a plain string; a trace spans the model call only,
  not the download, parse or upload around it; and a retried `summarize_text` produces
  one trace per attempt, since nothing groups them. `langfuse_client.shutdown()` flushes on exit. Independent of
  Sentry, which handles error capture and logs.
- **The project is on the Langfuse v4 data model.** Langfuse Cloud becomes v4-only on
  **2026-11-16**, when the legacy APIs, features and ingestion below are removed. What that
  means here, so none of it is re-derived:
  - **Ingestion needs nothing.** v4 requires Python SDK ≥ 4.7.0; `langfuse==4.14.4` is pinned
    and ingestion already goes through OTel (`Agent.instrument_all()`), not `POST /ingestion`.
  - **Trace-level input/output is deprecated product-wide** — tables, judges and exports all
    read from an observation instead. Nothing here sets it: `Tracer.observe_message` only
    calls `propagate_attributes`, which is the v4-correct way to copy trace attributes onto
    observations so they stay filterable, and the model call's own span already carries the
    input and output. **Never add `set_current_trace_io()` or an equivalent** to keep a legacy
    evaluator working; migrate the evaluator to the root observation instead.
  - **Evaluation targets `experiment`, which is already a v4 target.** The legacy targets are
    `trace` and `dataset`, and the project has none — `tier1-on-experiments` is the only rule.
  - **No blob-storage, PostHog or Mixpanel export is configured**, so the enriched-observation
    export migration does not apply. Only blob storage is visible on the public API; the other
    two are UI-only under *Project Settings → Integrations*.
- **Langfuse-managed prompts are a hand-maintained mirror, for experiments only.** Two chat
  prompts named exactly after the `prompt_key`s (`basic_prompt_for_transcript`,
  `key_points_for_transcript`) hold a copy of what `src/prompts.py` sends, so a Langfuse
  Prompt Experiment can run a strategy over a dataset against any model. `src/prompts.py`
  stays the source of truth and the bot never calls `get_prompt` — that keeps prompts in the
  repo, puts no network fetch on the request path, and leaves `prompts.prompt_version` as the
  pin a trace carries. Edits are made in the UI when a template changes; they are rare enough
  that a sync script was **rejected** as machinery for a once-a-quarter edit.
  Four things about the shape are load-bearing, and none of them announce themselves when
  broken — the experiment just renders every dataset item identically:
  - `type` is `chat` and is **immutable after creation**. A prompt created as `text` can never
    become one; it has to be deleted and recreated, losing its version history.
  - The system message is `SYSTEM_INSTRUCTION` with `{language}` rewritten to
    `{{target_language}}`. Langfuse substitutes double braces only, so a single-brace
    placeholder is copied through as literal text rather than failing loudly.
  - Two separate `user` messages — the strategy template, then `{{content}}` alone — because
    `summarize_text` sends the prompt and the content as two parts. Concatenating them into
    one message measures a call the bot never makes.
  - Variable names must equal the dataset item's input keys (`content`, `target_language`;
    `prompt_key` selects the prompt rather than filling a variable). Langfuse resolves a
    variable only against a key of the same name, so renaming either side breaks every run.

  Do **not** re-add a `Language` prompt referenced by composition, as an earlier hand-built
  version did. It freezes into the prompt what the dataset needs as a per-item variable, so a
  run cannot mix target languages, and Langfuse then refuses to delete it while any dependent
  version survives. Storing `prompt_version(prompt_key)` in the prompt's `config` is what ties
  a Langfuse version back to the repo revision it was copied from; nothing else records it.
- **Evaluation datasets are built from traces, and the content type is not one of the fields.**
  Two Langfuse datasets hold screened trace content: `summarization-screen-v1` (25 items) is a
  strict subset of `summarization-compare-v1` (50), so the per-item key-facts checklist that
  serves as `expected_output` is written once rather than twice. Item `input` is
  `{content, target_language}` and nothing else — those are the two prompt variables, and an
  `inputSchema` on both datasets rejects an item missing either. `prompt_key` rides in
  `metadata`, not `input`: an experiment picks one prompt and runs it over every item, so the
  originating trace's strategy fills no variable and would sit in `input` as a dead key.
  The trap when harvesting: a trace's tag is the **Telegram** `content_type`, which is `text`
  for a URL as much as for a pasted paragraph. A YouTube transcript, a web article and a
  Replicate-rescued audio transcript are therefore all tagged `text`, and no field
  distinguishes them — the stratum has to be inferred from the content, by **two** tests, not
  one. A YouTube transcript arrives in subtitle format, hard-wrapped to ~34-character lines.
  The other two are both single blobs, so line width cannot separate them; what does is that
  `parsing.py` returns markup (Exa HTML, Tavily markdown) while WhisperX returns its segments
  joined into plain prose with a leading space. Testing only for wrapping silently files every
  audio transcript under `web_article`, which is a stratum label that looks plausible in the
  UI and is wrong.
  The strata are not balanced and that is **accepted**, not an oversight to fix: nine days of
  real traffic yielded only 5 `web_article` items in total (2 of the 25 screening items),
  under the ≥8–10 per cell the plan asks for, and no amount of further harvesting changes it.
  The consequence to keep stating is narrow — a *web-article-specific* claim is anecdote until
  the stratum is seeded — while `yt_transcript` and `audio_transcript` carry enough items to
  rank models. Do not re-raise this as a blocker.
  Two screening filters earn their keep on real traffic: content under ~1500 characters, and
  degenerate output from `AudioTranscriber.transcribe` when WhisperX mis-decodes audio — a
  distinct failure from the documented empty-transcript case, and one that reaches the model
  as content rather than being dropped. Detect it by **compression ratio**, not by any single
  character's share: the observed failures repeat a multi-character sequence, so one of the two
  sat at 27% on its most common character and slipped a 30% threshold, while both compress to
  ~0.03 of their size against ~0.14 for the densest real item.
- **Tier 1 scoring is binary sub-checks, never weighted points.** Every rule in `prompts.py` is
  stated as an absolute — "Respond in {language}" has no 60%-credit reading — so a weighted
  composite would invent numbers and hide *which* rule broke, which is the only thing the
  screening stage needs to know. The Langfuse code evaluator `tier1-deterministic` emits
  `t1_language_match`, `t1_no_preamble`, `t1_no_artifacts`, `t1_bullet_count`,
  `t1_bullet_purity` (all BOOLEAN), `t1_compression` (NUMERIC) and the derived `t1_pass`, which
  ANDs the applicable binary checks. Screening drops a model scoring `t1_pass` on under 70% of
  items. Four judgements inside it are deliberate:
  - The language check passes at **70%** Cyrillic among letter characters, not 95%. A correct
    Russian summary carries Latin proper nouns (`ChatGPT`, `macOS`, `Codex`), and a stricter
    floor fails good output while adding nothing against a model that answered in English.
  - `t1_compression` is a **diagnostic with no threshold**. Judges reward length, so the length
    column belongs beside every quality score; gating on it would let a model win by truncating.
  - The two bullet checks are emitted **only** for `key_points_for_transcript`, which is the
    only strategy that asks for bullets. Scoring `basic_prompt_for_transcript` zero there would
    penalise it for obeying its own prompt. The consequence is that `t1_pass` ANDs three checks
    for one strategy and five for the other, so it ranks models **within** a strategy and must
    never be used to compare the two strategies — that is Tier 3's job.
  - Bullet count and bullet purity stay separate scores because "produced 3 bullets" and
    "produced 5 bullets plus a closing paragraph" are different failures with different fixes.

  **Stage 1 is run and eliminated nobody.** All six registered models over the 25 screening
  items on `key_points_for_transcript` score `t1_pass` far above the 70% floor:
  `gemini-3.7-flash` and `openai/gpt-5.6-luna` 100%, `meta/muse-spark-1.2` and
  `thinkingmachines/inkling` 96%, `minimax/minimax-m3` and `stepfun/step-3.7-flash` 84%.
  Read that as *the deterministic checks do not separate this pool*, not as six equally good
  models — Tier 1 only asks whether a model obeyed the prompt's absolutes. The discrimination
  has to come from Tier 2/3, so do not spend another sweep tuning Tier 1 thresholds.
  Two things the failures actually are: `stepfun/step-3.7-flash` returned an **empty response
  on 3 of 25 items** and `thinkingmachines/inkling` on 1, which Tier 1 books as a language
  failure (an empty string has no Cyrillic) — correct, and worth reading as a reliability
  signal rather than a quality one. `minimax/minimax-m3` returned no empties but answered in
  the **wrong language twice**, which is the failure mode Tier 1 exists to catch.
  `t1_compression` spans 0.125 (`gemini-3.7-flash`, tersest) to 0.228
  (`meta/muse-spark-1.2`), a near-2x spread that must stay beside every Tier 2/3 score
  because judges reward length.
  The registry is **6 models**; the 9-model table in the STG-138 description is stale and
  must not be used to size a sweep.

- **A code evaluator receives every metadata value as a string, and a crash inside it is
  silent.** `ctx.observation.metadata` is a flattened merge of OTel resource attributes, the
  dataset item's metadata and the run's own metadata, and *every* value in it — item metadata
  included — arrives stringified: `char_length` is `"19845"`, not `19845`, even though the
  dataset item stores a JSON number and the dataset-items API returns one. Arithmetic on such
  a value raises `TypeError`, which discards the whole `EvaluationResult` — including the
  scores already built before the failing line. Nothing surfaces this: the rule still reports
  `status: "active"`, the run completes, and the only symptom is that no score appears. This
  cost a full session to find, so **coerce every metadata value before using it as a number**.
  The one place the failure is visible is `POST /unstable/evaluators`, whose preflight executes
  the source against sample data and returns `422 evaluator_preflight_failed` with the
  exception and line number — which makes reinstalling the evaluator the cheapest way to test
  it, and means a rule that went active earlier is **not** evidence the code still runs, since
  preflight only sees whatever sample it was given.
  **`tier1-deterministic` stays one evaluator emitting all seven scores** — splitting it into
  one evaluator per score was considered and **deferred**, not overlooked. The argument for
  splitting is real (the `char_length` crash destroyed five already-computed scores along with
  the one that failed), but the price is higher than it looks:
  - `t1_pass` cannot survive the split. An evaluator's context is its own observation and
    experiment item; it cannot read scores other evaluators wrote. A standalone `t1_pass`
    would have to recompute all five checks internally — restoring the same monolith and the
    same single point of failure, just for the aggregate — or stop being a stored score and
    become a report-time calculation.
  - Each evaluator is a self-contained source blob with no imports between them, so `_text`,
    `_lines`, `_is_bullet`, `_cyrillic_ratio` and `_number` would be copied seven times. One
    fix becomes seven edits and seven reinstalls, and divergence between the copies is silent.
  - Splitting only helps when one check's *input* breaks, which is the `char_length` case. A
    change to the `ctx` shape itself breaks all seven identically either way.

  The cheaper equivalent, if this is revisited: keep one evaluator and wrap each check in
  `try/except`. Whatever is done, `t1_pass` must **not** silently become the conjunction of
  whichever checks survived — a partial failure has to suppress it or label it, or the score
  quietly changes meaning.
  What makes deferring safe is that **re-scoring Tier 1 costs no tokens**. The summaries are
  already trace outputs, so a broken scorer is repaired by recomputing over existing traces —
  either through Langfuse's backfill (Traces table → `Actions` → `Evaluate`, requires the v4
  preview toggle; documented for observation-level, **unverified** for a code evaluator on an
  experiment target) or by running the same source locally and posting scores through the API.
  Only Tier 2/3 spend money on a re-score, and those already live outside Langfuse.

  Two consequences for scoring runs:
  - Branch on `run_prompt_key` from the run metadata, not the item's `prompt_key`. An
    experiment applies one strategy to every item, while an item's `prompt_key` records the
    strategy of the trace it was *harvested* from; on a mixed dataset the two disagree and the
    bullet checks silently apply to the wrong items. `summarization-screen-v1` has 24 items
    from `key_points_for_transcript` and 1 from `basic_prompt_for_transcript`, so this is live,
    not hypothetical. The evaluator prefers `run_prompt_key` and falls back to the item.
  - Re-POSTing an evaluator under the same name creates a new **version** and every rule
    bound to that name follows it automatically — the rule's stored evaluator `id` changes to
    the new version's id. There is no separate update route, and no need to touch the rule.
- **Read experiment results through the v4 experiment endpoints, never the trace join.**
  Evaluator scores attach to the **observation**, so `GET /v3/scores?experimentId=…` returns
  nothing for them and reads exactly like the evaluator never fired. The answer is not to join
  through traces: `fields=scores` on `GET /experiment-items` returns each item's scores
  inline, and `fields=io` returns its input, output and expected output. One call per page
  replaces a dataset-run fetch plus one trace fetch per item plus a separate score sweep.
  `scripts/eval/langfuse_api.py` is the only place that talks to these endpoints.
  The v3 shapes this replaced are **deprecated and stop being served on 2026-11-16**:
  `GET /datasets/{name}/runs/{runName}` → `GET /experiments` then `GET /experiment-items`;
  `GET /traces/{id}` → `fields=io` on the item; `GET /observations` → `GET /v2/observations`.
  Experiments are queried by dataset **id**, not name, so resolve it through
  `GET /v2/datasets/{name}` first, and `fromStartTime` is **required** on both experiment
  endpoints. Under v2, `input`/`output` come back as **raw strings** rather than parsed JSON,
  and a field group that was not requested is **absent** rather than null.
  Two traps survive the migration. The public API allows **30 requests per window** and
  answers a 429 with `details.retryAfterSeconds`, which must be obeyed — blind exponential
  backoff does not converge, because every retry spends another request; an unchecked 429
  falls through `.json().get("data", [])` as an empty list and is indistinguishable from a
  model that scored nothing, which produced a *different table on each run* until it was
  fixed. And pagination is `meta.cursor` — **not** `meta.nextCursor`, which does not exist and
  silently truncates a sweep at the first page.
  For a quick project-wide check that a rule is producing anything at all, `GET /v3/scores`
  with `source=EVAL` and no other filter still works; `metadata.job_configuration_id` names
  the rule that wrote each score.

- **Tier 2 and Tier 3 judges run outside Langfuse, and have to.** Three independent
  constraints rule out Langfuse's managed LLM-as-a-judge for this project, so the judge is a
  local runner that posts scores back through the API into the same score table as the
  `t1_*` scores and any human annotations — which is what keeps the calibration comparison a
  query rather than a spreadsheet.
  - **OpenRouter silently drops `response_format: json_schema` on Anthropic models.** The
    model answers in prose and nothing errors; `provider: {require_parameters: true}` does not
    change it, and OpenRouter's own catalog advertises `structured_outputs: true` for these
    ids, so the metadata is wrong rather than merely absent. A **forced tool call**
    (`tools` + `tool_choice` naming the function) is honoured on the same route and returns
    clean structured JSON. Langfuse's managed judge sends `response_format` with no way to
    override it, so it fails preflight with "No object generated: could not parse the
    response" against any Anthropic model. The same schema works through the same connection
    on Gemini, so this is the Anthropic route specifically.
  - **OpenRouter's half-price `:batch` model ids reject chat/completions** with "This model is
    only available through the Batch API", pointing at `/api/beta/batches`. Langfuse's judge
    is synchronous, so it can never reach them at all.
    The batch path is **abandoned** — it was built, submission worked (a batch id and
    `status: validating` came back, pinning snapshot `claude-sonnet-5-20260630`), but the
    poll→results cycle never delivered, and half price is not worth a second unproven
    transport for a job costing tens of dollars. **The judge is synchronous
    `anthropic/claude-sonnet-5`.** Do not rebuild `:batch` without a reason beyond price.
  - **An evaluator sees one item.** Its context is that item's `input`, `output`,
    `expected_output` and metadata; there is no mapping source for a second run's output. So
    pairwise comparison cannot be an evaluator of either kind, whatever the judge model.

  The judge model is **`anthropic/claude-sonnet-5`**, settled. Anthropic is the only frontier
  family not in the candidate pool, so it is the one judge whose self-preference bias cannot
  favour a candidate, and Sonnet 5 still outranks a pool that is mostly flash tier. It is
  pinned by model id, `reasoning_effort` and judge-prompt hash — **not** by temperature, which
  Sonnet 5 and Opus 5 reject outright with a 400. §6 calibration against hand labels may still
  revise the choice; nothing else should.

  Three details of the judge itself are load-bearing. The judge **counts** (claims, entailed
  facts) and the runner computes the ratio, because a model asked directly for `0.71` makes
  arithmetic slips no prompt wording fixes. Each schema declares its **verdict field before
  `reasoning`**, since models emit in declared order and it is the long reasoning string that
  runs into `max_tokens` — a truncated call then still carries the answer. And OpenRouter does
  not enforce `required` on this route, so a missing field has to be caught explicitly rather
  than trusted. Pairwise runs **both orders and discards disagreements**; the discard rate is
  itself a judge-quality signal.

  Installing a code evaluator through the unstable API has a shape trap worth keeping: on
  `POST /unstable/evaluators` the `prompt` and `outputDefinition` fields are llm-as-judge-only
  and are rejected outright for `type=code`, while on `POST /unstable/evaluation-rules` the
  evaluator reference needs `type: "code"` and `mapping` must be **omitted entirely** — an
  empty array is rejected just as a populated one is, and leaving `type` off makes the request
  validate as llm-as-judge and demand a mapping. The evaluator reference also needs `name` and
  `scope` alongside `id` and `type`; sending only the id fails validation. The server fills the
  omitted `mapping` in with defaults, so a rule read back after creation shows six entries —
  that is expected, not drift. A rule returning `status: "active"` means its preflight ran the
  code **once, against sample data**; it does not mean the code survives real data, so treat
  `422` from a later `POST /unstable/evaluators` as the authoritative crash report.

  Four API shapes cost real time to rediscover:
  - The batch endpoint parses the request body as a **stream**, so `endpoint` and `model` must
    be serialised before `requests`; a plain dict literal in that order is what guarantees it.
  - Tier 2 evaluators attach through `Langfuse.run_experiment(evaluators=[…])` rather than by
    posting scores by hand — the run wires each `Evaluation` to the right item.
  - A Langfuse score **requires a target**. Passing `trace_id=None` fails with a bare
    `Bad request` while the calling code still prints success, so a pairwise score has to be
    anchored to something — run A's trace for that item is the natural choice.
  - Dataset run names embed the model id, so they contain `/` and spaces and must be
    URL-encoded into REST paths or the segments split and the request 404s.
