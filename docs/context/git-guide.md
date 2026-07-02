# Git Guide

This guide establishes the Git conventions, workflow, and pre-commit checks for the AI Summarizer Telegram Bot project.

## Git Conventions

All commit messages must use the **scope-prefixed** format. Lead with the area of the codebase
that changed, not a change type — the description already conveys what kind of change it is, and
the scope is what people actually scan for when debugging or reviewing history.

**Format:**

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

**Examples:**

```text
summary: handle empty transcript
prompts: tighten system instruction
deps: bump google-genai to 2.8.0
docs: link SOCKS proxy release
ci: update codecov action
```

---

## Pre-Commit Checks

All checks (lint, format, types, tests) run automatically as pre-commit hooks when you commit — do not run them manually first (the ruff auto-fixers under **Workflow** below are the exception), and never bypass them with `--no-verify`. If a hook fails or modifies files, fix, re-stage, and commit again.

**Coverage:** The project is at 100% line coverage — keep it there by covering new or changed code in the same commit. There is no `--cov-fail-under` gate; review the report printed by the pytest hook and make sure your commit does not introduce new uncovered lines. CI separately uploads branch coverage to Codecov.

**Workflow:** Run `uvx ruff format .` before committing to automatically format your code. Run `uvx ruff check --fix` to automatically resolve fixable linting errors. Note: `uvx` resolves the latest Ruff while the hooks pin their own version, so the two can disagree after a Ruff release — if the format hook still modifies files, trust the hook's output.
