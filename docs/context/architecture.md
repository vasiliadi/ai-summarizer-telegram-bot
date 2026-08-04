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
- **Gemini primary, Replicate fallback** — Replicate (WhisperX) is the transcription
  rescue path taken when Gemini file processing exhausts its retries, not a swappable
  summarization model.
- **pydantic-ai as the provider seam** — every model call goes through `llm.py`, so the
  registry (`config.MODEL_SPECS`) is what decides which provider serves a model id.
  Only Gemini models are registered today; the seam exists so adding one from another
  provider is a registry row plus a dependency extra, not a rewrite of `summary.py`.
  The Gemini Files API is still called directly (`services.GeminiHelper`), because
  base64-inlining a 20 MB Telegram file inflates it past the inline-request limit.
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
| `llm.py` | `LLMClient` — the provider seam. Each instance holds one pydantic-ai `Agent`; model, instructions and settings are resolved per run. Provider dispatch lives in `build_model` (keyed on `config.MODEL_SPECS[...].provider`); `build_settings` currently carries only the provider-agnostic thinking level. |
| `transcription.py` | `AudioTranscriber` (Replicate WhisperX) + `YouTubeTranscriber` (orchestrator over `ApiBackend` primary → `YtDlpBackend` fallback, mirroring `parsing.py`'s `ParserBackend`). |
| `download.py` | `Downloader` — YouTube audio (yt-dlp→mp3), Castro (scrape→mp3), Telegram file fetch. |
| `parsing.py` | `WebParser` — webpage text extraction, Exa primary → Tavily fallback. |
| `services.py` | `Messenger` (Telegram send with retry + 4096-unit chunking), `QuotaManager` (rate limits), `GeminiHelper` (MIME, file upload/poll), `Tracer` (Langfuse root span per message). |
| `container.py` | `Container` + `build_container()` — the composition root; wires every collaborator, including the `bot` client, to `config`'s clients. |
| `database.py` | `UserRepository` — users table access (SQLAlchemy + Postgres). |
| `models.py` | `UsersOrm` — the single `users` table (id, approval, per-user settings, `daily_limit`). |
| `exceptions.py` | Domain exceptions: `LimitExceededError`, `WebParseError`, `TranscriptDownloadError`, `FetchTranscriptError`. |
| `config.py` | All clients/singletons + the `MODEL_SPECS` registry, labels, defaults, limits, constants. Side-effectful import (Sentry, logging, env). |
| `prompts.py` | `PROMPTS` (strategy templates) + `SYSTEM_INSTRUCTION`. |
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

`ModelSpec.supports_audio` gates the native file-upload path: a model that
cannot read audio takes the Replicate transcription route instead, in
`summarize` and — because `SUPPORTED_DOCUMENT_MIME_TYPES` accepts `audio/ogg` —
in `summarize_with_document`. Every registered model is currently audio-capable,
so the branch is dormant in production and covered by tests with a synthetic
spec. It exists so a text-only model is a registry row, not a code change.

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

- **Constructor injection migration (STG-135, in progress).** Service classes
  move from module-level singletons to collaborators injected once by
  `container.py`. Migrated: `Messenger`, `QuotaManager`, `GeminiHelper`,
  `Tracer` (`services.py`); `UserRepository` (`database.py`); `LLMClient`
  (`llm.py`); `Downloader` (`download.py`); `WebParser` (`parsing.py`);
  `AudioTranscriber`/`YouTubeTranscriber` (`transcription.py`); `Summarizer`
  (`summary.py`); `MessageHandlers` (`handlers.py`); `BotApp` (`main.py`).
  Only deleting the now-unused transitional shims remains. Unwinding to plain
  functions is **rejected**.
- **Quota model.** `check_quota(..., quantity=0)` is a pre-check that raises when
  the daily budget is exhausted but consumes nothing; `quantity=1` consumes one
  unit. A global per-minute limit throttles by sleeping. Counters live in Valkey;
  user data lives in Postgres. Gemini bills failed calls, so quota is counted
  per attempt by design — not a double-charge bug.
- **Retries.** Network/model calls use `tenacity` `@retry`; persistent failure
  surfaces as `RetryError`, which `handle_message` maps to a user-facing
  "try again later" message. Other mapped errors: `LimitExceededError`,
  `WebParseError`. All exceptions are sent to Sentry via `capture_exception`.
- **Temp-file hygiene.** Downloads/compression write UUID-named temp files in the
  CWD; `clean_up` removes them, guarded by a `PROTECTED_FILES` snapshot taken at
  startup. On shutdown `clean_up(all_downloads=True)` sweeps the rest.
- **Settings commands** use a one-time reply keyboard + `register_next_step_handler`
  (`_prompt_choice` → `proceed_*`) and validate against the allow-lists in `config.py`.
- **Tracing (optional).** Langfuse tracing is enabled only when `LANGFUSE_PUBLIC_KEY`
  and `LANGFUSE_SECRET_KEY` are set (`config.langfuse_client`, else `None`). When on,
  `Agent.instrument_all()` makes pydantic-ai emit an OpenTelemetry span per model
  call, which the OTel-based Langfuse SDK ingests — no provider-specific
  instrumentor. `Tracer.observe_message` (used in `BotApp.handle_message`) wraps
  each Telegram message in one root span attributed to the user and tagged with the
  content type, so all model calls for a message nest under a single trace.
  `langfuse_client.shutdown()` flushes on exit. Independent of Sentry, which handles
  error capture and logs; the Langfuse tracing is a no-op when disabled.
