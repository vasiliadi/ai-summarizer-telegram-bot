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
- **One model provider: OpenRouter** — every summarizing model is an OpenRouter id, and the
  direct Google provider, `google-genai` and the Gemini Files API are gone. Accepted
  consequences: an OpenRouter outage stops all summarization, and Gemini's native audio and
  video understanding is lost. Replicate (WhisperX) is a transcription service, never a
  swappable summarization model.
- **The `openai` SDK, pointed at OpenRouter** — `config.openrouter_client` is one
  `openai.OpenAI` on `https://openrouter.ai/api/v1`, and every model call goes through
  `llm.py` on it. With a single provider there is no seam left for a framework to own, so
  pydantic-ai was dropped: it also refused OpenRouter file ids (`UploadedFile` rejects
  `provider_name='openrouter'`) and inline OGG audio. OpenRouter's own Python SDK was
  **rejected** (checked 2026-10-01): it caps `pydantic` below 2.13, which downgrades this
  project's; it is auto-generated with several releases a day; and it has no Langfuse
  integration, so spans, usage and cost would be written by hand. Revisit only if the cap is
  lifted and a Langfuse integration exists. The SDK retries on its own — twice by default, on
  connection errors and 408/409/429/5xx — inside one `@retry` attempt, so those repeats
  consume no extra quota unit.
- **Dropping or renaming a model id needs an Alembic data migration in the same PR** — the
  migration rewrites rows whose stored `summarizing_model` left the registry onto a surviving
  id, so `/myinfo` and the user's real model agree. It cannot be the only guard: the
  `Dockerfile` runs `alembic upgrade head` at image build, while the previous container is
  still serving and still writes its own default into every new row, so a user registered in
  that window (or after a rollback) keeps the dropped id. `MessageHandlers._settings` therefore
  substitutes `DEFAULT_MODEL_ID_FOR_SUMMARY` for an id outside `MODEL_SPECS`, logged at
  WARNING; the stored row is left alone, and `/myinfo` shows its raw id. The migration's
  rewrite alone changes no schema, so `uv-guide.md`'s schema-change rule is not what requires
  it. *Adding* an id needs no
  migration. Moving `DEFAULT_MODEL_ID_FOR_SUMMARY` also moves `models.UsersOrm`'s
  `server_default` (pinned by `test_orm_server_defaults_match_config`) and the column's own
  default.
