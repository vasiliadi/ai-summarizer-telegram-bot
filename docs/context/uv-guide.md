# uv Guide

This document explains how to run the project and manage dependencies using `uv`. For the developer tools used in the project, see `docs/context/tooling-guide.md`.

## Package Management

This project uses [uv](https://docs.astral.sh/uv/) as the package manager for fast, reliable Python dependency management.

## Running the Project with uv

Run all Python commands through `uv run`:

```bash
# Run the main application
uv run python src/main.py

# Run database migrations
uv run python scripts/db.py
uv run alembic upgrade head

# Generate new migration
uv run alembic revision --autogenerate

# Deploy cron jobs
uv run modal deploy scripts/cron.py
```

## Dependency Groups

The project defines four dependency groups in `pyproject.toml`:

| Group | Purpose | When active |
|-------|---------|-------------|
| `dev` | Local development (alembic, modal, python-dotenv, yt-dlp[deno]) | Default — included by `uv sync` |
| `test` | Local testing (pytest, coverage, fakeredis, pytest-mock, pytest-cov) | Default — included by `uv sync` |
| `build` | CI build/deploy (alembic, modal, psycopg2-binary, sqlalchemy) | CI only — explicit `uv sync --group build` |
| `modal` | Modal cron image (redis) | CI only — explicit `uv sync --group modal` |

`default-groups = ["dev", "test"]` in `[tool.uv]` means `uv sync` always installs `dev` and `test`. Do not add `build` or `modal` to local installs.

## Dependency Management

```bash
# Install dependencies (installs dev + test by default)
uv sync

# Add a production dependency
uv add package-name

# Add a development dependency
uv add --group dev package-name

# Update dependencies
uv lock --upgrade
```

## Development Workflow

1. **Setup**: Run `uv sync` to install dependencies
2. **Database**: Run `uv run python scripts/db.py` and `uv run alembic upgrade head`
3. **Configuration**: Copy `.env.example` to `.env` and fill in API keys
4. **Run**: Execute `uv run python src/main.py` to start the bot
5. **Deploy Cron**: Run `uv run modal deploy scripts/cron.py` for rate limit resets

## Rules for AI Agents

### Python Commands

- Use `uv run` for all Python commands
- Do not use bare `python`, `pip`, `poetry`, or `conda`
- Do not invoke `pixi` directly — see note below
- Use `uv add` for adding dependencies, not manual `pyproject.toml` edits
- Keep production dependencies in `[project.dependencies]`; use the appropriate group in `[dependency-groups]` for everything else

### Pixi

`pyproject.toml` contains a `[tool.pixi.*]` workspace config and `pixi.lock` exists. Pixi is configured to manage system-level dependencies that `uv` cannot install from PyPI — specifically `ffmpeg` and `deno`. Do not invoke `pixi` for Python or project work; use `uv` for all of that.

### Database Operations

- Use SQLAlchemy ORM for database operations
- Avoid raw SQL queries unless absolutely necessary
- Create Alembic migrations for all schema changes: `uv run alembic revision --autogenerate`
- Alembic uses `black` internally to format generated migration files — this is expected and intentional
- Test migrations with `uv run alembic upgrade head` before committing
