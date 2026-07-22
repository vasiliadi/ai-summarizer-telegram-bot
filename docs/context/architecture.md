# Architecture

High-level component map and data flow for orientation at session start.
**Stable** — update only when the architecture actually changes (a new component,
a new flow, a routing/fallback rewrite), not every handoff.

This file is deliberately **not** a source mirror. It does not list functions
line-by-line, dependencies, or env vars — read the source for that.

- Stack list → `pyproject.toml` + `README.md`
- *Why* the core infra was chosen (sync polling, Valkey, Gemini+Replicate,
  Postgres+Valkey split, Modal cron) → `docs/summaries/decision-10-architecture-rationale.md`
- Per-feature decisions → `docs/summaries/decision-*.md`
- External-service gotchas → `docs/summaries/decision-*.md` and source comments

---

## What it is

A private Telegram bot that summarizes content — webpages, YouTube/Castro
links, audio, voice, video, video notes, and documents — with Gemini, and
replies with the summary in the user's chosen language. Synchronous,
polling-based (`bot.infinity_polling`); no webhooks, no async framework.

## Component map (`src/`)

| Module | Role |
|--------|------|
| `main.py` | Telegram entry point. Command handlers + the unified `handle_message`; routes by `content_type`; top-level error → user-message mapping. |
| `handlers.py` | Per-content-type handlers. Media validation, builds `SummaryKwargs` from the user record, picks the summarize path. |
| `summary.py` | `Summarizer` — the core summarization orchestrator. Owns the input-type branching and the Gemini calls. |
| `transcription.py` | `AudioTranscriber` (Replicate WhisperX) + `YouTubeTranscriber` (orchestrator over `ApiBackend` primary → `YtDlpBackend` fallback, mirroring `parsing.py`'s `ParserBackend`). |
| `download.py` | `Downloader` — YouTube audio (yt-dlp→mp3), Castro (scrape→mp3), Telegram file fetch. |
| `parsing.py` | `WebParser` — webpage text extraction, Exa primary → Tavily fallback. |
| `services.py` | `Messenger` (Telegram send with retry + 4096-unit chunking), `QuotaManager` (rate limits), `GeminiHelper` (config, MIME, file upload/poll). |
| `database.py` | `UserRepository` — users table access (SQLAlchemy + Postgres). |
| `models.py` | `UsersOrm` — the single `users` table (id, approval, per-user settings, `daily_limit`). |
| `exceptions.py` | Domain exceptions: `LimitExceededError`, `WebParseError`, `TranscriptDownloadError`, `FetchTranscriptError`. |
| `config.py` | All clients/singletons + labels, defaults, limits, constants. Side-effectful import (Sentry, logging, env). |
| `prompts.py` | `PROMPTS` (strategy templates) + `SYSTEM_INSTRUCTION`. |
| `domain.py` | `PrefixedText` + `format_prefixed_summary` — source-provenance prefixing. |
| `utils.py` | Proxy pick, temp-name gen, `compress_audio` (ffmpeg Opus 16k mono), `clean_up`. |
| `scripts/cron.py` | Modal serverless cron — clears the bot's per-user daily request-limit counters (`RPD`) in Valkey at midnight PT, so daily budgets reset in step with Gemini's free-tier quota. |
| `scripts/db.py` | Standalone bootstrap script — creates the `users` table via its own `Base`/engine (separate from `src/models.py`); runs `create_all` at import. |

## Request flow

```
Telegram update
  └─ main.handle_message
       ├─ select_user (Postgres) ─ reject if not approved
       └─ process_message_content  ── routes by content_type ──┐
                                                               │
  handlers.py:                                                 ▼
    audio / voice ───────────────► summarize(File)
    video / video_note ──────────► download_tg(.mp4) → compress_audio(.ogg) → summarize(path)
    document ────────────────────► summarize_with_document(File, mime)
    text (treated as URL) ── _classify_url ──┬─ "media" (YT/Castro) ► summarize(url)
                                             └─ "web"  ► parse_url → summarize_text
```

### Summarizer input branching (`summary.py:summarize`)

- **YouTube URL** → try transcript (`get_yt_transcript`); on success summarize
  the transcript. On failure → `download_yt` audio, then the file path below.
- **Castro URL** → `download_castro` audio → file path.
- **Telegram File** → `download_tg(.ogg)` → file path.
- **File path** → `summarize_with_file` (upload to Gemini, generate). If that
  exhausts retries → fallback: `compress_audio` → `transcribe` (Replicate) →
  `summarize_text`.

So there are two layered fallbacks for spoken content: transcript-first for
YouTube, and Gemini-file-first with a Replicate-transcription rescue for any
audio that Gemini can't process.

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

- **OOP + singleton + alias.** Each service module defines a (mostly stateless)
  class, instantiates one module-level singleton, then exports module-level
  aliases to its methods so the original functional public API (`module.func`)
  still works — importers and `mocker.patch("module.func")` calls depend on
  those aliases today. OOP is the intended direction: a proposal to *unwind* it
  — remove the classes and revert to plain module-level functions — was reviewed
  and rejected, so don't go back that way. A future refactor toward stricter OOP
  is welcome; note the alias layer is a backward-compatibility shim, not an OOP
  goal, so such a refactor may drop it, but must migrate importers and the
  `mocker.patch("module.func")` test calls in the same change.
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
  the OpenInference `GoogleGenAIInstrumentor` auto-captures every Gemini
  `generate_content` call, and `services.observe_message` (used in
  `main.handle_message`) wraps each Telegram message in one root span attributed to
  the user and tagged with the content type, so all Gemini calls for a message nest
  under a single trace. `langfuse_client.shutdown()` flushes on exit. Independent
  of Sentry, which handles error capture and logs; the Langfuse tracing is a
  no-op when disabled.
