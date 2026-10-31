# Git Guide

## Commit Convention

All commit messages use the **scope-prefixed** format. Lead with the area of the codebase that
changed, not a change type — the description already conveys what kind of change it is, and the
scope is what people actually scan for when debugging or reviewing history.

```text
scope: description

[optional body]
```

* **scope** — the subsystem, module, or area affected. Usually a file/module name without its
  extension (e.g. `summary`, `prompts`, `config`) or a logical component (e.g. `deps`, `docs`,
  `ci`). For changes that span a path, a slash-separated scope is fine (e.g. `net/http:`).
  Lowercase, no `type(...)` wrapper.
* **description** — concise, imperative mood, lowercase first word, no trailing period.

Do not use Conventional Commit types (`feat`, `fix`, `chore`, …) and do not add gitmoji.

```text
summary: handle empty transcript
deps: bump openai to 3.20.0
ci: update codecov action
```

## Pre-Commit Checks

Hooks run automatically at commit time, each scoped to the files it matches. Never bypass them with
`--no-verify`. If a hook fails or modifies files, fix, re-stage, and commit again.

Only `gitleaks` runs unconditionally; every other hook is file-scoped, and barely any two share a
scope. Half the filters live in `.pre-commit-config.yaml`, half in the upstream
`.pre-commit-hooks.yaml` of each pinned repo — check both before claiming a hook covered something:

| Hook | Matches |
|------|---------|
| `gitleaks` | every commit — `pass_filenames: false`, it scans the staged diff itself |
| `check-added-large-files` | files staged for **addition** only — no `--enforce-all`, so edits to existing files are never size-checked |
| `end-of-file-fixer`, `check-merge-conflict`, `detect-private-key` | every staged text file |
| `trailing-whitespace` | every staged text file **except** `*.py` — `ruff-format` owns those. `.pyi` and `.ipynb` are *not* excluded, so they get both |
| `check-yaml` / `check-toml` | staged `.yaml`/`.yml` / `.toml` files |
| `uv-lock` | `uv.lock`, `pyproject.toml`, `uv.toml` |
| `ruff-check`, `ruff-format` | staged `.py`, `.pyi`, `.ipynb` |
| `pytest` | `src/`, `tests/`, `scripts/eval/`, `pyproject.toml`, `uv.lock` |
| `ty` | `src/`, `pyproject.toml`, `uv.lock` — **not** `tests/` |

`default_install_hook_types` also installs `post-merge`, `post-checkout` and `post-rewrite` hooks,
where `uv-sync` runs `uv sync` unconditionally, so switching branches, pulling or rebasing
re-syncs `.venv`. On `git checkout` it also prints the pre-commit hooks, all skipped except
`uv-sync`.

Two consequences worth holding onto. A test-only change is never type-checked at commit time, so run
`uvx ty@latest check .` yourself when it could affect types — `@latest` per *Always `@latest`*
below, which the hook honours too. And five hooks *rewrite* files instead of merely rejecting them —
`end-of-file-fixer`, `trailing-whitespace`, `ruff-check --fix`, `ruff-format` (it formats in place;
there is no `--check`), and `uv-lock` (it regenerates `uv.lock`) — so a "failed" commit has often
already fixed itself and only needs re-staging.

Do not pre-run the hook suite as a gate before committing — that is the hook's job, and it is
already what runs. Running `uv run pytest --cov` while iterating on code is a different thing and is
expected; see `docs/uv-guide.md`.

**Coverage:** `src/` is at 100% line coverage — keep it there by covering new or changed code in the same commit. There is no `--cov-fail-under` gate; review the report printed by the pytest hook and make sure your commit does not introduce new uncovered lines. CI separately uploads branch coverage to Codecov.

`scripts/eval/` has no coverage target. `[tool.coverage.run]` measures `src` only, so neither the hook's report nor Codecov counts it. Its tests (`tests/test_eval_*.py`) still run in the same pytest hook, which fires on changes under `scripts/eval/`, and must pass: cover the behaviour that matters, not a percentage.

**Ruff:** the hooks auto-fix and format, so no manual run is needed. They see only your staged files — a green commit is not a green tree, and only CI sweeps the rest.

**Always `@latest`:** every uvx call site pins it — both ruff hooks, the `ty` hook, `.github/workflows/typechecking.yml` and `.github/workflows/linting.yml`. Bare `uvx <tool>` reuses a `uv tool install`ed copy that may lag behind CI.

## CI Workflows

`linting.yml` runs `ruff check` and `ruff format --check` over the whole tree (`uvx
ruff@latest`), `typechecking.yml` runs `ty` over `src/`, `codecov.yml` runs the tests with branch
coverage, and `sentry_release.yml` creates a Sentry release on every push to `main`.
The three check workflows run standalone only off `main`: linting and type checking on
`pull_request`, the tests on push to any other branch, which is how a PR gets all three required
checks. On `main` they run once, inside `deploy.yml`, which calls them through `workflow_call` on
every push to `main` (a job's `needs` can only name jobs of its own workflow), so they show as
`Deploy / linting / Linting` and so on, and the `main` Codecov upload comes from Deploy's `tests`
job. Once all three pass, Deploy's migrate job creates the `users` table, applies migrations and
deploys the Modal cron (see *Deploy steps run outside the image build* in `architecture.md`). It
needs the repository secrets `DSN`, `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`, each passed only to
the step that uses it. Its `concurrency` group sits on that job, not the workflow, so every
commit's checks run at once and are never cancelled. The group never cancels a running migration,
and `queue: max` keeps every waiting migrate job: checks can finish out of order, and the default
`queue: single` keeps only the last job to join, which can be an older commit's that then replaces
the newest. Waiting jobs run in the order they joined, and the job's first step skips the remaining
steps for a commit that is no longer the tip of `main`, so an older commit never redeploys over a
newer one. Only the newest commit deploys, and only if its checks and deploy steps pass; if they
fail, the older commits it skipped stay undeployed until a fix lands. actionlint 1.7.12 flags `queue` as an unknown key; GitHub
documents it, so don't remove it to satisfy the linter.

Every workflow that runs uv (all but `sentry_release.yml`) pins `astral-sh/setup-uv` to `version: "latest-known"`,
deliberately and unlike the uvx rule above. The project pins no uv version, so leaving `version`
unset means `latest`. The action verifies a download only against the checksum table baked into
the action release you pinned, and **silently skips verification** for a uv newer than that table
— which `latest` usually is. `latest-known` resolves to the newest uv *inside* the table, so the
checksum is always checked. Do not "upgrade" it to `latest`.

All of them also spell out `enable-cache: "auto"` (the default, written so the choice survives a change of
default). `auto` skips the cache on `release`, tag-push, `pull_request_target`, and `workflow_run`
events — a cache-poisoning guard, because a restored cache holds unpacked wheels that `uv sync` does
not re-check against `uv.lock` hashes. **Do not set `enable-cache: true`**; it drops the guard to save
seconds. No `cache-dependency-glob` is needed — the default covers `uv.lock` and `pyproject.toml`.

No workflow uses `actions/setup-python`: `uv sync` downloads the exact `.python-version` patch
itself, as the Dockerfile does. `setup-python` reads a separate manifest that can lag behind a patch
uv already installs, so a `.python-version` bump would break CI for a day. The jobs that run Python
set `cache-python: true` so the interpreter comes from the Actions cache instead of a new download.
