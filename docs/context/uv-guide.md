# uv Guide

This document explains how to run the project and manage dependencies using `uv`. For the developer tools used in the project, see `docs/context/tooling-guide.md`.

## Package Management

This project uses [uv](https://docs.astral.sh/uv/) as the package manager for fast, reliable Python dependency management.

## Running the Project with uv

All Python commands must be executed through `uv run`:

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

## Dependency Management

```bash
# Install dependencies
uv sync

# Add a new dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

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

- **ALWAYS** use `uv run` prefix for all Python commands
- **NEVER** use bare `python`, `pip`, `pixi`, `poetry`, `conda`, or direct script execution
- Use `uv add` for adding dependencies, not manual `pyproject.toml` edits
- Maintain dependency groups: production dependencies in `[project.dependencies]`, dev tools in `[dependency-groups.dev]`

### Database Operations

- **ALWAYS** use SQLAlchemy ORM for database operations
- **NEVER** write raw SQL queries unless absolutely necessary
- Create Alembic migrations for all schema changes: `uv run alembic revision --autogenerate`
- Test migrations with `uv run alembic upgrade head` before committing
