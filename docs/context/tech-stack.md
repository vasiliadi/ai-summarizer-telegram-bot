# Tech Stack

This document lists the technologies used in the AI Summarizer Telegram Bot project. For command usage, developer workflow, and tool-specific setup, see `docs/context/tooling-guide.md`.

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
- **pytest** - Test runner
- **pytest-cov** - Coverage reporting
- **ty** - Type checker

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

## Infrastructure

### Deployment Options

- **Docker** - Containerized deployment via `Dockerfile` or `compose.yaml`
- **Modal** - Serverless cron jobs for rate limit resets

### Recommended Cloud Services

- **Database**: Supabase (PostgreSQL)
- **Cache**: Aiven for Valkey
- **Hosting**: Railway, or any Docker-compatible platform
- **Monitoring**: Sentry (errors)

## Documentation Resources

- [pyTelegramBotAPI](https://pytba.readthedocs.io/en/latest/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Google Gen AI SDK](https://github.com/googleapis/python-genai)
- [uv Documentation](https://docs.astral.sh/uv/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [ty Documentation](https://docs.astral.sh/ty/)

## Technology-Specific Decisions

### Why uv as Package Manager?

**Decision**: Use uv instead of pip/poetry/pipenv

**Rationale**:

- 10-100x faster than pip for dependency resolution and installation
- Built-in virtual environment management
- Compatible with standard Python packaging (`pyproject.toml`)
- Single tool for dependency management, virtual environments, and script running
- Developed by Astral (same team as Ruff), ensuring ecosystem compatibility
- Native support for lockfiles and reproducible builds

### Why Telegram Bot API?

**Decision**: Use pyTelegramBotAPI for bot framework

**Rationale**:

- Lightweight and straightforward API wrapper
- Synchronous design fits the application's polling-based architecture
- Well-documented with active community support
- Minimal overhead compared to async frameworks (`python-telegram-bot`)
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
- Redis protocol for rate limiting (`rush`) and caching

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
