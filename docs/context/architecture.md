# Architecture

High-level component map and data flow for orientation at session start. **Stable** —
update only on a real architectural change (new component, new flow, routing/fallback
rewrite) or a durable external-service gotcha (→ Cross-cutting patterns), not every
handoff. Not a source mirror: read the source for function
signatures, dependencies, and env vars.

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
- **Gemini primary, Replicate fallback** — Replicate (WhisperX) is a transcription path,
  never a swappable summarization model. It is taken when Gemini file processing exhausts
  its retries, and as the standing route for audio whenever the selected model is
  text-only (every OpenRouter model is).
- **`pyproject.toml` and `uv.lock` ship in the final image** — the `Dockerfile`'s final
  stage copies them and deliberately does not `rm -f` them afterward, as an earlier
  version did (`4dff64b`, PR #575). A same-stage `rm -f` only writes a whiteout: the
  bytes stay in the layer and are recoverable from the raw image, so it never protected
  against that threat model. A running container already discloses the same dependency
  versions through `.venv/lib/python*/site-packages/*/dist-info/METADATA`, which must
  exist for the venv to work. Do not re-flag this as a security gap; genuinely excluding
  a file needs a multi-stage build that never copies it into the final stage.
- **pydantic-ai as the provider seam** — every model call goes through `llm.py`, so the
  registry (`config.MODEL_SPECS`) is what decides which provider serves a model id.
  Adding a model from a registered provider is a registry row; adding a provider is a
  branch in `build_model` plus a dependency extra, not a rewrite of `summary.py`. Google
  and OpenRouter are registered. The `else` in `build_model` still raises for a provider
  with no builder, and is covered by a test that fabricates a spec.
  The Gemini Files API is still called directly (`services.GeminiHelper`), because
  base64-inlining a 20 MB Telegram file inflates it past the inline-request limit.
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
  Valkey, in step with Gemini's quota window, without running a second container.
  Also stated in `README.md`; keep the two in step.

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
| `scripts/cron.py` | Modal serverless cron — clears the bot's per-user daily request-limit counters (`RPD`) in Valkey at midnight PT, so daily budgets reset in step with Gemini's free-tier quota. |
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
  user data lives in Postgres. Gemini bills failed calls, so quota is counted
  per attempt by design — not a double-charge bug.
- **Retries.** Network/model calls use `tenacity` `@retry`; persistent failure
  surfaces as `RetryError`, which `handle_message` maps to a user-facing
  "try again later" message. Other mapped errors: `LimitExceededError`,
  `WebParseError`. All exceptions are sent to Sentry via `capture_exception`.
- **Gemini Files API constraints.** `safety_settings` is **rejected** on the Interactions
  surface — the live API answers `400 Unknown parameter 'safety_settings'` to the
  top-level kwarg, `generation_config`, and the `extra_body` escape hatch alike (Sentry
  issue 7500680560). The bot relies on default model safety behavior; an SDK release
  exposing the kwarg is not by itself evidence the API accepts it, so re-adding it needs
  a live smoke test first. *Confirmed on `google-genai==2.3.0`; `pyproject.toml` now pins
  `==2.16.0`, so that check is owed before the constraint is either trusted or dropped.*
  Uploads orphaned by a post-upload failure (polling error, FAILED state, uri/mime guard)
  get **no** `files.delete` cleanup: Gemini expires them on its own, both callers retry at
  most twice, and the `name is None` path has no handle to delete with. Reviewers re-raise
  this as a resource leak — the tell is the claim that the files are orphaned
  *indefinitely*, which is what inflates the severity. Rejected on PR #925, re-affirmed
  on #1022.
- **Temp-file hygiene.** Downloads/compression write UUID-named temp files in the
  CWD; `clean_up` removes them, guarded by a `PROTECTED_FILES` snapshot taken at
  startup. On shutdown `clean_up(all_downloads=True)` sweeps the rest.
- **Fragmented downloads.** `download_yt` (`src/download.py`) keeps yt-dlp's default
  `skip_unavailable_fragments=True`. Making a missing fragment fatal would turn many
  usable downloads into hard failures; the occasional truncated file that crashes the
  ffmpeg fixup (`Invalid argument`, STG-128) is an accepted edge case, since PR #889
  (`672ebc0`) already clears the leftover partials and a proxy connection dropping
  mid-download is genuinely retryable. Setting it to `False` was proposed and declined.
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
  to compare models on.
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
