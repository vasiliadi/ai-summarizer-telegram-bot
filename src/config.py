import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import replicate
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
from tavily import TavilyClient

if os.environ.get("ENV") != "PROD":
    from dotenv import load_dotenv

    load_dotenv()


# Sentry.io config
sentry_sdk.init(
    dsn=os.environ["SENTRY_DSN"],
    enable_logs=True,
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
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
openrouter_provider = OpenRouterProvider(api_key=OPENROUTER_API_KEY)


# Summarizing model registry
@dataclass(frozen=True)
class ModelSpec:
    """A selectable summarizing model: its label, provider, and input modalities.

    `provider` names the pydantic-ai provider the model is reached through. It
    dispatches in three places, all of which a new provider has to answer for:
    `llm.LLMClient.build_model` (which raises for a provider it cannot build),
    `llm.LLMClient.build_settings`, and `llm.LLMClient.build_uploaded_file`
    (which serves the Gemini Files API only).

    Both flags say what **this bot can deliver** to the model, not what the
    model's catalog advertises. `supports_audio` False routes spoken content
    through Replicate transcription instead of a native file upload;
    `supports_files` False sends documents to `DEFAULT_MODEL_ID_FOR_SUMMARY`
    instead. Every OpenRouter model is registered with both False on purpose:
    OpenRouter has no file API, so files would have to be inlined as base64,
    and several registered models — `meta/muse-spark-1.2` advertises both — do
    read those modalities upstream. Correcting the flags to match the catalog
    without first building an inline path breaks the routing.
    """

    label: str
    provider: Literal["google", "openrouter"]
    supports_audio: bool
    supports_files: bool


MODEL_SPECS: dict[str, ModelSpec] = {
    "gemini-3.6-flash": ModelSpec(
        label="Gemini 3.6 Flash",
        provider="google",
        supports_audio=True,
        supports_files=True,
    ),
    "meta/muse-spark-1.2": ModelSpec(
        label="Meta Muse Spark 1.2",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
    "minimax/minimax-m3": ModelSpec(
        label="MiniMax M3",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
    "openai/gpt-5.6-luna": ModelSpec(
        label="GPT-5.6 Luna",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
    "qwen/qwen3.8-max": ModelSpec(
        label="Qwen3.8 Max",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
    "thinkingmachines/inkling": ModelSpec(
        label="Thinking Machines Inkling",
        provider="openrouter",
        supports_audio=False,
        supports_files=False,
    ),
}
MODEL_LABELS: dict[str, str] = {k: v.label for k, v in MODEL_SPECS.items()}
MODEL_LABELS_REVERSE: dict[str, str] = {v: k for k, v in MODEL_LABELS.items()}
ALLOWED_MODELS_FOR_SUMMARY = list(MODEL_SPECS.keys())
# If you change DEFAULT_MODEL_ID_FOR_SUMMARY, also change it in models.py.
# It also serves documents whose selected model has supports_files=False, so it
# must stay a spec with supports_files=True.
DEFAULT_MODEL_ID_FOR_SUMMARY = "gemini-3.6-flash"
DEFAULT_THINKING_LEVEL = "medium"
# The keys are pydantic-ai's `ThinkingEffort`, which every provider's model maps
# to its own vocabulary; nothing here translates them. The values exist only to
# give the reply keyboard readable buttons — "xhigh" has no decent title-case.
# Ordered low to high, which is the order the keyboard shows.
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
# Optional: tracing is enabled only when both keys are present, so local runs
# and tests work without Langfuse. When enabled, this is the default: pydantic-ai
# emits an OpenTelemetry span per model call, which the OTel-based Langfuse SDK
# ingests. `llm.LLMClient` overrides it to off for runs whose content is an
# uploaded file, so only text-input model calls get traced.
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
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)


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
