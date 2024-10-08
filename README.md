# AI Summarizer - telegram bot

![Python](https://img.shields.io/badge/Python-3.11_|_3.12-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)

## Usage

1. Get API keys: [@BotFather](https://t.me/BotFather), [Gemini](https://ai.google.dev/), and [Replicate](https://replicate.com/account/api-tokens)
2. Setup DB, for example [Supabase x Postgres](https://supabase.com/database)
3. Edit `.env`
4. Run `python main.py`

After `/start`, you need to set approved to `True` for wanted user IDs. Depending on your database, you can use [SQL Editor](https://supabase.com/docs/guides/database/overview) for [Supabase x Postgres](https://supabase.com/database) or any other SQL client for another database.

Example of `.env` file:

```text
TG_API_TOKEN = "your_api_key"
GEMINI_API_KEY = "your_api_key"
REPLICATE_API_TOKEN = "your_api_key"
DB_URL = "postgresql+driver://user:password@host:port/database"
PROXY = ""
```

Pass in an empty string to `PROXY` for direct connection. \
Or use `schema`://`username`:`password`@`proxy_address`:`port` \
For example `http://user:password@proxy.com:1234`

Don't forget to enabble `RLS` if you use [Supabase x Postgres](https://supabase.com/database).

After completing these steps, you are ready to send youtube.com and castro.fm links to the bot and receive summary.

## Deploy

- Using `Dockerfile` on any cloud hosting
- Using [Dokploy](https://dokploy.com/) or a similar tool and a cost-efficient cloud service like [Hetzner](https://www.hetzner.com/cloud/)

## Docs

[pyTelegramBotAPI](https://pytba.readthedocs.io/en/latest/) \
[SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/contents.html)

[Telegram Bot API](https://core.telegram.org/bots/api)

## Cloud DBs

[PostgreSQL on Render](https://docs.render.com/databases) \
[Supabase x Postgres](https://supabase.com/database) \
[EdgeDB Cloud](https://www.edgedb.com/)

## SQL Clients

[TablePlus](https://tableplus.com/) \
[DBeaver Community](https://dbeaver.io/) \
[Valentina Studio](https://www.valentina-db.com/en/valentina-studio-overview)

## Easy deploy

[Coolify](https://coolify.io/) \
[Appliku](https://appliku.com/) \
[CapRover](https://caprover.com/) \
[Dokku](https://dokku.com/)

## Known issues

- Markdown

> Maybe [aiogram's](https://docs.aiogram.dev/en/dev-3.x/) built-in parsers are better.

- File object not in class
- Weak error handling
