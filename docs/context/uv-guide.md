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

1. **Environment setup script** (claude.ai environment dialog, not in the repo) provisions the VM:
   `apt-get install python3.14 python3.14-venv` from the deadsnakes PPA the image already lists,
   `python3 -m pip install --upgrade --break-system-packages uv`, then
   `ln -sf "$(python3 -c 'import uv; print(uv.find_uv_bin())')" /root/.local/bin/uv` — pip puts
   the new uv in `/usr/local/bin`, behind the preinstalled one in `/root/.local/bin` on `PATH` —
   and finally `uv tool install pre-commit`. The environment's variables set
   `UV_PYTHON=python3.14` and `UV_PYTHON_DOWNLOADS=never`.
2. **`scripts/cloud_session_start.sh`**, a SessionStart hook in `.claude/settings.json`, runs
   `uv sync --frozen` and installs the pre-commit hooks in every cloud session. It exits at once
   unless `CLAUDE_CODE_REMOTE=true`, so local sessions are untouched. `--frozen` matters: with
   `exclude-newer = "3 days"`, a plain `uv sync` can re-resolve and rewrite `uv.lock`. Its output
   goes to `~/session-start.log`, since SessionStart stdout is fed into Claude's context.

Network constraints behind those choices (sandbox egress proxy, observed 2026-09):

- `astral.sh` is not on the **Trusted** allowlist, so the uv install script 403s; get uv from PyPI.
- `uv python install` / `uv self update` download from GitHub releases of repos not attached to
  the session, which the GitHub proxy refuses — hence the PPA and `UV_PYTHON_DOWNLOADS=never`.
- The image's `apt` sources include PPAs on `ppa.launchpadcontent.net`, which **Trusted** blocks
  (`x-deny-reason: host_not_allowed`), so any `apt-get update` fails there. The environment
  therefore uses **Full** network access; a **Custom** entry for that host did not take effect.

## Pixi

`pyproject.toml` contains a `[tool.pixi.*]` workspace config and `pixi.lock` exists. Pixi manages
system-level dependencies `uv` cannot install from PyPI — specifically `ffmpeg` and `deno`. Do not
invoke `pixi` for Python or project work; use `uv` for all of that.

## Database

Use the SQLAlchemy ORM, not raw SQL. Every schema change needs an Alembic migration
(`uv run alembic revision --autogenerate`), tested with `uv run alembic upgrade head` before
committing. `black` is in the `dev` group **only** because Alembic invokes it internally to format
autogenerated migrations — keep the dependency; do not run `black` on project code.
