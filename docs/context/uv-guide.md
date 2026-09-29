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

**`requests` is a production dependency**, not a transitive one to rely on. `src/transcription.py`,
`src/services.py` and `src/summary.py` all catch `requests.exceptions`; it reached them through
`exa-py`/`tavily-python`/`replicate` for a long time before being declared. Anything `src/`
imports belongs in `[project.dependencies]`, however reliably some other package drags it in.

**Do not swap `requests.exceptions` for `curl_cffi.requests.exceptions`.** The names all exist on
both sides — `SSLError`, `ProxyError`, `ChunkedEncodingError`, `ReadTimeout` — which makes the swap
look like a free way to drop a dependency. They are **unrelated classes with no subclass relation
in either direction**, so `except` on one never catches the other, and the failure is silent: the
handler simply stops firing and `tenacity` stops retrying, with no error to say so. The exceptions
are not raised by `curl-cffi` at those sites anyway — `pyTelegramBotAPI` and
`youtube-transcript-api` both transport over `requests`, so their errors *are* `requests`
exceptions, and that is an API contract of those libraries rather than an implementation detail.
`summary.py` imports both deliberately and catches both in `summarize_with_document`, which is the
one path that also downloads through `curl-cffi`; `summarize_with_file` takes an already-local path
and needs only the `requests` side. Dropping `requests` means replacing those two libraries, not
rewriting an import.

`redis` is declared twice on purpose — once in `[project.dependencies]` for the bot and once in
the `modal` group for the cron image. Bump both together, and do not fold either back into a
`limits[redis]` extra; see *Why this stack* in `architecture.md` for the version cap that forbids it.

## Cloud Sessions

Claude Code cloud sessions run on an Ubuntu 24.04 VM whose image ships Python 3.10–3.13 (default
`python3` is 3.11) and **uv 0.8.17** — no 3.14, and a uv too old to trust with this `uv.lock`.
Setup is split in two, because the environment's setup script runs outside the repo:

1. **Environment setup script** (pasted into the claude.ai environment dialog; the reference copy
   is in `README.md` → *Claude Cloud Sessions* — edit both together) provisions the VM
   under `set -euo pipefail`, logging to `/root/setup.log`:
   - **uv**: the `astral.sh` installer, which replaces the image's uv in `/root/.local/bin`.
   - **Python 3.14**: `uv python install 3.14`, a uv-managed CPython.
   - **pre-commit**: `uv tool install pre-commit`.

   An earlier version fell back to pip for uv and to the deadsnakes PPA for Python; neither
   fallback ever ran, so they were dropped. The uv installer needs **Full** network access, as
   `astral.sh` is blocked on **Trusted** (see below). If the environment moves to **Trusted**, restore the uv fallback —
   `python3 -m pip install --upgrade --break-system-packages uv`, then
   `ln -sf "$(python3 -c 'import uv; print(uv.find_uv_bin())')" /root/.local/bin/uv`, since pip
   puts uv in `/usr/local/bin`, behind the image's copy on `PATH` — and first check whether
   `uv python install` works there.

   The environment sets **no variables**. uv follows `.python-version` (`3.14.7`, an exact patch)
   as it does locally; when the setup script's `uv python install 3.14` got a different patch —
   a newer 3.14 at cache-build time, or `.python-version` bumped since — uv downloads the pinned
   one on first use, which works on **Full**. An earlier version set `UV_PYTHON=3.14` and
   `UV_PYTHON_DOWNLOADS=manual`, chosen while Python downloads were assumed blocked; they were
   dropped because `manual` turned any patch mismatch into a failure, and both variables apply to
   every repo started in the environment.
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
  `uv python install` works on **Trusted** is untested.

## Pixi

`pyproject.toml` contains a `[tool.pixi.*]` workspace config and `pixi.lock` exists. Pixi manages
system-level dependencies `uv` cannot install from PyPI — specifically `ffmpeg` and `deno`. Do not
invoke `pixi` for Python or project work; use `uv` for all of that.

## Database

Use the SQLAlchemy ORM, not raw SQL. Every schema change needs an Alembic migration
(`uv run alembic revision --autogenerate`), tested with `uv run alembic upgrade head` before
committing. `black` is in the `dev` group **only** because Alembic invokes it internally to format
autogenerated migrations — keep the dependency; do not run `black` on project code.
