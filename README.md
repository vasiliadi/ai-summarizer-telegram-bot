# AI Summarizer - telegram bot

![Python](https://img.shields.io/badge/Python-3.14-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Valkey](https://img.shields.io/badge/Valkey-9-blue)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/e215a12081084eed95c60e5e80480218)](https://app.codacy.com/gh/vasiliadi/ai-summarizer-telegram-bot/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![codecov](https://codecov.io/github/vasiliadi/ai-summarizer-telegram-bot/graph/badge.svg?token=JLUAET14RE)](https://codecov.io/github/vasiliadi/ai-summarizer-telegram-bot)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fvasiliadi%2Fai-summarizer-telegram-bot.svg?type=shield&issueType=license)](https://app.fossa.com/projects/git%2Bgithub.com%2Fvasiliadi%2Fai-summarizer-telegram-bot?ref=badge_shield&issueType=license)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![Pixi](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json&style=flat-square)](https://pixi.sh)

## About

A bot designed to summarize YouTube videos (via audio or transcripts), Castro.fm podcasts, and various Telegram content, including voice messages, videos, and files (PDF, RTF, CSV, etc.).

## Usage

### General settings

1. Get API keys: [@BotFather](https://t.me/BotFather), [Gemini](https://ai.google.dev/), [Replicate](https://replicate.com/account/api-tokens), [Sentry](https://sentry.io/signup/), [Modal](https://modal.com/), [Tavily](https://app.tavily.com/), [Exa](https://dashboard.exa.ai/)
2. Setup DB and Redis. For example [Supabase x Postgres](https://supabase.com/database) and [Aiven for Valkey](https://aiven.io/free-redis-database)
3. Edit `.env`
4. Set up the [Modal Secrets](https://modal.com/secrets) with name `resetlimit-secrets`. Only `REDIS_URL` from `.env` needed.

### Dockerfile

Run `Dockerfile` or `compose.yaml`

### Without docker

1. Apply [migrations](#migrations).
2. Run `uv run python src/main.py`
3. To reset daily rate limit you must run `uv run modal deploy scripts/cron.py`. Otherwise, the daily limit may become inaccurate.

### After start

After `/start`, you need to set approved to `True` for wanted user IDs and set a daily limit (default is 0). Depending on your database, you can use [SQL Editor](https://supabase.com/docs/guides/database/overview) for [Supabase x Postgres](https://supabase.com/database) or any other SQL client for another database.

## .env

Example of `.env` file:

```env
TG_API_TOKEN="your_api_key"
GEMINI_API_KEY="your_api_key"
REPLICATE_API_TOKEN="your_api_key"
TAVILY_API_KEY="your_api_key"
EXA_API_KEY="your_api_key"
DSN="postgresql+driver://user:password@host:port/database"
REDIS_URL="rediss://default:password@host:port"
SENTRY_DSN="your_sentry_dsn"
PROXY=""
LOG_LEVEL="ERROR"
DEFAULT_PARSING_BACKEND="tavily"
MODAL_TOKEN_ID="your_token"
MODAL_TOKEN_SECRET="your_token_secret"
```

Pass in an empty string to `PROXY` for direct connection. \
Or use `schema`://`username`:`password`@`proxy_address`:`port` \
For example `https://user:password@proxy.com:1234`

Multiple proxies can be supplied as a comma-separated list; one is picked at random per request to mitigate IP blocking. Whitespace around entries is trimmed.

Only HTTP/HTTPS proxies are supported. The last version with SOCKS proxy support is [0.13.0](https://github.com/vasiliadi/ai-summarizer-telegram-bot/releases/tag/0.13.0).

```env
PROXY="https://user:password@proxy.com:1234,https://user:password@proxy.com:1235"
```

Don't forget to enable `RLS` if you use [Supabase x Postgres](https://supabase.com/database).

After completing these steps, you are ready to send youtube.com and castro.fm links to the bot and receive summary.

## List of commands for BotFather

```text
set_summarizing_model - Choose which model you want to use for summary
set_prompt_strategy - Choose which prompt strategy to use for summary
toggle_transcription - Toggle transcription for summary (fallback on failure)
toggle_yt_transcription - Toggle YouTube transcription
set_thinking_level - Choose AI thinking level
set_target_language - Choose which language you want to translate into
myinfo - Show my settings
```

## Deploy

- Using `Dockerfile` on any cloud hosting
- Using [Dokploy](https://dokploy.com/) or a similar tool and a cost-efficient cloud service like [Hetzner](https://www.hetzner.com/cloud/)

### For development

#### Migrations

Apply migrations before first run.

```bash
uv run python scripts/db.py
uv run alembic upgrade head
```

For developers, how to generate a migration.

```bash
uv run alembic revision --autogenerate
```

#### Developer tools

Install [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Homebrew (macOS)
brew install uv
```

Optionally, install [pixi](https://pixi.sh) for local development when `ffmpeg` is required:

```bash
# macOS/Linux
curl -fsSL https://pixi.sh/install.sh | sh

# Homebrew (macOS)
brew install pixi
```

```bash
pixi run start  # ffmpeg available
```

Install `ruff` and `ty` as system-wide tools or use `uvx`:

```bash
uv tool install ruff
uv tool install ty
```

To upgrade all installed tools to their latest versions:

```bash
uv tool upgrade --all
```

Optionally, install [direnv](https://direnv.net/) to automatically load `.env` when entering the project directory:

```bash
brew install direnv
```

#### Git hooks

Install `pre-commit`.

```bash
uv tool install pre-commit
```

Install pre-commit hooks.

```bash
pre-commit install
pre-commit install --hook-type post-merge
pre-commit install --hook-type post-checkout
pre-commit install --hook-type post-rewrite
```

#### Webpage parsing

Webpage URLs are parsed into clean text before being passed to Gemini. This gives every model version identical, well-structured input and removes the variability introduced by Gemini's server-side `UrlContext` tool.

The parsing backend is pluggable and selected via the `DEFAULT_PARSING_BACKEND` env var (defaults to `tavily`):

- `tavily` — [Tavily](https://tavily.com)
- `exa` — [Exa.ai](https://exa.ai)

#### Remote functions

To avoid multiple docker images, I use a [Modal](https://modal.com/) for cron jobs to reset the Gemini rate limit. [Modal Secrets](https://modal.com/docs/guide/secrets) should include `REDIS_URL`.

Modal Image Builder Version required to be `2025.06`. Set in Settings -> Image Builder Version.

## Audio vs Text Summaries (AI answer)

There are a few reasons why providing an audio file might lead to a more detailed and comprehensive summary compared to a text transcript:

1. **Contextual Understanding:** When processing audio, I can leverage the nuances of speech, such as intonation, emphasis, and pauses, to better understand the speaker's intent and the overall context of the conversation. This contextual understanding helps me identify the main points and supporting arguments more accurately.

2. **Speaker Identification and Role:** In audio files, I can often distinguish between different speakers and their roles in the conversation. This allows me to attribute specific statements and opinions to the correct individuals, which can be crucial for understanding the dynamics of the discussion.

3. **Non-verbal Cues:** While text transcripts provide the words spoken, they lack the non-verbal cues that often accompany speech, such as laughter, sighs, or changes in tone. These cues can convey additional information and emotions that can significantly impact the overall meaning of the conversation.

4. **Advanced Audio Processing Techniques:** My underlying technology can analyze audio files for various features, including speaker identification, sentiment analysis, and topic modeling. These techniques can help me identify key points, summarize the content, and even extract specific information, such as names, dates, or locations.

While text transcripts can provide a solid foundation for understanding the content, they lack the richness and depth of information that can be gleaned from audio files. By incorporating advanced audio processing techniques and considering the broader context of the conversation, I can provide more detailed and insightful summaries when working with audio files.

## Docs

[pyTelegramBotAPI](https://pytba.readthedocs.io/en/latest/) \
[SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/contents.html) \
[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html) \
[Google Gen AI SDK](https://github.com/googleapis/python-genai) \
[yt-dlp](https://github.com/yt-dlp/yt-dlp) \
[beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) \
[Replicate](https://github.com/replicate/replicate-python) \
[telegramify_markdown](https://github.com/sudoskys/telegramify-markdown) \
[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) \
[Tenacity](https://tenacity.readthedocs.io/en/latest/) \
[Sentry](https://docs.sentry.io/platforms/python/) \
[limits](https://github.com/alisaifee/limits) \
[tavily-python](https://docs.tavily.com/welcome) \
[exa-py](https://github.com/exa-labs/exa-py) \
[curl_cffi](https://github.com/lexiforest/curl_cffi)

[Telegram Bot API](https://core.telegram.org/bots/api) \
[Docker | Set build-time variables (--build-arg)](https://docs.docker.com/reference/cli/docker/buildx/build/#build-arg) \
[Logging Levels](https://docs.python.org/3/library/logging.html#logging-levels), [LogRecord attributes](https://docs.python.org/3/library/logging.html#logrecord-attributes) \
[Google Python Style Guide | Docstrings](https://google.github.io/styleguide/pyguide.html#s3.8.1-comments-in-doc-strings) \
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), [Conventional Commits cheatsheet](https://cheatsheets.zip/conventional-commits), [gitmoji](https://gitmoji.dev/), [Stop Using Conventional Commits](https://sumnerevans.com/posts/software-engineering/stop-using-conventional-commits/) \
[Renovate bot](https://docs.renovatebot.com/), [Renovate Configuration Options](https://docs.renovatebot.com/configuration-options/) \
[crontab guru](https://crontab.guru/) \
[Gemini API Cookbook](https://github.com/google-gemini/cookbook/) \
Uptime stats: [Gemini Models](https://openrouter.ai/google) \
[AI Agent Framework](https://github.com/Poorna-Repos/claude-context-survival-kit), [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices)

### Cloud DBs

PostgreSQL: [PostgreSQL on Render](https://docs.render.com/databases), [Supabase x Postgres](https://supabase.com/database), [EdgeDB Cloud](https://www.edgedb.com/) \
Redis: [Redis.io](https://redis.io/), [Upstash x Redis](https://upstash.com/), [Aiven for Valkey](https://aiven.io/free-redis-database)

### SQL Clients

[TablePlus](https://tableplus.com/), [DBeaver Community](https://dbeaver.io/), [Valentina Studio](https://www.valentina-db.com/en/valentina-studio-overview)

### Linters and Checkers

[black](https://github.com/psf/black), [ruff](https://github.com/astral-sh/ruff), [ty](https://docs.astral.sh/ty/), [pyrefly](https://pyrefly.org/)

#### Error suppression

[ruff error suppression](https://docs.astral.sh/ruff/linter/#error-suppression) and [ruff block-level](https://docs.astral.sh/ruff/linter/#block-level), [ty](https://docs.astral.sh/ty/suppression/), [pyrefly](https://pyrefly.org/en/docs/error-suppressions/)

### Easy deploy

[Coolify](https://coolify.io/), [Appliku](https://appliku.com/), [CapRover](https://caprover.com/), [Dokku](https://dokku.com/)

### Logs

[Logtail](https://logs.betterstack.com/), [Papertrail](https://papertrailapp.com/)

## Possible improvements

- [Gitflow workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow).
- [NumPy Docstrings Style Guide | Docstrings](https://numpydoc.readthedocs.io/en/latest/format.html).
- Frontend to configure access.
