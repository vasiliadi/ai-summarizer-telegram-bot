# Git Guide

This guide establishes the Git conventions, workflow, and pre-commit checks for the AI Summarizer Telegram Bot project.

## Git Conventions

All commit messages must follow the **Conventional Commits** specification.

**Format:**

```text
type(scope): subject

[optional body]
```

**Valid Types:**

* `feat`: A new feature
* `fix`: A bug fix
* `docs`: Documentation changes
* `style`: Code formatting (no functional changes)
* `refactor`: Code restructuring
* `test`: Adding or updating tests
* `chore`: Maintenance, dependencies, config updates

*(Note: Gitmoji is required. Always prefix the subject with the appropriate emoji, e.g. ✨ for feat, 🐛 for fix, 📝 for docs, 🎨 for style, ♻️ for refactor, ✅ for test, 🔧 for chore).*

---

## Pre-Commit Checks

Pass these checks before each commit:

1. `ruff format .`
2. `ruff check .`
3. `ty check .`
4. `uv run pytest`

**Workflow:** Run `ruff format .` before committing to automatically format your code. Run `ruff check --fix` to automatically resolve fixable linting errors.
