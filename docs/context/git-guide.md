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
deps: bump google-genai to 2.8.0
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
| `pytest` | `src/`, `tests/`, `pyproject.toml`, `uv.lock` |
| `ty` | `src/`, `pyproject.toml`, `uv.lock` — **not** `tests/` |

Two consequences worth holding onto. A test-only change is never type-checked at commit time, so run
`uvx ty@latest check .` yourself when it could affect types — `@latest` per *Always `@latest`*
below, which the hook honours too. And five hooks *rewrite* files instead of merely rejecting them —
`end-of-file-fixer`, `trailing-whitespace`, `ruff-check --fix`, `ruff-format` (it formats in place;
there is no `--check`), and `uv-lock` (it regenerates `uv.lock`) — so a "failed" commit has often
already fixed itself and only needs re-staging.

Do not pre-run the hook suite as a gate before committing — that is the hook's job, and it is
already what runs. Running `uv run pytest --cov` while iterating on code is a different thing and is
expected; see `docs/context/uv-guide.md`.

**Coverage:** The project is at 100% line coverage — keep it there by covering new or changed code in the same commit. There is no `--cov-fail-under` gate; review the report printed by the pytest hook and make sure your commit does not introduce new uncovered lines. CI separately uploads branch coverage to Codecov.

**Ruff:** the hooks auto-fix and format, so no manual run is needed. They see only your staged files — a green commit is not a green tree, and only CI sweeps the rest.

**Always `@latest`:** every uvx call site pins it — both ruff hooks, the `ty` hook, and `.github/workflows/typechecking.yml`. Bare `uvx <tool>` reuses a `uv tool install`ed copy that may lag behind CI.

## CI Workflows

`astral-sh/setup-uv` is pinned to `version: "latest-known"` in `typechecking.yml` and `codecov.yml`.
That is deliberate and different from the uvx rule above: `latest-known` installs the newest uv whose
checksum ships inside the action, so the install is verified and needs no GitHub API lookup at run
time. Leaving `version` unset would fall through to `latest` — the project pins no uv version in
`pyproject.toml` and has no `.tool-versions` — which resolves over the API and skips that checksum.
Do not "upgrade" it to `latest`.

`enable-cache: "auto"` is spelled out in both, which is also the v10 default — written explicitly so
the choice is visible at the call site and survives a future change of default. `auto` caches on
GitHub-hosted runners *except* on `release`, tag-push, `pull_request_target`, and `workflow_run`
events. That exclusion is a cache-poisoning guard: those events run with the base repo's permissions
or produce published artifacts, so a cache entry written by a less-trusted run must not flow into
them. **Do not set `enable-cache: true`** — it opts out of the guard for no gain. The only run it
would change today is `codecov.yml` on a tag push (its trigger is bare `on: push`), and skipping the
cache there costs a few seconds of cold install.

The uv cache is a real trust boundary, not just a speed knob: `uv sync` verifies downloads against
the hashes in `uv.lock`, but a restored cache holds *already-unpacked* wheels that are not re-checked
against those hashes. No `cache-dependency-glob` is needed — the default already covers `uv.lock` and
`pyproject.toml`.
