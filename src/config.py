import logging
import os
import sys
from pathlib import Path

import replicate
import sentry_sdk
import telebot
from google import genai
from google.genai import types
from rush import quota, throttle
from rush.limiters import periodic
from rush.stores import redis as redis_store

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
PROXY = os.environ.get("PROXY", "")


# Telegram bot config
TG_API_TOKEN = os.environ["TG_API_TOKEN"]
bot = telebot.TeleBot(token=TG_API_TOKEN, disable_web_page_preview=True)


# Gemini config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_LABELS: dict[str, str] = {
    "gemini-3-flash-preview": "Gemini 3 Flash",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
}
ALLOWED_MODELS_FOR_SUMMARY = list(MODEL_LABELS.keys())
MODELS_WITH_THINKING_SUPPORT = [
    "gemini-3-flash-preview",
]
# If you change DEFAULT_MODEL_ID_FOR_SUMMARY, also change it in models.py.
DEFAULT_MODEL_ID_FOR_SUMMARY = "gemini-3-flash-preview"
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
ALLOWED_PROMPT_KEYS = list(PROMPT_STRATEGY_LABELS.keys())


# Replicate.com config
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)


# Headers for requests https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",  # noqa: E501
}


# Rate limits https://ai.google.dev/gemini-api/docs/models#gemini-2.5-pro-exp-03-25
MINUTE_LIMIT_KEY = "RPM"
DAILY_LIMIT_KEY = "RPD"
MINUTE_LIMIT = 5
rate_limiter_redis = redis_store.redis.StrictRedis.from_url(
    url=RATE_LIMITER_URL,
    decode_responses=True,
)
rate_limiter_store = redis_store.RedisStore(
    url=RATE_LIMITER_URL,
    client=rate_limiter_redis,
)
per_minute_limit = throttle.Throttle(
    limiter=periodic.PeriodicLimiter(
        store=rate_limiter_store,
    ),
    rate=quota.Quota.per_minute(
        count=MINUTE_LIMIT,
    ),
)


# For cleanup
PROTECTED_FILES = (
    os.listdir(Path.cwd())  # noqa: PTH208
    if os.environ.get("ENV") != "PROD"
    else [
        "config.py",
        "database.py",
        "download.py",
        "exceptions.py",
        "handlers.py",
        "main.py",
        "models.py",
        "parse.py",
        "prompts.py",
        "services.py",
        "summary.py",
        "transcription.py",
        "utils.py",
    ]
)


# Translation
DEFAULT_LANG = "English"
# https://ai.google.dev/gemini-api/docs/models/gemini#available-languages
SUPPORTED_LANGUAGES = [
    "Afrikaans",
    "Albanian",
    "Amharic",
    "Arabic",
    "Armenian",
    "Assamese",
    "Azerbaijani",
    "Basque",
    "Belarusian",
    "Bengali",
    "Bosnian",
    "Bulgarian",
    "Catalan",
    "Cebuano",
    "Corsican",
    "Croatian",
    "Czech",
    "Danish",
    "Dhivehi",
    "Dutch",
    "English",
    "Esperanto",
    "Estonian",
    "Finnish",
    "French",
    "Frisian",
    "Galician",
    "Georgian",
    "German",
    "Greek",
    "Gujarati",
    "Haitian Creole",
    "Hausa",
    "Hawaiian",
    "Hebrew",
    "Hindi",
    "Hmong",
    "Hungarian",
    "Icelandic",
    "Igbo",
    "Indonesian",
    "Irish",
    "Italian",
    "Japanese",
    "Javanese",
    "Kannada",
    "Kazakh",
    "Khmer",
    "Korean",
    "Krio",
    "Kurdish",
    "Kyrgyz",
    "Lao",
    "Latin",
    "Latvian",
    "Lithuanian",
    "Luxembourgish",
    "Macedonian",
    "Malagasy",
    "Malay",
    "Malayalam",
    "Maltese",
    "Maori",
    "Marathi",
    "Mongolian",
    "Nepali",
    "Norwegian",
    "Pashto",
    "Persian",
    "Polish",
    "Portuguese",
    "Punjabi",
    "Romanian",
    "Russian",
    "Samoan",
    "Scots Gaelic",
    "Serbian",
    "Sesotho",
    "Shona",
    "Sindhi",
    "Slovak",
    "Slovenian",
    "Somali",
    "Spanish",
    "Sundanese",
    "Swahili",
    "Swedish",
    "Tajik",
    "Tamil",
    "Telugu",
    "Thai",
    "Turkish",
    "Ukrainian",
    "Urdu",
    "Uyghur",
    "Uzbek",
    "Vietnamese",
    "Welsh",
    "Xhosa",
    "Yiddish",
    "Yoruba",
    "Zulu",
]