- **Documents go to the model by `file_id`; audio never does** — a document is uploaded to
  OpenRouter's Files API and referenced as `{"type": "file", "file": {"file_id": "or_file_…"}}`.
  Observed 2026-09-29 – 2026-10-02:
  - The API is **beta** ("the API and behavior may change"): 100 MiB per upload, 10 GiB per
    workspace, no charge, and **files never expire**. A model request caps a referenced file at
    20 MB (seen on audio; ASSUMED the same for documents), which equals `TG_MAX_FILE_SIZE`.
  - It answers on the **global endpoint only**; `eu.`/`us.openrouter.ai` return 403, so
    `OPENROUTER_BASE_URL` must stay global (pinned by a test).
  - The `openai` SDK's own `files.create(purpose="user_data")` and `files.delete` work against
    it: OpenRouter replies in OpenAI's shape, and an upload is `processed` at once, so there is
    no state to poll.
  - `openai/gpt-6-luna` and `x-ai/grok-4.7` read PDF, TXT, CSV and RTF by `file_id`; the
    extension-less temp names `download_tg` produces were enough for `gpt-6-luna` on all four
    and for Grok on a PDF. RTF is stored as `text/plain`, so the model sees raw RTF markup
    (quality on large files untested). Grok adds 1 300–2 300 prompt tokens to any request with
    a file, against 63–208 for `gpt-6-luna`.
  - **Audio by `file_id` is refused by OpenRouter itself** (`400 Unsupported file type
    audio/…` for WAV, MP3 and OGG), even on an audio-capable model. Native audio does work
    inline (`input_audio`, base64, `format: "ogg"`), and is **deliberately unused**: spoken
    content is always transcribed. Offering it needs an inline delivery path, a request-size
    cap and a transcription fallback for long recordings; `ModelSpec.supports_audio` is kept
    for that day (see *Modality routing*).
  - A model without the `file` modality still answers from a PDF, because OpenRouter parses
    it — at what looked like about $0.002 a page on `deepseek/deepseek-v4.1-flash` (inferred
    from one request's cost, tariff not checked). That is why such a model is registered
    `supports_files=False` and routed to the failover model instead (see *Modality routing*).
- **OpenRouter calls identify the app** — `config.openrouter_client` sends
  `config.OPENROUTER_APP_URL`/`OPENROUTER_APP_TITLE` as the `HTTP-Referer`/`X-Title` default
  headers; without them all spend lands under "Unknown" in OpenRouter's app ranking.
  OpenRouter groups apps by the referer URL, so changing `OPENROUTER_APP_URL` starts a *new*
  Top Apps entry rather than renaming the old one. Hardcoded deliberately rather than read
  from the environment: the identity belongs to the repo, and an unset var in some deployment
  would silently revert attribution. The block-page detector and the eval judges call
  OpenRouter without the client and set the same headers by hand (`evals.md`).
- **Thinking levels are OpenRouter's `reasoning.effort`, sent untranslated** — the value stored
  in `users.thinking_level` goes out as `{"reasoning": {"effort": level}}`, and this codebase
  owns no per-model mapping; what a model does with a level is OpenRouter's and the model's
  business. The allow-list (`minimal|low|medium|high|xhigh`) is a subset of what OpenRouter
  accepts (`max|xhigh|high|medium|low|minimal|none`, observed 2026-10-01); all five returned
  200 on every registered model. A value outside OpenRouter's set is a 400, which is retried
  and ends in "try again later"; only a stale `users.thinking_level` can reach that, since
  `database.set_thinking_level` is the only writer.
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
| `handlers.py` | `MessageHandlers` — per-content-type handlers. Media validation, builds `SummarySettings` from the user record, picks the summarize path. |
| `summary.py` | `Summarizer` — the core summarization orchestrator. Owns the input-type branching, assembles the message content, and calls the injected `LLMClient.run`. |
| `llm.py` | `LLMClient` — the one place a model is called. `run` turns the instructions, the user's thinking level and the content parts into a single chat-completions request on the injected `openai` client; `build_file_part` references an uploaded document by id. A text run goes through `chat.completions.create`, a run carrying a file through the client's generic `post` (see Tracing below). It never consults `MODEL_SPECS`, so the eval harness runs unregistered ids on it as is. |
| `transcription.py` | `AudioTranscriber` (Replicate WhisperX, over plain HTTP) + `YouTubeTranscriber` (orchestrator over `ApiBackend` primary → `YtDlpBackend` fallback, mirroring `parsing.py`'s `ParserBackend`; an empty or whitespace-only transcript counts as a backend failure, so it falls through too). |
| `download.py` | `Downloader` — YouTube audio (yt-dlp→mp3), Castro (scrape→mp3), Telegram file fetch. |
| `parsing.py` | `WebParser` — webpage text extraction, Exa primary → Tavily fallback; each backend's output is block-page checked by JEV. |
| `services.py` | `Messenger` (Telegram send with retry + 4096-unit chunking), `QuotaManager` (rate limits), `OpenRouterFiles` (document upload/delete on OpenRouter's Files API), `Tracer` (names, tags and adds settings metadata to the Langfuse trace for a message, if one is opened). |
| `container.py` | `Container` + `build_container()` — the composition root; wires every collaborator to `config`'s clients. `Container` carries only the five roots `BotApp` holds (`bot`, `quota_manager`, `tracer`, `user_repo`, `handlers`); the rest of the graph is reached through `handlers`. |
| `database.py` | `UserRepository` — users table access (SQLAlchemy + Postgres). |
| `models.py` | `UsersOrm` — the single `users` table (id, approval, per-user settings, `daily_limit`). |
| `exceptions.py` | Domain exceptions: `LimitExceededError`, `WebParseError`, `TranscriptDownloadError`, `FetchTranscriptError`, `ReplicateError`, `TranscriptionError`. |
| `config.py` | All third-party clients (by design — see Cross-cutting patterns) + the `MODEL_SPECS` registry, labels, defaults, limits, constants. Side-effectful import (Sentry, logging, env). |
| `prompts.py` | `PROMPTS` (strategy templates) + `SYSTEM_INSTRUCTION` + `prompt_version` (short hash over both, for trace metadata). |
| `domain.py` | `PrefixedText` + `format_prefixed_summary` — source-provenance prefixing. `SummarySettings` — the per-request settings every `Summarizer` entry point takes. |
| `utils.py` | Proxy pick, temp-name gen, `classify_url` (shared URL routing), `compress_audio` (ffmpeg Opus 16k mono), `clean_up`. |
| `scripts/cron.py` | Modal serverless cron — clears the bot's per-user daily request-limit counters (`RPD`) in Valkey at midnight UTC, resetting every user's daily budget. |
| `scripts/db.py` | Standalone bootstrap script — creates the `users` table via its own `Base`/engine (separate from `src/models.py`); runs `create_all` at import. |
| `scripts/cloud_session_start.sh` | Claude Code SessionStart hook — in cloud sessions only, runs `uv sync --frozen` and installs pre-commit hooks; see *Cloud Sessions* in `uv-guide.md`. |

## Request flow

```
Telegram update
  └─ BotApp.handle_message
       ├─ select_user (Postgres) ─ reject if not approved
       └─ process_message_content  ── routes by content_type ──┐
                                                               │
  handlers.py:                                                 ▼
    audio / voice ───────────────► summarize(File)
    video / video_note ──────────► download_tg(.mp4) → summarize(path)
    document ────────────────────► summarize_with_document(File, mime)
    text (treated as URL) ── classify_url ──┬─ "youtube" / "castro" ► summarize(url)
                                            └─ "web"  ► WebParser.parse → summarize_text
```

### Summarizer input branching (`summary.py:summarize`)

`utils.classify_url` is the **single** source of URL routing: `handlers.handle_url`
calls it to pick the summarize path and `summarize` calls it again to pick the
download path. Neither may re-derive the kind on its own — a second, narrower
classifier here previously let www-prefixed and uppercase-host media URLs reach
the file upload with the URL string as their file path.

- **YouTube URL** → try transcript (`YouTubeTranscriber.get_transcript`); on
  success summarize the transcript. On failure → `Downloader.download_yt`
  audio, then the file path below.
- **Castro URL** → `Downloader.download_castro` audio → file path.
- **Telegram File** → `Downloader.download_tg(.ogg)` → file path.
- **File path** → `_summarize_via_transcription`: `compress_audio` →
  `AudioTranscriber.transcribe` (Replicate) → `summarize_text` with the user's model.

Spoken content therefore has one route — a transcript — and one fallback: YouTube's
own transcript first, Replicate when there is none. All audio and video load lands on
Replicate, so its cost and latency apply to every such message.

### Modality routing

Audio is routed by content, not by model: `summarize` and the `audio/` branch of
`summarize_with_document` (`SUPPORTED_DOCUMENT_MIME_TYPES` accepts `audio/ogg`) always
transcribe, and the transcript is summarized by the model the user chose.
`ModelSpec.supports_audio` is kept for a future native-audio route and is **read by
nothing**: it is `False` on every model, and setting it `True` changes no routing (pinned by
`test_no_model_claims_audio_before_a_native_route_exists`).

`ModelSpec.supports_files` decides who summarizes any other document. A model with the
flag is handed the document by `file_id`: download → `OpenRouterFiles.upload` → summarize →
`OpenRouterFiles.delete`. A model without it is replaced, for that request only, by
`DEFAULT_MODEL_ID_FOR_SUMMARY` — logged at WARNING, with no user-facing message and no
change to the stored setting. One constant is both the new-user default and this failover,
so it must stay a spec with `supports_files=True` (pinned by
`test_default_summarizing_model_accepts_files`). The audio branch keeps precedence over the
failover. Set the flag from a probe of the model, not from OpenRouter's catalog alone: see
*Documents go to the model by `file_id`* for what a model without the modality does.

## Source-provenance prefixes

Summaries made from a transcript or a parsed webpage are prefixed with an emoji marking
where the content came from (`format_prefixed_summary`). Only a document summarized by
`file_id` returns the raw model text with **no** prefix.

| Prefix | Source |
|--------|--------|
| 📺 | YouTube transcript via `youtube_transcript_api` (primary) |
| 📹 | YouTube transcript via yt-dlp (fallback) |
| 📝 | Audio transcription via Replicate — audio, voice, video, video notes, Castro, and YouTube without a transcript |
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
  per attempt by design — not a double-charge bug. The pre-check calls `limits`' `test()`,
  never `hit(cost=0)`: a zero-cost hit increments nothing, so an exhausted window still
  compares ≤ the limit and reads as open.
- **Retries.** Network/model calls use `tenacity` `@retry`; persistent failure
  surfaces as `RetryError`, which `handle_message` maps to a user-facing
  "try again later" message. Other mapped errors: `LimitExceededError`,
  `WebParseError`. All exceptions are sent to Sentry via `capture_exception`.
- **Sentry log collection is an explicit opt-in.** `config.py` passes
  `LoggingIntegration(capture_sentry_logs=True)` to `sentry_sdk.init`; without it stdlib `logging`
  records stop reaching Sentry Logs while error capture keeps working (pinned by
  `test_sentry_opts_into_log_collection`). `enable_logs=True` was a no-op in sentry-sdk 2.68.0;
  later releases honour it only as a compat fallback slated for removal in the next major, so keep
  the explicit flag rather than switching back. `logging.basicConfig(force=True)` after `init` does not unhook the
  integration: it patches `logging.Logger.callHandlers` rather than adding a root handler.
- **A failed delete leaks an uploaded file for good.** `_summarize_uploaded_file` deletes
  the upload in a `finally`, whatever the model call did. A transient failure there is
  repeated by the SDK's own retries (pinned by a test, so `config.openrouter_client` must not
  be built with `max_retries=0`); a delete that still fails is logged at WARNING. A `@retry`
  around the delete is **rejected**: it would cover no failure the SDK does not already retry
  except a 4xx, which repeating cannot fix, and its wait would hold back a summary that is
  already written. OpenRouter never expires a file, so each such failure stays in the
  workspace and counts toward its 10 GiB quota until removed by hand. An upload that fails
  returns no id, so there is nothing to delete.
- **Temp-file hygiene.** Downloads/compression write UUID-named temp files in the
  CWD; `clean_up` removes them, guarded by a `PROTECTED_FILES` snapshot taken at
  startup. On shutdown `clean_up(all_downloads=True)` sweeps the rest.
- **Fragmented downloads.** `download_yt` leaves yt-dlp's `skip_unavailable_fragments` at
  its default, so a download missing a few fragments still yields usable audio. Setting it
  to `False` is **rejected**: it would turn many tolerable downloads into hard failures,
  while the rare truncated file that crashes the ffmpeg fixup is retryable — `download_yt`
  makes at most two attempts on `DownloadError` (`stop_after_attempt(2)`).
- **YouTube transcript cooldown.** When `ApiBackend.fetch` finds no transcript in the
  default languages, it lists the video's languages and sleeps 60 s before fetching again:
  back-to-back requests get rate-limited or blocked by YouTube (youtube-transcript-api issue
  #572). The sleep is deliberate — **do not shorten or remove it**.
- **Every extraction is screened for block pages by JEV.** A refused parser (region block, bot
  check, login or paywall) still returns non-empty text. `WebParser` passes each backend's output to
  `BlockedPageDetector`, which asks TypeSafe's JEV one `noul` question over the first 20k characters
  (block pages are short; an uncapped Tavily extraction can overflow JEV's input). At p ≥ 0.5 the
  output is a `WebParseError`: a blocked primary falls through to the fallback, a blocked fallback
  ends in "page is not available". The check lives in `WebParser`, not a backend, so it holds
  whichever backend is primary. JEV is a decisions model served only on OpenRouter's
  `POST /api/alpha/decisions`, so it is called with a direct HTTPS request, not through `LLMClient`.
  Calibrated on 2026-09-30 against `typesafe/jev-1.13-20260917`: block pages 0.83–0.99, real pages
  (including an article *about* regional blocking) 0.01–0.03; ~0.4 s and ~$0.0002 per 20k-character
  page. Settled: **fail open** (a detector error logs a warning and keeps the text), **no retry on
  a block page** (outside the backends' `@retry`), **not metered** by `QuotaManager`. A bare
  marketing shell with no block wording is not a block page and is not caught.
- **Replicate over plain HTTP.** `AudioTranscriber` calls `https://api.replicate.com/v1` with
  `curl-cffi`, not the `replicate` SDK, which was dropped as unmaintained: no stable release
  since 2025-05-27 (observed 2026-10). One `transcribe` is four requests — `GET /models/{owner}/{name}`
  for `latest_version.id` (a community model takes a version id, and it is resolved on every
  call rather than pinned), a multipart `POST /files` whose part is named `content`,
  `POST /predictions` with the upload's `urls.get` as `audio_file`, then `GET /predictions/{id}`
  every 10 s. Two retries, nested on purpose: `_poll` repeats its own GET on
  429/500/502/503/504 and on a network error, because the outer `@retry` reruns the whole
  `transcribe` — a second upload and a second billed prediction — so it must not be what
  absorbs a blip on a status check. The outer one covers `ReplicateError` (any HTTP 4xx/5xx)
  only. A network error anywhere else, or one that outlasts the poll retry, is re-raised as
  `TranscriptionError` and is **not** retried. **Do not let a raw `curl-cffi` exception leave
  `transcribe`**: `Summarizer.summarize_with_document` retries on `CurlConnectionError` and
  `CurlSSLError` for its own download, and would rerun the transcription too.
  `TranscriptionError` (also status `failed`, `canceled` or `aborted`, or output without a
  `segments` list) reaches `handle_message` as `Unexpected: ...`. The loop has no overall deadline: a
  prediction stuck in `starting` is polled until Replicate ends it.
- **Settings commands** use a one-time reply keyboard + `register_next_step_handler`
  (`_prompt_choice` → `proceed_*`) and validate against the allow-lists in `config.py`.
- **One `openai` client for every thread.** `config.openrouter_client` is the synchronous
  client, whose HTTP pool is safe to share, so every telebot worker and eval-harness thread
  uses the same one. The per-thread provider this replaced existed only because pydantic-ai's
  `run_sync` ran a separate event loop in each thread.
- **Tracing (optional), text input only.** Enabled only when `LANGFUSE_PUBLIC_KEY` and
  `LANGFUSE_SECRET_KEY` are set (`config.langfuse_client`, else `None`). `config` then imports
  `langfuse.openai`, Langfuse's drop-in for the `openai` SDK, and that import is the whole
  integration: it patches `chat.completions.create` **process-wide**, for every client, and
  records one generation per call (pinned by `test_langfuse_patches_the_openai_sdk_when_enabled`).
  Independent of Sentry; `langfuse_client.shutdown()` flushes on exit.
  - **File runs are never traced.** The patch cannot be switched off per client, so
    `LLMClient.run` sends a request carrying a file part through the client's generic `post`,
    which the drop-in does not wrap. A traced file run would hold token usage and an
    `or_file_…` id in place of the content, and would enter the eval dataset harvest as a
    generation with no source. **Do not move file runs onto `chat.completions.create`.** A media
    message is traced all the same, since it is summarized from a transcript — a plain string.
  - **Cost is OpenRouter's own.** The drop-in copies `usage.cost` from the reply onto the
    generation, so the trace shows what was charged; nothing in this codebase reports cost, and
    no `usage: {include: true}` is needed. It matched OpenRouter's figure exactly on all three
    registered models (2026-10-01).
  - **A generation's model parameters are not what was sent.** The drop-in lists its own
    defaults (`temperature: 1`, `max_tokens: Infinity`, …) for parameters the request never
    carried, and does not record `reasoning.effort`, which travels in `extra_body`. The
    thinking level is on the trace as metadata instead (next bullet).
  - **`Tracer.observe_message` opens no span**, so a message whose every model call carries an
    uploaded file produces no trace at all. It names the trace `handle_message`, tags it with
    the content type, and adds `prompt_key`, `prompt_version`, `target_language` and
    `thinking_level` as metadata — values no generation carries, kept so a trace is
    filterable and replayable as a dataset item (the model id is already on the generation). `prompt_version`
    hashes `SYSTEM_INSTRUCTION` **and** the strategy template, so editing either moves it.
  - **Prompt and content are separate parts.** `summarize_text` sends them as two text parts, not
    one concatenated string, so a trace separates the wording from the content (a multi-part text
    prompt is still text-only, so it stays traced, as two `text` parts of the user message); blank content (e.g. `AudioTranscriber.transcribe` returns
    `""` for silence or music) sends the prompt part alone, so do not assume a content part.
  - A trace spans the model call only, not the download, parse or upload around it; a retried
    `summarize_text` produces one trace per attempt.
  - **Trace-level input/output is deprecated** in Langfuse v4 — tables, judges and exports read an
    observation instead. **Never add `set_current_trace_io()` or an equivalent**, not even for a
    legacy evaluator; migrate the evaluator to the root observation.
  - Everything built *on top* of these traces — datasets, scorers, judges, `scripts/eval/` — is
    owned by `evals.md`.
