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

Hooks run automatically at commit time, each scoped to the files it matches — the ruff hooks to any staged Python file, `ty` and `pytest` to `src/`, `tests/`, `pyproject.toml`, and `uv.lock` — so a docs-only commit skips all four. Do not run them manually first (the ruff auto-fixers below are the exception), and never bypass them with `--no-verify`. If a hook fails or modifies files, fix, re-stage, and commit again.

**Coverage:** The project is at 100% line coverage — keep it there by covering new or changed code in the same commit. There is no `--cov-fail-under` gate; review the report printed by the pytest hook and make sure your commit does not introduce new uncovered lines. CI separately uploads branch coverage to Codecov.

**Ruff:** Run `uvx ruff@latest format .` and `uvx ruff@latest check --fix` before committing. Keep the `@latest` — bare `uvx ruff` reuses a `uv tool install`ed Ruff, which may lag behind CI. The hooks run that same Ruff over your staged files, so the two never disagree; a release can still surface new rules at commit time, and only CI sweeps files your commit did not touch.
