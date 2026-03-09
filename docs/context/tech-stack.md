# Tech Stack

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

## Core Technologies

### Language & Runtime

- **Python** - Primary programming language
- **uv** - Fast Python package manager and project manager

### Bot Framework

- **pyTelegramBotAPI+** - Telegram Bot API wrapper

### AI & ML Services

- **Google Gemini API** - Primary AI model for summarization
- **Replicate** - Alternative AI model hosting

### Database & Caching

- **PostgreSQL 15** - Primary relational database
- **SQLAlchemy 2.0** - ORM and database toolkit
- **Alembic** - Database migration tool
- **Valkey 8.0** (Redis-compatible) - Caching and rate limiting
- **psycopg2-binary** - PostgreSQL adapter

### Media Processing

- **yt-dlp** - YouTube and video platform downloader
- **youtube-transcript-api** - YouTube transcript extraction
- **BeautifulSoup4** - HTML parsing and web scraping

### Utilities

- **Requests** - HTTP library with SOCKS proxy support
- **Tenacity** - Retry logic and error handling
- **telegramify-markdown** - Markdown formatting for Telegram
- **Sentry SDK** - Error tracking and monitoring
- **rush** - Rate limiting with Redis backend

### Development Tools

- **Ruff** - Fast Python linter and formatter
- **python-dotenv** - Environment variable management
- **Modal** - Serverless function deployment for cron jobs

## Infrastructure

### Deployment Options

- **Docker** - Containerized deployment via `Dockerfile` or `compose.yaml`
- **Modal** - Serverless cron jobs for rate limit resets

### Recommended Cloud Services

- **Database**: Supabase (PostgreSQL)
- **Cache**: Aiven for Valkey
- **Hosting**: Railway, or any Docker-compatible platform
- **Monitoring**: Sentry (errors)

## Code Quality

### Linting & Formatting

- **Ruff** - Primary linter with extensive rule set (see `pyproject.toml`)

### Style Guidelines

