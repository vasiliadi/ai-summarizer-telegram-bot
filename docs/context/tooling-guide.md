# Tooling Guide

This document explains how to use the project's developer tools and local workflow. For the list of technologies used in the project, see `docs/context/tech-stack.md`.

## Package Management

This project uses [uv](https://github.com/astral-sh/uv) as the package manager for fast, reliable Python dependency management.

### Installation

First, check if uv is already installed:

```bash
uv --version
```

If not installed, install uv using one of these methods:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Using pip
pip install uv

# Using Homebrew (macOS)
brew install uv
```

### Running Python Commands

All Python commands should be executed through `uv run`:

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

### Using `uv tool` for Tooling

Use `uv tool install` to install general-purpose developer tools so the executables are available on your `PATH`. In this project, `ruff`, `ty`, and `pre-commit` should be installed as system-wide tools and run directly after installation.

**Preferred workflow for linting, formatting, hooks, and type checking:**

```bash
# Install once (system-wide executable via uv)
uv tool install ruff
uv tool install ty
uv tool install pre-commit

# Run directly
ruff check .
ruff format .
ty check .
pre-commit run --all-files
```

If one of these tools is missing locally, install it with `uv tool install <tool-name>` before continuing. If a tool should be part of the project's standard workflow, add it to dev dependencies with `uv add --dev` as well (so CI and other contributors have it via the project).

### Dependency Management

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

## Configuration Files

- `pyproject.toml` - Project metadata, dependencies, and tool configuration
- `.env` - Environment variables (API keys, database URLs, etc.)
- `alembic.ini` - Database migration configuration
- `compose.yaml` - Docker Compose configuration
- `Dockerfile` - Container build instructions

## API Keys Required

1. **Telegram Bot Token** - [@BotFather](https://t.me/BotFather)
2. **Gemini API Key** - [Google AI Studio](https://ai.google.dev/)
3. **Replicate API Token** - [Replicate](https://replicate.com/account/api-tokens)
4. **Sentry DSN** - [Sentry](https://sentry.io/signup/)
5. **Modal Token** - [Modal](https://modal.com/)

## Environment Variables

Required variables in `.env`:

```env
TG_API_TOKEN="your_telegram_bot_token"
GEMINI_API_KEY="your_gemini_api_key"
REPLICATE_API_TOKEN="your_replicate_token"
DSN="postgresql+driver://user:password@host:port/database"
REDIS_URL="rediss://default:password@host:port"
SENTRY_DSN="your_sentry_dsn"
PROXY=""
LOG_LEVEL="ERROR"
MODAL_TOKEN_ID="your_modal_token_id"
MODAL_TOKEN_SECRET="your_modal_token_secret"
```

## Development Workflow

1. **Setup**: Install uv and run `uv sync` to install dependencies
2. **Database**: Run `uv run python scripts/db.py` and `uv run alembic upgrade head`
3. **Configuration**: Copy `.env.example` to `.env` and fill in API keys
4. **Run**: Execute `uv run python src/main.py` to start the bot
5. **Deploy Cron**: Run `uv run modal deploy scripts/cron.py` for rate limit resets

## Testing & Quality Assurance

The project uses `pytest` for unit testing and `pytest-cov` for coverage reporting.

### Run tests

```bash
uv run pytest
```

Run tests with `uv run pytest`, and run them before every commit.

### Generate coverage report

```bash
uv run pytest --cov=src --cov-report=term-missing
```

> [!NOTE]
> If you encounter `unrecognized arguments: --cov=src`, ensure `pytest-cov` is installed by running `uv sync` or use `uv run --with pytest-cov pytest --cov=src`.

The HTML report can also be generated:

```bash
uv run pytest --cov=src --cov-report=html
```

The report will be available in the `htmlcov/` directory.

- Linting: `ruff check .` (install via `uv tool install ruff` if missing)
- Formatting: `ruff format .` (install via `uv tool install ruff` if missing)
- Type checking: `ty check .` (install via `uv tool install ty` if missing; using [ty](https://docs.astral.sh/ty/) - modern type checker from Astral)
- Commit hooks: `pre-commit run --all-files` (install via `uv tool install pre-commit` if missing)

## Tooling Rules for AI Agents

### Python Command Rules

- **ALWAYS** use `uv run` prefix for all Python commands
- **NEVER** use bare `python`, `pip`, or direct script execution
- Use `uv add` for adding dependencies, not manual `pyproject.toml` edits
- Maintain dependency groups: production dependencies in `[project.dependencies]`, dev tools in `[dependency-groups.dev]`

### Database Operations

- **ALWAYS** use SQLAlchemy ORM for database operations
- **NEVER** write raw SQL queries unless absolutely necessary
- Create Alembic migrations for all schema changes: `uv run alembic revision --autogenerate`
- Test migrations with `uv run alembic upgrade head` before committing

### Code Quality

- **ALWAYS** install `ruff`, `ty`, and `pre-commit` as system-wide tools with `uv tool install` if they are not already available
- **ALWAYS** run `ruff check .` before every commit
- **ALWAYS** run `ruff format .` before every commit
- **ALWAYS** run `ty check .` before every commit
- **ALWAYS** run `pre-commit run --all-files` before every commit
- `pre-commit` is configured to run automatically on every `git commit`
- Follow Google Python Style Guide for docstrings
- Use type hints for all function signatures

### Testing Strategy

- Write property-based tests for critical business logic
- Test database operations with transactions
- Mock external API calls in tests
- Use `temp/` directory for test artifacts (auto-cleaned)
- **ALWAYS** run tests with `uv run pytest` before every commit

### Dependencies

- Prefer Astral ecosystem tools (`uv`, `ruff`, `ty`) for consistency
- Minimize dependency count - evaluate if new dependencies are truly needed
- Pin major versions, allow minor/patch updates
- Review security advisories for dependencies regularly
