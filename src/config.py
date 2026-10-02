import logging
import os
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

import sentry_sdk
import telebot
from exa_py import Exa
from google import genai
from langfuse import Langfuse
from limits import parse as parse_rate_limit
from limits.storage import RedisStorage
from limits.strategies import FixedWindowRateLimiter
from pydantic_ai import Agent
from pydantic_ai.providers.openrouter import OpenRouterProvider
from sentry_sdk.integrations.logging import LoggingIntegration
from tavily import TavilyClient

if os.environ.get("ENV") != "PROD":
    from dotenv import load_dotenv

    load_dotenv()


# Sentry.io config
# See architecture.md → *Sentry log collection is an explicit opt-in*.
sentry_sdk.init(
    dsn=os.environ["SENTRY_DSN"],
    integrations=[LoggingIntegration(capture_sentry_logs=True)],
)

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "ERROR").upper()
NUMERIC_LOG_LEVEL = logging.getLevelNamesMapping().get(LOG_LEVEL, logging.ERROR)
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Ensure root logger is configured for all modules, not just telebot.
logging.basicConfig(
    level=NUMERIC_LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
telebot.logger.setLevel(NUMERIC_LOG_LEVEL)


# DB
DSN = os.environ["DSN"]
REDIS_URL = os.environ["REDIS_URL"]
RATE_LIMITER_URL = f"{REDIS_URL}/0"


# Proxy
PROXIES: list[str] = [
    p.strip() for p in os.environ.get("PROXY", "").split(",") if p.strip()
]


# Telegram bot config
TG_API_TOKEN = os.environ["TG_API_TOKEN"]
bot = telebot.TeleBot(token=TG_API_TOKEN, disable_web_page_preview=True)


# Gemini config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# OpenRouter config
# Hardcoded, not read from env. See architecture.md →
# *OpenRouter calls identify the app*.
OPENROUTER_APP_URL = "https://github.com/vasiliadi/ai-summarizer-telegram-bot"
OPENROUTER_APP_TITLE = "ai-summarizer-telegram-bot"
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
# A factory, not a provider: `LLMClient` builds one per thread. See
# architecture.md → *One OpenRouter provider per thread*.
openrouter_provider_factory = partial(
    OpenRouterProvider,
    api_key=OPENROUTER_API_KEY,
    app_url=OPENROUTER_APP_URL,
    app_title=OPENROUTER_APP_TITLE,
)
# JEV is a decisions model, not a chat model: OpenRouter serves it only on this
# endpoint, which pydantic-ai does not speak (see parsing.BlockedPageDetector).
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
BLOCK_DETECTOR_MODEL_ID = "~typesafe/jev-latest"


# Summarizing model registry
@dataclass(frozen=True)
class ModelSpec:
    """A selectable summarizing model: its label, provider, and input modalities.

    The flags say what this bot can deliver, not what the model's catalog
    advertises; see architecture.md → *Modality routing*.
    """

    label: str
    provider: Literal["google", "openrouter"]
    supports_audio: bool
    supports_files: bool


MODEL_SPECS: dict[str, ModelSpec] = {
    "deepseek/deepseek-v4.1-flash": ModelSpec(
        label="DeepSeek V4.1 Flash",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
    "gemini-3.8-flash": ModelSpec(
        label="Gemini 3.8 Flash",
        provider="google",
        supports_audio=True,
        supports_files=True,
    ),
    "openai/gpt-6-luna": ModelSpec(
        label="GPT-6 Luna",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
    "x-ai/grok-4.7": ModelSpec(
        label="Grok 4.7",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
}
MODEL_LABELS: dict[str, str] = {k: v.label for k, v in MODEL_SPECS.items()}
MODEL_LABELS_REVERSE: dict[str, str] = {v: k for k, v in MODEL_LABELS.items()}
ALLOWED_MODELS_FOR_SUMMARY = list(MODEL_SPECS.keys())
# If you change DEFAULT_MODEL_ID_FOR_SUMMARY, also change it in models.py.
# It must keep supports_files=True: see architecture.md → *Modality routing*.
DEFAULT_MODEL_ID_FOR_SUMMARY = "gemini-3.8-flash"
DEFAULT_THINKING_LEVEL = "medium"
# Keys are pydantic-ai's `ThinkingEffort`, untranslated here; values are only the
# keyboard's button text, in the order shown (low to high).
THINKING_LEVEL_LABELS: dict[str, str] = {
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Extra High",
}
THINKING_LEVEL_LABELS_REVERSE: dict[str, str] = {
    v: k for k, v in THINKING_LEVEL_LABELS.items()
}
ALLOWED_THINKING_LEVELS = list(THINKING_LEVEL_LABELS.keys())


# Langfuse config
# Optional, so local runs and tests work without it. See architecture.md →
# *Tracing (optional), text input only*.
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY")
LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL")
langfuse_client: Langfuse | None = None
if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
    langfuse_client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        base_url=LANGFUSE_BASE_URL,
    )
    Agent.instrument_all()


# Prompts
# If you change DEFAULT_PROMPT_KEY, also change it in models.py.
DEFAULT_PROMPT_KEY = "basic_prompt_for_transcript"
PROMPT_STRATEGY_LABELS: dict[str, str] = {
    "basic_prompt_for_transcript": "Detailed Summary",
    "key_points_for_transcript": "Key Points",
}
PROMPT_STRATEGY_LABELS_REVERSE: dict[str, str] = {
    v: k for k, v in PROMPT_STRATEGY_LABELS.items()
}
ALLOWED_PROMPT_KEYS = list(PROMPT_STRATEGY_LABELS.keys())


# Replicate.com config
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]


# Tavily config
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)


# Exa.ai config
EXA_API_KEY = os.environ["EXA_API_KEY"]
exa_client = Exa(api_key=EXA_API_KEY)


# Rate limits
MINUTE_LIMIT_KEY = "RPM"
DAILY_LIMIT_KEY = "RPD"
MINUTE_LIMIT = 5
rate_limiter = FixedWindowRateLimiter(RedisStorage(RATE_LIMITER_URL))
per_minute_rate = parse_rate_limit(f"{MINUTE_LIMIT} per minute")


# Telegram bot API caps incoming-file downloads at 20MB.
# https://core.telegram.org/bots/api#getfile
TG_MAX_FILE_SIZE = 20 * 1024 * 1024


# MIME types accepted by /document handler.
SUPPORTED_DOCUMENT_MIME_TYPES = (
    "application/pdf",
    "text/plain",
    "application/rtf",
    "text/csv",
    "audio/ogg",
)


# YouTube host allow-list for URL routing.
YT_HOSTS = frozenset({"youtu.be", "youtube.com"})
CASTRO_HOST = "castro.fm"


# For cleanup: snapshot of files present at startup; treated as do-not-delete.
# In PROD the container's working dir IS src/, so this also covers source files.
PROTECTED_FILES = os.listdir(Path.cwd())  # noqa: PTH208


# Translation
DEFAULT_LANG = "English"
# https://ai.google.dev/gemini-api/docs/models/gemini#available-languages
SUPPORTED_LANGUAGES = [
    "Arabic",
    "Bengali",
    "English",
    "French",
    "German",
    "Hindi",
    "Indonesian",
    "Japanese",
    "Korean",
    "Marathi",
    "Portuguese",
    "Russian",
    "Spanish",
    "Swahili",
    "Tamil",
    "Telugu",
    "Turkish",
    "Ukrainian",
    "Urdu",
    "Vietnamese",
]
