# Tech Stack

This document lists the technologies used in the AI Summarizer Telegram Bot project. For running commands see `docs/context/uv-guide.md`. For developer tools see `docs/context/tooling-guide.md`.

## Core Technologies

### Language & Runtime

- **Python** - Primary programming language
- **uv** - Fast Python package manager and project manager

### Bot Framework

- **pyTelegramBotAPI** - Telegram Bot API wrapper (synchronous, polling-based)

### AI & ML Services

- **Google Gemini API** - Primary AI model for summarization
- **Replicate** - Alternative AI model hosting (fallback)

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
- **ty** - Type checker
- **pytest** - Test runner
- **python-dotenv** - Environment variable management
- **Modal** - Serverless function deployment for cron jobs

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

## Key Architecture Notes

- **Synchronous, polling-based** bot — no webhooks, no async framework needed
- **Valkey** is Redis-compatible (use Redis protocol / `rush` for rate limiting); chosen over Redis for licensing
- **Gemini** is the primary model; **Replicate** provides model flexibility without code changes
- **PostgreSQL** for user data (persistent), **Valkey** for rate limit counters (ephemeral)
- **Modal** runs cron jobs serverlessly to reset Gemini rate limits without a second container

## Documentation Resources

- [pyTelegramBotAPI](https://pytba.readthedocs.io/en/latest/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Google Gen AI SDK](https://github.com/googleapis/python-genai)
- [uv Documentation](https://docs.astral.sh/uv/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [ty Documentation](https://docs.astral.sh/ty/)
