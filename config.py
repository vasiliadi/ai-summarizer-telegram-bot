import os

import telebot
import google.generativeai as genai
import replicate


if os.getenv("ENV") != "PROD":
    from dotenv import load_dotenv
    import logging

    load_dotenv()

    logger = telebot.logger
    telebot.logger.setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.CRITICAL)


# DB
DSN = os.getenv("DSN")


# Telegram bot config
TG_API_TOKEN = os.environ["TG_API_TOKEN"]
bot = telebot.TeleBot(token=TG_API_TOKEN, parse_mode="Markdown")


# Gemini config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
gemini_pro_model = genai.GenerativeModel(
    "models/gemini-1.5-pro-latest",
    generation_config={"max_output_tokens": 8192},
    safety_settings=[
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ],
)


# Replicate.com config
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)


# For clean up
PROTECTED_FILES = [
    "main.py",
    "config.py",
    "database.py",
    "download.py",
    "models.py",
    "summary.py",
    "transcription.py",
    "utils.py",
    "requirements.txt",
]
