from telebot.util import smart_split
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import telegramify_markdown

from config import bot, SUPPORTED_LANGUAGES
from database import (
    register_user,
    select_user,
    toggle_transcription,
    toggle_translation,
    set_target_language,
    toggle_yt_transcription,
)
from summary import summarize
from utils import clean_up
from translate import translate


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


@bot.message_handler(commands=["toggle_transcription"])
def handle_toggle_transcription(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    toggle_transcription(message.from_user.id)
    bot.send_message(
        message.chat.id,
        (
            "Transcription enabled."
            if user.use_transcription
            else "Transcription disabled."
        ),
    )


@bot.message_handler(commands=["toggle_translation"])
def handle_toggle_translation(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    toggle_translation(message.from_user.id)
    bot.send_message(
        message.chat.id,
        (
            "Translation enabled."
            if user.use_translator
            else "Translation disabled."
        ),
    )


@bot.message_handler(commands=["toggle_yt_transcription"])
def handle_toggle_yt_transcription(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    toggle_yt_transcription(message.from_user.id)
    bot.send_message(
        message.chat.id,
        (
            "YT transcription enabled."
            if user.use_yt_transcription
            else "YT transcription disabled."
        ),
    )


@bot.message_handler(commands=["set_target_language"])
def handle_set_target_language(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    languages = [KeyboardButton(lang.title()) for lang in SUPPORTED_LANGUAGES]
    markup.add(*languages)

    bot.send_message(message.chat.id, "Select target language 👇", reply_markup=markup)
    bot.register_next_step_handler(message, proceed_set_target_language)


def proceed_set_target_language(message):
    set_lang = set_target_language(message.from_user.id, message.text)
    if not set_lang:
        raise ValueError("Unknown language")
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"The target language is set to {message.text}.",
        reply_markup=markup,
    )


@bot.message_handler(content_types=["text"])
def handle_text(message):
    try:
        user = select_user(message.from_user.id)
        if not user.approved:
            raise ValueError("User is not approved")

        if message.text.strip().startswith(
            "https://www.youtube.com/"
        ) or message.text.strip().startswith("https://youtu.be/"):
            data = message.text.strip()
        elif message.text.strip().startswith("https://castro.fm/episode/"):
            data = message.text.strip()
        else:
            raise ValueError("No data to proceed")

        answer = summarize(data=data, use_transcription=user.use_transcription)
        answer = telegramify_markdown.markdownify(answer)

        if len(answer) > 4000:  # 4096 limit
            chunks = smart_split(answer, 4000)
            for text in chunks:
                bot.reply_to(message, text)
        else:
            bot.reply_to(message, answer)

        if user.use_translator:
            translation = translate(answer, target_language=user.target_language)
            translation = telegramify_markdown.markdownify(translation)
            if len(translation) > 4096:
                chunks = smart_split(translation, 4096)
                for text in chunks:
                    bot.reply_to(message, text)
            else:
                bot.reply_to(message, translation)

    except Exception as e:
        bot.reply_to(message, f"Unexpected: {e}")
    finally:
        clean_up()


if __name__ == "__main__":
    bot.infinity_polling(timeout=20)
