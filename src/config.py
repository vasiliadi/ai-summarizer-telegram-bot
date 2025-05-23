import logging
import os
from pathlib import Path

import coloredlogs
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
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    enable_tracing=True,
)

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "ERROR").upper()
NUMERIC_LOG_LEVEL = getattr(logging, LOG_LEVEL, "ERROR")
telebot.logger.setLevel(NUMERIC_LOG_LEVEL)
coloredlogs.install(level=NUMERIC_LOG_LEVEL)


# DB
DSN = os.environ["DSN"]
REDIS_URL = os.environ["REDIS_URL"]
RATE_LIMITER_URL = f"{REDIS_URL}/0"


# Proxy
PROXY = os.environ.get("PROXY", "")
WEB_SCRAPE_PROXY = os.environ.get("WEB_SCRAPE_PROXY", PROXY)


# Telegram bot config
TG_API_TOKEN = os.environ["TG_API_TOKEN"]
bot = telebot.TeleBot(token=TG_API_TOKEN, disable_web_page_preview=True)


# Gemini config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID_FOR_TRANSLATION = "gemini-2.0-flash"
ALLOWED_MODELS_FOR_SUMMARY = [
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-preview-05-20",
    "gemma-3n-e4b-it",
]
# if change DEFAULT_MODEL_ID_FOR_SUMMARY, also change in models.py
DEFAULT_MODEL_ID_FOR_SUMMARY = "gemini-2.0-flash"
SAFETY_SETTINGS = [
    types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="BLOCK_NONE",
    ),
]
GEMINI_CONFIG = types.GenerateContentConfig(
    system_instruction=None,
    safety_settings=SAFETY_SETTINGS,
    response_mime_type="text/plain",
    max_output_tokens=8192,
)


# Prompts
# If change DEFAULT_PROMPT_KEY, also change in models.py
DEFAULT_PROMPT_KEY = "basic_prompt_for_transcript"
ALLOWED_PROMPT_KEYS = [
    "basic_prompt_for_transcript",
    "soap_prompt_for_transcript",
    "key_points_for_transcript",
]


# Replicate.com config
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)


# Headers for requests https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",  # noqa: E501
}


# Rate limits https://ai.google.dev/gemini-api/docs/models#gemini-2.5-pro-exp-03-25
MINUTE_LIMIT_KEY = "RPM"
DAILY_LIMIT_KEY = "RPD"
MINUTE_LIMIT = 2
DAILY_LIMIT = 50
per_minute_limit = throttle.Throttle(
    limiter=periodic.PeriodicLimiter(
        store=redis_store.RedisStore(url=RATE_LIMITER_URL),
    ),
    rate=quota.Quota.per_minute(
        count=MINUTE_LIMIT,
    ),
)
per_day_limit = throttle.Throttle(
    limiter=periodic.PeriodicLimiter(
        store=redis_store.RedisStore(url=RATE_LIMITER_URL),
    ),
    rate=quota.Quota.per_day(
        count=DAILY_LIMIT,
    ),
)


# For clean up
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
        "translate.py",
        "utils.py",
    ]
)


# Translation
DEFAULT_LANG = "English"
# https://ai.google.dev/gemini-api/docs/models/gemini#available-languages
SUPPORTED_LANGUAGES = [
    "Arabic",
    "Bengali",
    "Bulgarian",
    "Chinese",
    "Croatian",
    "Czech",
    "Danish",
    "Dutch",
    "English",
    "Estonian",
    "Finnish",
    "French",
    "German",
    "Greek",
    "Hebrew",
    "Hindi",
    "Hungarian",
    "Indonesian",
    "Italian",
    "Japanese",
    "Korean",
    "Latvian",
    "Lithuanian",
    "Norwegian",
    "Polish",
    "Portuguese",
    "Romanian",
    "Russian",
    "Serbian",
    "Slovak",
    "Slovenian",
    "Spanish",
    "Swahili",
    "Swedish",
    "Thai",
    "Turkish",
    "Ukrainian",
    "Vietnamese",
]
