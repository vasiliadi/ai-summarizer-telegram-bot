# AI Summarizer - telegram bot

![Python](https://img.shields.io/badge/Python-3.12-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/e215a12081084eed95c60e5e80480218)](https://app.codacy.com/gh/vasiliadi/ai-summarizer-telegram-bot/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fvasiliadi%2Fai-summarizer-telegram-bot.svg?type=shield&issueType=license)](https://app.fossa.com/projects/git%2Bgithub.com%2Fvasiliadi%2Fai-summarizer-telegram-bot?ref=badge_shield&issueType=license)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Usage

1. Get API keys: [@BotFather](https://t.me/BotFather), [Gemini](https://ai.google.dev/), [Replicate](https://replicate.com/account/api-tokens), [Perplexity](https://docs.perplexity.ai/guides/getting-started), [Sentry](https://sentry.io/signup/)
2. Setup DB and Redis. For example [Supabase x Postgres](https://supabase.com/database) and [Aiven for Valkey](https://aiven.io/free-redis-database)
3. Edit `.env`
4. Apply [migrations](#migrations). Or run `Dockerfile` or `compose.yaml`
5. Run `python main.py` if you don't use Docker

After `/start`, you need to set approved to `True` for wanted user IDs. Depending on your database, you can use [SQL Editor](https://supabase.com/docs/guides/database/overview) for [Supabase x Postgres](https://supabase.com/database) or any other SQL client for another database.

Example of `.env` file:

```text
TG_API_TOKEN="your_api_key"
GEMINI_API_KEY="your_api_key"
REPLICATE_API_TOKEN="your_api_key"
PERPLEXITY_API_KEY="your_api_key"
DB_URL="postgresql+driver://user:password@host:port/database"
REDIS_URL=""
SENTRY_DSN="your_sentry_dsn"
PROXY=""
WEB_SCRAPE_PROXY=""
LOG_LEVEL="ERROR"
```

Pass in an empty string to `PROXY` for direct connection. \
Or use `schema`://`username`:`password`@`proxy_address`:`port` \
For example `http://user:password@proxy.com:1234`

Don't forget to enabble `RLS` if you use [Supabase x Postgres](https://supabase.com/database).

After completing these steps, you are ready to send youtube.com and castro.fm links to the bot and receive summary.

## List of commands for @BotFather

```text
toggle_transcription - Toggle transcription for summary (fallback on failure)
toggle_yt_transcription - Toggle YouTube transcription
toggle_translation - Toggle translator
set_target_language - Choose which language you want to translate into
set_parsing_strategy - Select the strategy to use to parse the webpage
```

## Deploy

- Using `Dockerfile` on any cloud hosting
- Using [Dokploy](https://dokploy.com/) or a similar tool and a cost-efficient cloud service like [Hetzner](https://www.hetzner.com/cloud/)

### For development

#### Migrations

Apply migrations before first run. Or use `Dockerfile`.

```text
python db.py
alembic upgrade head
```

#### JavaScript rendering

Many websites have protections against bots, and some content requires JavaScript to be rendered for visibility. To enable JavaScript rendering, I am using [Selenium WebDriver](https://www.selenium.dev/documentation/webdriver/), which requires the Chrome browser and ChromeDriver to be installed on the operating system.

`Selenium WebDriver` supports only proxy without authorization. For authorized access, use a local proxy server such as [tinyproxy](https://github.com/tinyproxy/tinyproxy) or [pproxy](https://github.com/qwj/python-proxy), or any other proxy server.

Another approach (by default) is to use a special proxy. This approach requiring special proxy (`WEB_SCRAPE_PROXY`) solutions for web scraping, such as [ScrapingBee](https://www.scrapingbee.com/), [ScrapingAnt](https://scrapingant.com/), [WebScrapingAPI](https://www.webscrapingapi.com/), [scraperapi](https://www.scraperapi.com/), or others.

## Docs

[pyTelegramBotAPI](https://pytba.readthedocs.io/en/latest/) \
[SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/contents.html) \
[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html) \
[Google AI Python SDK](https://github.com/google-gemini/generative-ai-python) \
[Requests](https://requests.readthedocs.io/en/latest/) \
[yt-dlp](https://github.com/yt-dlp/yt-dlp) \
[beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) \
[Replicate](https://github.com/replicate/replicate-python) \
[telegramify_markdown](https://github.com/sudoskys/telegramify-markdown) \
[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) \
[Tenacity](https://tenacity.readthedocs.io/en/latest/) \
[Sentry](https://docs.sentry.io/platforms/python/) \
[SeleniumBase](https://seleniumbase.io/) \
[rush](https://rush.readthedocs.io/en/latest/) \
[OpenAI](https://github.com/openai/openai-python) \
[Loguru](https://loguru.readthedocs.io/en/stable/index.html)

[Telegram Bot API](https://core.telegram.org/bots/api) \
[Docker | Set build-time variables (--build-arg)](https://docs.docker.com/reference/cli/docker/buildx/build/#build-arg) \
[Logging Levels](https://docs.python.org/3/library/logging.html#logging-levels)

## Cloud DBs

PostgreSQL: [PostgreSQL on Render](https://docs.render.com/databases), [Supabase x Postgres](https://supabase.com/database), [EdgeDB Cloud](https://www.edgedb.com/) \
Redis: [Redis.io](https://redis.io/), [Upstash x Redis](https://upstash.com/), [Aiven for Valkey](https://aiven.io/free-redis-database)

## SQL Clients

[TablePlus](https://tableplus.com/), [DBeaver Community](https://dbeaver.io/), [Valentina Studio](https://www.valentina-db.com/en/valentina-studio-overview)

## Linters and Checkers

[isort](https://pycqa.github.io/isort/), [black](https://github.com/psf/black), [mypy](https://mypy-lang.org/), [pylint](https://pylint.readthedocs.io/en/latest/), [ruff](https://github.com/astral-sh/ruff)

### Error suppression

[ruff](https://docs.astral.sh/ruff/linter/#error-suppression), [pylint](https://pylint.pycqa.org/en/latest/user_guide/messages/message_control.html#block-disables)

## Easy deploy

[Coolify](https://coolify.io/), [Appliku](https://appliku.com/), [CapRover](https://caprover.com/), [Dokku](https://dokku.com/)

## Conventional Commits

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) \
[Conventional Commits cheatsheet](https://cheatsheets.zip/conventional-commits) \
[gitmoji](https://gitmoji.dev/)

## Logs

[Logtail](https://logs.betterstack.com/), [Papertrail](https://papertrailapp.com/)

## Possible improvements

- Another model, [Claude 3.5 Sonnet](https://docs.anthropic.com/en/docs/about-claude/models), produces the same output as 8,192 tokens but with only 200k inputs. Or [GPT-4o](https://platform.openai.com/docs/models#gpt-4o) with 16,384 output and 128k input. Prices for [Claude 3.5 Sonnet](https://www.anthropic.com/pricing#anthropic-api) and [GPT-4o](https://openai.com/api/pricing/).
- [Modal](https://modal.com/docs/guide/custom-container) for ffmpeg.
