import logging
import os
from pathlib import Path
from textwrap import dedent

import coloredlogs
import google.generativeai as genai
import replicate
import sentry_sdk
import telebot
from rush import quota, throttle
from rush.limiters import periodic
from rush.stores import redis as redis_store

from prompts import TRANSLATION_SYSTEM_INSTRUCTION

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
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_COMMON_CONFIG = {
    "generation_config": {
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    },
    "safety_settings": [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ],
}
gemini_pro_model = genai.GenerativeModel(
    "models/gemini-1.5-flash-latest",
    **GEMINI_COMMON_CONFIG,
)
gemini_flash_model = genai.GenerativeModel(
    "models/gemini-1.5-flash-latest",
    **GEMINI_COMMON_CONFIG,
    system_instruction=dedent(TRANSLATION_SYSTEM_INSTRUCTION).strip(),
)


# Replicate.com config
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)


# Headers for requests https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",  # noqa: E501
}


# Rate limits https://ai.google.dev/gemini-api/docs/models/gemini#gemini-1.5-pro
MINUTE_LIMIT_KEY = "RPM"
DAILY_LIMIT_KEY = "RPD"
MINUTE_LIMIT = 2
DAILY_LIMIT = 1500
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
    os.listdir(Path.cwd())
    if os.environ.get("ENV") != "PROD"
    else [
        "config.py",
        "database.py",
        "download.py",
        "exceptions.py",
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


DEFAULT_LANG = "English"


PARSING_STRATEGIES = ["browser", "requests"]


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
    "Afrikaans",
    "Amharic",
    "Assamese",
    "Azerbaijani",
    "Belarusian",
    "Bosnian",
    "Catalan",
    "Cebuano",
    "Corsican",
    "Welsh",
    "Dhivehi",
    "Esperanto",
    "Basque",
    "Persian",
    "Filipino",
    "Frisian",
    "Irish",
    "Scots",
    "Galician",
    "Gujarati",
    "Hausa",
    "Hawaiian",
    "Hmong",
    "Haitian",
    "Armenian",
    "Igbo",
    "Icelandic",
    "Javanese",
    "Georgian",
    "Kazakh",
    "Khmer",
    "Kannada",
    "Krio",
    "Kurdish",
    "Kyrgyz",
    "Latin",
    "Luxembourgish",
    "Lao",
    "Malagasy",
    "Maori",
    "Macedonian",
    "Malayalam",
    "Mongolian",
    "Meiteilon",
    "Marathi",
    "Malay",
    "Maltese",
    "Myanmar",
    "Nepali",
    "Nyanja",
    "Odia",
    "Punjabi",
    "Pashto",
    "Sindhi",
    "Sinhala",
    "Samoan",
    "Shona",
    "Somali",
    "Albanian",
    "Sesotho",
    "Sundanese",
    "Tamil",
    "Telugu",
    "Tajik",
    "Uyghur",
    "Urdu",
    "Uzbek",
    "Xhosa",
    "Yiddish",
    "Yoruba",
    "Zulu",
]
