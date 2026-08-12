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

The hygiene hooks — `gitleaks`, `end-of-file-fixer`, `trailing-whitespace`, the `check-*` hooks,
`detect-private-key`, `uv-lock` — run on **every** commit, docs-only ones included, and
`end-of-file-fixer` rewrites files rather than just rejecting them. The Python hooks are narrower,
and their scopes are not identical:

| Hook | Matches |
|------|---------|
| `ruff-check`, `ruff-format` | any staged Python file |
| `pytest` | `src/`, `tests/`, `pyproject.toml`, `uv.lock` |
| `ty` | `src/`, `pyproject.toml`, `uv.lock` — **not** `tests/` |

So a test-only change is never type-checked at commit time; run `uvx ty check .` yourself if the
change could affect types.

Do not pre-run the hook suite as a gate before committing — that is the hook's job, and it is
already what runs. Running `uv run pytest --cov` while iterating on code is a different thing and is
expected; see `docs/context/uv-guide.md`.

**Coverage:** The project is at 100% line coverage — keep it there by covering new or changed code in the same commit. There is no `--cov-fail-under` gate; review the report printed by the pytest hook and make sure your commit does not introduce new uncovered lines. CI separately uploads branch coverage to Codecov.

**Ruff:** the hooks auto-fix and format, so no manual run is needed. They see only your staged files — a green commit is not a green tree, and only CI sweeps the rest.

**Always `@latest`:** every uvx call site pins it — both ruff hooks, the `ty` hook, and `.github/workflows/typechecking.yml`. Bare `uvx <tool>` reuses a `uv tool install`ed copy that may lag behind CI.
