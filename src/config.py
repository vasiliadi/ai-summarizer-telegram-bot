import logging
import os
import sys
from pathlib import Path

import replicate
import sentry_sdk
import telebot
from google import genai
from google.genai import types
from limits import parse as parse_rate_limit
from limits.storage import RedisStorage
from limits.strategies import FixedWindowRateLimiter
from tavily import TavilyClient

if os.environ.get("ENV") != "PROD":
    from dotenv import load_dotenv

    load_dotenv()


# Sentry.io config
sentry_sdk.init(
    dsn=os.environ["SENTRY_DSN"],
    send_default_pii=True,  # capture input and output of your AI model
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    enable_tracing=True,
    enable_logs=True,
)

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "ERROR").upper()
NUMERIC_LOG_LEVEL = getattr(logging, LOG_LEVEL, "ERROR")
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
MODEL_LABELS: dict[str, str] = {
    "gemini-3.5-flash": "Gemini 3.5 Flash",
}
MODEL_LABELS_REVERSE: dict[str, str] = {v: k for k, v in MODEL_LABELS.items()}
ALLOWED_MODELS_FOR_SUMMARY = list(MODEL_LABELS.keys())
# If you change DEFAULT_MODEL_ID_FOR_SUMMARY, also change it in models.py.
DEFAULT_MODEL_ID_FOR_SUMMARY = "gemini-3.5-flash"
SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
]
DEFAULT_THINKING_LEVEL = "MINIMAL"
THINKING_LEVEL_LABELS: dict[str, str] = {
    "MINIMAL": "Minimal",
    "LOW": "Low",
    "MEDIUM": "Medium",
    "HIGH": "High",
}
THINKING_LEVEL_LABELS_REVERSE: dict[str, str] = {
    v: k for k, v in THINKING_LEVEL_LABELS.items()
}
ALLOWED_THINKING_LEVELS = list(THINKING_LEVEL_LABELS.keys())
GEMINI_CONFIG = types.GenerateContentConfig(
    system_instruction=None,
    safety_settings=SAFETY_SETTINGS,
    response_mime_type="text/plain",
)


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


# YouTube transcript source backend, set via env ("api" or "ytdlp").
YT_TRANSCRIPT_SOURCE = (os.environ.get("YT_TRANSCRIPT_SOURCE") or "ytdlp").lower()


# Replicate.com config
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)


# Tavily config
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)


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
