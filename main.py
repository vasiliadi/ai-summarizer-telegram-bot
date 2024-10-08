from telebot.util import smart_split
import telegramify_markdown

from config import bot
from download import download_yt, download_castro
from database import (
    register_user,
    select_user,
    enable_transcription,
    disable_transcription,
)
from summary import summarize
from utils import clean_up


@bot.message_handler(commands=["start"])
def handle_start(message):
    if register_user(
        message.from_user.id,
        message.from_user.first_name,
        message.from_user.last_name,
        message.from_user.username,
    ):
        bot.send_message(
            message.chat.id,
            "Hi there. I'm a private bot, if you know how to use me, go ahead.",
        )
    else:
        bot.send_message(
            message.chat.id,
            "You are good to go!",
        )


@bot.message_handler(commands=["info"])
def handle_info(message):
    bot.send_message(message.chat.id, f"{message.from_user.id}")


@bot.message_handler(commands=["enable_transcription"])
def handle_info(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved.")

    enable_transcription(message.from_user.id)
    bot.send_message(message.chat.id, "Transcription enabled.")


@bot.message_handler(commands=["disable_transcription"])
def handle_info(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved.")

    disable_transcription(message.from_user.id)
    bot.send_message(message.chat.id, "Transcription disabled.")


@bot.message_handler(content_types=["text"])
def handle_text(message):
    try:
        user = select_user(message.from_user.id)
        if not user.approved:
            bot.send_message(message.chat.id, "You are not approved.")
            raise ValueError("User is not approved")

        if message.text.strip().startswith(
            "https://www.youtube.com/"
        ) or message.text.strip().startswith("https://youtu.be/"):
            file = download_yt(input=message.text.strip())
        elif message.text.strip().startswith("https://castro.fm/episode/"):
            file = download_castro(input=message.text.strip())
        else:
            bot.reply_to(message, "I don't find anything useful here.")
            raise ValueError("No file to proceed")

        answer = summarize(file=file, use_transcription=user.use_transcription)
        answer = telegramify_markdown.markdownify(answer)

        if len(answer) > 3500:  # 4096 limit
            chunks = smart_split(answer, 3500)
            for text in chunks:
                bot.reply_to(message, text)
        else:
            bot.reply_to(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Unexpected: {e}")
    finally:
        try:
            clean_up(file)
        except:
            pass


if __name__ == "__main__":
    bot.infinity_polling(timeout=20)
