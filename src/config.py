import os
from pathlib import Path

import google.generativeai as genai
import replicate
import sentry_sdk
import telebot

if os.getenv("ENV") != "PROD":
    import logging

    from dotenv import load_dotenv

    load_dotenv()

    logger = telebot.logger
    telebot.logger.setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.CRITICAL)


# Sentry.io config
sentry_sdk.init(
    dsn=os.environ["SENTRY_DSN"],
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
)


# DB
DSN = os.getenv("DSN")


# Proxy
PROXY = os.getenv("PROXY")


# Telegram bot config
TG_API_TOKEN = os.environ["TG_API_TOKEN"]
bot = telebot.TeleBot(token=TG_API_TOKEN, disable_web_page_preview=True)


# Gemini config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_COMMON_CONFIG = {
    "generation_config": {"max_output_tokens": 8192},
    "safety_settings": [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ],
}
gemini_pro_model = genai.GenerativeModel(
    "models/gemini-1.5-pro-latest",
    **GEMINI_COMMON_CONFIG,
)
gemini_flash_model = genai.GenerativeModel(
    "models/gemini-1.5-flash-latest",
    **GEMINI_COMMON_CONFIG,
)


# Replicate.com config
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)


# For clean up
PROTECTED_FILES = (
    os.listdir(Path.cwd())
    if os.getenv("ENV") != "PROD"
    else [
        "config.py",
        "database.py",
        "download.py",
        "main.py",
        "models.py",
        "summary.py",
        "transcription.py",
        "translate.py",
        "utils.py",
    ]
)


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
