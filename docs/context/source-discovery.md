# Find webpages to summarize

When you have a topic but no URL yet, use [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp)
in Codex CLI to find public webpages and inspect candidate sources. Then send a chosen URL to
your running Telegram bot for a summary in your saved model, language, and prompt strategy.

This is an optional workflow outside the bot. It adds no Telegram command or parsing backend:
the bot still retrieves the URL through the [Exa-to-Tavily flow](../../README.md#webpage-parsing).
Parallel's anonymous endpoint needs no account or API key and uses Fast mode for search. It is
intended for exploration and light use, with rate limits; see the linked service documentation
for higher-volume options.

## Connect Codex

Install and sign in to [Codex CLI](https://developers.openai.com/codex/cli/) first. Merge this
entry into your user configuration at `~/.codex/config.toml` (keep any existing settings):

```toml
[mcp_servers.parallel-search]
url = "https://search.parallel.ai/mcp"
enabled_tools = ["web_search", "web_fetch"]
http_headers = { "User-Agent" = "ai-summarizer-telegram-bot" }
```

If that server name already exists, review its settings before changing it. This user-level
configuration makes the tools available to your Codex sessions; it does not belong in the bot's
`.env` or change the repository's `.codex/config.toml`. Codex still needs its own authentication.
For configuration options, see [Codex MCP setup](https://developers.openai.com/codex/mcp/).

Confirm the entry is loaded:

```bash
codex mcp get parallel-search --json
```

Check that the URL and header match the entry above. Restart Codex, then use `/mcp` to check the
connection and the availability of `web_search` and `web_fetch`. If the tools are missing, check
the configuration syntax and network access to `search.parallel.ai`.

## Find a source and hand off its URL

For example, ask Codex:

```text
Use parallel-search to find the official PostgreSQL documentation explaining logical versus
physical backups. Return up to three public source URLs with a short note about what each
covers. Fetch the most relevant page and check that it contains the backup guidance, rather
than a login, error, or access-denied page. Give me the original page URL to send to my
AI Summarizer Telegram bot.
```

`web_search` returns candidate URLs and excerpts; `web_fetch` helps inspect a selected page.
Review the original source and its date before choosing it. Send one selected webpage URL to
the bot in Telegram. The bot retrieves and summarizes that page independently; search excerpts
are not supplied to the summarizing model, and a successful MCP fetch does not guarantee Exa
or Tavily can retrieve the same page. A page requiring login or a subscription may remain
unavailable to the bot.

Search queries and fetched URLs go to Parallel. Use public topics and public URLs, and keep
private messages, credentials, and signed URLs out of this workflow. If a request hits a service
limit, wait before retrying or follow the service's higher-limit setup; changing the bot's API
keys does not change this separate MCP connection.
