# uv Guide

The project uses [uv](https://docs.astral.sh/uv/) for dependency management. Run every Python
command through `uv run`; never bare `python`, `pip`, `poetry`, or `conda`.

```bash
uv sync                              # install deps (dev + test by default)
uv run pytest --cov                  # run the tests with the coverage report
uv run python src/main.py            # run the bot
uv run python scripts/db.py          # bootstrap the users table
uv run alembic upgrade head          # apply migrations
uv run alembic revision --autogenerate  # generate a migration
uv run modal deploy scripts/cron.py  # deploy the rate-limit-reset cron

uv add package-name                  # add a production dependency
uv add --group dev package-name      # add a dev dependency
uv lock --upgrade                    # update dependencies
```

`uv run pytest --cov` needs no extra flags for the usual case — `[tool.coverage.run]` already pins
`source` and `[tool.coverage.report]` already sets `show_missing`, so `--cov=src` and
`--cov-report=term-missing` add nothing. It is also what the pre-commit hook runs (plus `-q`); see
`docs/context/git-guide.md` for how that gate works.

The one flag that is *not* redundant is `--cov-branch`. `[tool.coverage.run]` sets no `branch`, so
the command above measures lines only, while CI runs `uv run pytest --cov --cov-branch
--cov-report=xml` and uploads branch coverage to Codecov. To reproduce anything Codecov flags, add
`--cov-branch` locally or the numbers will not match.

Use `uv add` rather than hand-editing `pyproject.toml`. Keep production dependencies in
`[project.dependencies]`; everything else goes in the appropriate group under `[dependency-groups]`.

## Dependency Groups

| Group | Purpose | When active |
|-------|---------|-------------|
| `dev` | Local development (alembic, modal, python-dotenv, yt-dlp[deno]) | Default — included by `uv sync` |
| `test` | Local testing (pytest, coverage, fakeredis, pytest-mock, pytest-cov) | Default — included by `uv sync` |
| `build` | CI build/deploy (alembic, modal, psycopg2-binary, sqlalchemy) | CI only — explicit `uv sync --group build` |
| `modal` | Modal cron image (redis) | CI only — explicit `uv sync --group modal` |

`default-groups = ["dev", "test"]` in `[tool.uv]` means `uv sync` always installs `dev` and
`test`. Do not add `build` or `modal` to local installs. The `Dockerfile` excludes every
non-production group explicitly (`--no-group dev/test/modal/build`) rather than relying on the
defaults, so adding a group means adding a `--no-group` line there too.

**`scripts/eval/` gets no dependency group of its own, and one was tried and removed.** The
harness imports `config`, `llm` and `prompts` from `src/`, so running it needs the bot's entire
runtime set — a group could never be synced on its own, which is the only thing such a group
would have been for. Everything it needs is already a project or `dev` dependency, so a group
would have held `python-dotenv` and nothing else. Install the harness with a plain `uv sync`.

**`requests` is a production dependency**, not a transitive one to rely on. `src/transcription.py`
and `src/services.py` both catch `requests.exceptions`; it reached them through
`exa-py`/`tavily-python` for a long time before being declared. Anything `src/`
imports belongs in `[project.dependencies]`, however reliably some other package drags it in.

**Do not swap `requests.exceptions` for `curl_cffi.requests.exceptions`.** The names all exist on
both sides — `SSLError`, `ProxyError`, `ChunkedEncodingError`, `ReadTimeout` — which makes the swap
look like a free way to drop a dependency. They are **unrelated classes with no subclass relation
in either direction**, so `except` on one never catches the other, and the failure is silent: the
handler simply stops firing and `tenacity` stops retrying, with no error to say so. The exceptions
are not raised by `curl-cffi` at those sites anyway — `pyTelegramBotAPI` and
`youtube-transcript-api` both transport over `requests`, so their errors *are* `requests`
exceptions, and that is an API contract of those libraries rather than an implementation detail.
`summary.py` is the reverse case and catches only the `curl-cffi` side, in
`summarize_with_document`: that method downloads through `curl-cffi`, and nothing under the
`Summarizer` retries transports over `requests` — the `openai` SDK uses httpx.
Dropping `requests` means replacing those two libraries, not rewriting an import.

`redis` is declared twice on purpose — once in `[project.dependencies]` for the bot and once in
the `modal` group for the cron image. Bump both together, and do not fold either back into a
`limits[redis]` extra; see *Why this stack* in `architecture.md` for the version cap that forbids it.

## Cloud Sessions

Claude Code cloud sessions run on an Ubuntu 24.04 VM whose image (as observed 2026-09) ships
Python 3.10–3.13, default `python3` 3.11, and **uv 0.8.17** — no 3.14, and a uv too old to trust
with this `uv.lock`.
Setup is split in two, because the environment's setup script runs outside the repo:

1. **Environment setup script** (pasted into the claude.ai environment dialog; the reference copy
   is in `README.md` → *Claude Cloud Sessions* — edit both together) provisions the VM
   under `set -euo pipefail`, logging to `/root/setup.log`:
   - **uv**: the `astral.sh` installer, which replaces the image's uv in `/root/.local/bin`.
   - **pre-commit**: `uv tool install pre-commit`.

   The uv installer needs **Full** network access: `astral.sh` is blocked on **Trusted** (see
   below). On **Trusted**, install uv with `python3 -m pip install --upgrade
   --break-system-packages uv`, then
   `ln -sf "$(python3 -c 'import uv; print(uv.find_uv_bin())')" /root/.local/bin/uv`, since pip
   puts uv in `/usr/local/bin`, behind the image's copy on `PATH` — and first check whether uv's
   Python download works there.

   The script installs **no Python** and the environment sets **no variables**. The hook's
   `uv sync --frozen` downloads exactly the patch pinned in `.python-version` on first use, as it
   would locally; this works on **Full**. Do not add `uv python install 3.14` to the script: it
   gets the *newest* 3.14, not the pinned patch. Do not set `UV_PYTHON` or
   `UV_PYTHON_DOWNLOADS`: environment variables apply to every repo started in the environment,
   and `UV_PYTHON_DOWNLOADS=manual` turns a patch mismatch into a failure of every uv command.
2. **`scripts/cloud_session_start.sh`**, a SessionStart hook in `.claude/settings.json`, runs in
   the repo in every cloud session. Its essential job is `pre-commit install`: nothing else puts
   the hooks into a fresh clone's `.git/hooks`, so without it cloud commits silently skip every
   check. It also runs `uv sync --frozen`; `uv run` would sync on first use anyway, but `--frozen`
   installs strictly from `uv.lock` — with `exclude-newer = "3 days"`, a re-resolve could rewrite
   the lock. It exits at once unless `CLAUDE_CODE_REMOTE=true`, so local sessions are untouched,
   and logs to `~/session-start.log`, since SessionStart stdout is fed into Claude's context.

   Do not move `pre-commit install` into the setup script: it runs outside the repo, a
   `|| true` would hide the failure, and the setup script is cached and skipped while each
   session gets a fresh clone.

Network constraints behind those choices (sandbox egress proxy, observed 2026-09):

- `astral.sh` is not on the **Trusted** allowlist; the uv install script 403s there.
- The Claude Code docs say the GitHub proxy serves release assets only for repos attached to the
  session, at any access level. In practice, on **Full**, both first-choice downloads work
  (observed 2026-09): the astral.sh installer put uv 0.12.20 in `/root/.local/bin`, replacing
  the image's 0.8.17, and `uv python install 3.14` installed a uv-managed CPython 3.14.7 that
  `.venv` uses.
- The image's `apt` sources include PPAs on `ppa.launchpadcontent.net`, which **Trusted** blocks
  (`x-deny-reason: host_not_allowed`), so any `apt-get update` fails there. A **Custom** entry for
  that host did not take effect. The environment uses **Full** network access; whether
  uv's Python download works on **Trusted** is untested.

## Codex Cloud

Codex cloud tasks start from a snapshot of the filesystem the environment's **install script**
prepared in `/workspace/ai-summarizer-telegram-bot`; the **start skill** is instructions the agent
reads at the start of a task. Both live in the Codex environment settings, and the reference copies
are in `README.md` → *Codex Cloud*. Edit both places together. Unlike Claude's setup script, the
install script runs inside the repo, so it does project setup (`uv sync --frozen`,
`pre-commit install`) itself and needs no SessionStart hook.

To change the setup, open the environment's **Edit** conversation and have Codex run the new
script there, then **Save draft → Republish**. Republishing alone does not rerun the install
script: it captures whatever filesystem was last prepared, so tasks keep starting from the old one.

Facts behind the script (Codex image, observed 2026-10):

- **Tasks have no network.** Every outbound connection fails with `Operation not permitted`; only
  the install script has internet. So the bot cannot run live (no Telegram, PostgreSQL or Redis),
  and the test suite is the only useful check. The script fills uv's cache with ruff and ty, which
  the pre-commit hooks call as `uvx …@latest`, and then sets `UV_OFFLINE=1` in `env.sh`. Offline,
  `uvx …@latest` resolves from the cache and `uv run` and `uv sync` keep working. Two consequences:
  ruff and ty stay at the versions the install script cached, and a change to `.python-version`
  or `uv.lock` that needs new downloads requires rerunning the install script.
- `$HOME` is read-only. `/workspace/env.sh` points `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`,
  `XDG_DATA_HOME` and `XDG_BIN_HOME` at `/workspace`. uv's cache, Python and tools, pre-commit's
  cache and Go's build cache all follow those variables. Every new shell must `source` it, so the
  start skill says so.
- `/usr/bin/go` is not the Go toolchain: it belongs to no package, and `go version` fails with
  `Go: Unknown option: version`. pre-commit uses any `go` on `PATH` to build the gitleaks
  hook, and only downloads its own Go when there is none, so the script installs the latest stable
  Go into `/workspace/go`, ahead of it on `PATH`. It reads the archive name and SHA-256 from
  `https://go.dev/dl/?mode=json`, the same index pre-commit uses, so there is no version to bump.
- ffmpeg ships with the image, and so does uv, but that uv can lag behind `.python-version`: uv
  knows only the Python releases it was built with, and `uv sync` fails with `No interpreter found
  for Python …` (the image had 0.12.19, too old for 3.14.8). The script installs the current uv
  with the `astral.sh` installer into `XDG_BIN_HOME`, ahead of the image's copy on `PATH`;
  `UV_NO_MODIFY_PATH=1` because the shell profiles in `$HOME` are read-only, and
  `XDG_CONFIG_HOME` because the installer writes its receipt there and fails if it cannot.

The script deliberately has no live-service check or smoke script, which Codex's autogenerated
setup adds. Tasks cannot reach the services anyway, and the pytest suite already covers the app
graph without them.

## Pixi

`pyproject.toml` contains a `[tool.pixi.*]` workspace config. Pixi manages system-level
dependencies `uv` cannot install from PyPI — specifically `ffmpeg` and `deno`. Do not invoke `pixi`
for Python or project work; use `uv` for all of that.

`pixi.lock` is **not tracked** (it is in `.gitignore`). Pixi is used only locally and rarely, `pixi`
regenerates the lock on its next run, and a tracked lock kept colliding with Renovate's
lock-maintenance PRs. Do not commit it back.

## Database

Use the SQLAlchemy ORM, not raw SQL. Every schema change needs an Alembic migration
(`uv run alembic revision --autogenerate`), tested with `uv run alembic upgrade head` before
committing. `black` is in the `dev` group **only** because Alembic invokes it internally to format
autogenerated migrations — keep the dependency; do not run `black` on project code.
