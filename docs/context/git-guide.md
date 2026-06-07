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

Run all four manually before each commit. `ruff format .`, `ruff check .`, and `uv run pytest` also run automatically via pre-commit hooks; `ty check .` does not.

1. `ruff format .`
2. `ruff check .`
3. `ty check .`
4. `uv run pytest`

**Workflow:** Run `ruff format .` before committing to automatically format your code. Run `ruff check --fix` to automatically resolve fixable linting errors.