- **Google Python Style Guide** - Docstring format
- **Conventional Commits** - Commit message format
- **gitmoji** - Commit emoji conventions

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
DB_URL="postgresql+driver://user:password@host:port/database"
REDIS_URL="rediss://default:password@host:port"
SENTRY_DSN="your_sentry_dsn"
PROXY=""
LOG_LEVEL="ERROR"
MODAL_TOKEN_ID="your_modal_token_id"
MODAL_TOKEN_SECRET="your_modal_token_secret"
```

## Project Structure

```
.
├── src/                    # Main application code
│   ├── main.py            # Bot entry point and command handlers
│   ├── config.py          # Configuration and settings
│   ├── database.py        # Database operations
│   ├── handlers.py        # Message type handlers
│   ├── services.py        # Business logic services
│   ├── models.py          # SQLAlchemy models
│   ├── prompts.py         # AI prompt templates
│   ├── transcription.py   # Audio transcription logic
│   ├── summary.py         # Summarization logic
│   ├── download.py        # Media download utilities
│   ├── utils.py           # Helper functions
│   └── exceptions.py      # Custom exceptions
├── migrations/            # Alembic database migrations
├── scripts/               # Utility scripts
│   ├── db.py             # Database initialization
│   └── cron.py           # Modal cron jobs
├── docs/                  # Documentation
├── pyproject.toml        # Project configuration
├── alembic.ini           # Migration configuration
├── Dockerfile            # Container definition
└── compose.yaml          # Docker Compose setup
```

## Development Workflow

1. **Setup**: Install uv and run `uv sync` to install dependencies
2. **Database**: Run `uv run python scripts/db.py` and `uv run alembic upgrade head`
3. **Configuration**: Copy `.env.example` to `.env` and fill in API keys
4. **Run**: Execute `uv run python src/main.py` to start the bot
5. **Deploy Cron**: Run `uv run modal deploy scripts/cron.py` for rate limit resets

## Testing & Quality Assurance

- Linting: `uv run ruff check .`
- Formatting: `uv run ruff format .`
- Type checking: `uv run ty check .` (using [ty](https://docs.astral.sh/ty/) - modern type checker from Astral)

## Documentation Resources

- [pyTelegramBotAPI](https://pytba.readthedocs.io/en/latest/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Google Gen AI SDK](https://github.com/googleapis/python-genai)
- [uv Documentation](https://docs.astral.sh/uv/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [ty Documentation](https://docs.astral.sh/ty/)

## Architecture Decisions

### General Principles for AI Agents

When working on this project, AI agents must follow these architectural principles:

#### 1. Package Management

- **ALWAYS** use `uv run` prefix for all Python commands
- **NEVER** use bare `python`, `pip`, or direct script execution
- Use `uv add` for adding dependencies, not manual `pyproject.toml` edits
- Maintain dependency groups: production dependencies in `[project.dependencies]`, dev tools in `[dependency-groups.dev]`

#### 2. Database Operations

- **ALWAYS** use SQLAlchemy ORM for database operations
- **NEVER** write raw SQL queries unless absolutely necessary
- Create Alembic migrations for all schema changes: `uv run alembic revision --autogenerate`
- Test migrations with `uv run alembic upgrade head` before committing

#### 3. Code Quality

- **ALWAYS** run `uv run ruff check .` before committing code
- **ALWAYS** run `uv run ruff format .` to format code
- Use `uv run ty check .` for type checking
- Follow Google Python Style Guide for docstrings
- Use type hints for all function signatures

#### 4. Error Handling

- **ALWAYS** use Sentry's `capture_exception()` for error tracking
- Use Tenacity's retry decorators for external API calls
- Implement proper error messages for users (no stack traces in bot responses)
- Log errors with appropriate levels (ERROR, WARNING, INFO, DEBUG)

#### 5. Configuration

- **NEVER** hardcode API keys, tokens, or sensitive data
- **ALWAYS** use environment variables via `.env` file
- Use `config.py` for application configuration
- Document all required environment variables

#### 6. Bot Development

- Keep command handlers in `src/main.py`
- Keep business logic in `src/handlers.py` and `src/services.py`
- Use `check_auth()` decorator for protected commands
- Implement rate limiting for all user-facing operations

#### 7. AI Model Integration

- Default to Google Gemini API for summarization
- Implement fallback to Replicate when Gemini fails
- Respect rate limits using Redis-backed rush library
- Cache responses when appropriate to reduce API costs

#### 8. Testing Strategy

- Write property-based tests for critical business logic
- Test database operations with transactions
- Mock external API calls in tests
- Use `temp/` directory for test artifacts (auto-cleaned)

#### 9. Deployment

- **ALWAYS** test Docker builds locally before deploying
- Use `compose.yaml` for local development with dependencies
- Deploy Modal cron jobs separately: `uv run modal deploy scripts/cron.py`
- Verify environment variables are set in production

#### 10. Dependencies

- Prefer Astral ecosystem tools (uv, ruff, ty) for consistency
- Minimize dependency count - evaluate if new dependencies are truly needed
- Pin major versions, allow minor/patch updates
- Review security advisories for dependencies regularly

#### 11. File Organization

- Source code in `src/`
- Database migrations in `migrations/`
- Utility scripts in `scripts/`
- Documentation in `docs/`
- Temporary files in `temp/` (gitignored)

#### 12. Commit Standards

- Use Conventional Commits format
- Use gitmoji for commit prefixes
- Write clear, descriptive commit messages
- Reference issues/PRs when applicable

### Technology-Specific Decisions

#### Why uv as Package Manager?

**Decision**: Use uv instead of pip/poetry/pipenv

**Rationale**:

- 10-100x faster than pip for dependency resolution and installation
- Built-in virtual environment management
- Compatible with standard Python packaging (pyproject.toml)
- Single tool for dependency management, virtual environments, and script running
- Developed by Astral (same team as Ruff), ensuring ecosystem compatibility
- Native support for lockfiles and reproducible builds

### Why Telegram Bot API?

**Decision**: Use pyTelegramBotAPI for bot framework

**Rationale**:

- Lightweight and straightforward API wrapper
- Synchronous design fits the application's polling-based architecture
- Well-documented with active community support
- Minimal overhead compared to async frameworks (python-telegram-bot)
- Sufficient for the bot's use case (no need for webhooks or complex async patterns)

### Why Google Gemini as Primary AI Model?

**Decision**: Use Google Gemini API with Replicate as fallback

**Rationale**:

- Gemini offers competitive pricing and performance for summarization tasks
- Native support for multimodal inputs (text, audio, video)
- Generous free tier for development and testing
- Replicate provides flexibility to switch models without code changes
- Rate limiting handled at application level with Redis

### Why PostgreSQL + Valkey (Redis)?

**Decision**: PostgreSQL for persistent storage, Valkey for caching/rate limiting

**Rationale**:

- PostgreSQL: Robust relational database with excellent SQLAlchemy support
- Valkey: Redis-compatible, open-source alternative with better licensing
- Clear separation of concerns: PostgreSQL for user data, Valkey for ephemeral data
- Both have excellent managed service options (Supabase, Aiven)
- Redis protocol for rate limiting (rush library) and caching

### Why SQLAlchemy 2.0?

**Decision**: Use SQLAlchemy 2.0 ORM with Alembic migrations

**Rationale**:

- Type-safe ORM with modern Python syntax
- Alembic provides robust schema migration management
- Excellent PostgreSQL support with advanced features
- Clear separation between models and database operations
- Version 2.0 brings improved performance and better typing

### Why Ruff for Linting?

**Decision**: Use Ruff as primary linter and formatter, replacing Black, isort, flake8, etc.

**Rationale**:

- 10-100x faster than traditional Python linters
- Replaces multiple tools (Black, isort, flake8, pylint) with single tool
- Extensive rule set covering code quality, security, and style
- Built in Rust for performance
- Compatible with existing Python tooling and CI/CD pipelines
- Same ecosystem as uv and ty (Astral)

### Why Modal for Cron Jobs?

**Decision**: Use Modal for serverless cron jobs instead of traditional cron

**Rationale**:

- Serverless execution reduces infrastructure overhead
- No need to maintain separate server for periodic tasks
- Pay-per-execution pricing model
- Easy deployment and monitoring
- Handles rate limit resets without impacting main bot process

### Why Docker for Deployment?

**Decision**: Containerize application with Docker

**Rationale**:

- Consistent environment across development and production
- Easy deployment to any cloud platform
- Isolation from host system dependencies
- Simple scaling and orchestration options
- Standard approach for Python applications

### Why Sentry for Error Tracking?

**Decision**: Use Sentry SDK for error monitoring

**Rationale**:

- Real-time error tracking and alerting
- Detailed stack traces and context
- Integration with Telegram bot framework
- Free tier sufficient for small to medium deployments
- Better than log-based debugging for production issues
