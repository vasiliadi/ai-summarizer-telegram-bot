# Tooling Guide

This document describes the developer tools used in the project and how to run them. For running the project and managing dependencies with `uv`, see `docs/context/uv-guide.md`. For the list of technologies used in the project, see `docs/context/tech-stack.md`.

## Tools

The project uses the following developer tools:

- **ruff** - Linting and formatting ([ruff](https://docs.astral.sh/ruff/))
- **ty** - Type checking ([ty](https://docs.astral.sh/ty/), modern type checker from Astral)
- **pre-commit** - Git commit hooks
- **pytest** - Unit testing

## Code Quality

Run these directly (installed as system-wide executables):

- Linting: `ruff check .`
- Formatting: `ruff format .`
- Type checking: `ty check .`
- Commit hooks: `pre-commit run --all-files`

`pre-commit` runs automatically on every `git commit`.

## Testing & Quality Assurance

The project uses `pytest` for unit testing. Tests live in `tests/`, configured in `pyproject.toml` under `[tool.pytest.ini_options]` with `pythonpath = ["src"]`.

### Structure

- `tests/conftest.py` — shared fixtures
- `tests/test_*.py` — one file per source module (commands, database, download, handlers, services, state, summary, transcription, utils)

### Run tests

```bash
uv run pytest
```

Run tests before every commit.

## Tooling Rules for AI Agents

### Code Quality

Follow the pre-commit sequence in `docs/context/git-guide.md` before every commit.

- Follow Google Python Style Guide for docstrings
- Use type hints for all function signatures

### Testing Strategy

- Write property-based tests for critical business logic
- Test database operations with transactions
- Mock external API calls in tests

### Dependencies

- Prefer Astral ecosystem tools (`uv`, `ruff`, `ty`) for consistency
- Minimize dependency count - evaluate if new dependencies are truly needed
- Review security advisories for dependencies regularly
