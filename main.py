from telebot.util import smart_split
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import telegramify_markdown

from config import bot, SUPPORTED_LANGUAGES
from download import download_yt, download_castro
from database import (
    register_user,
    select_user,
    enable_transcription,
    disable_transcription,
    enable_translation,
    disable_translation,
    set_target_language,
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


@bot.message_handler(commands=["enable_transcription"])
def handle_enable_transcription(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    enable_transcription(message.from_user.id)
    bot.send_message(message.chat.id, "Transcription enabled.")


@bot.message_handler(commands=["disable_transcription"])
def handle_disable_transcription(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    disable_transcription(message.from_user.id)
    bot.send_message(message.chat.id, "Transcription disabled.")


@bot.message_handler(commands=["enable_translation"])
def handle_enable_translation(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    enable_translation(message.from_user.id)
    bot.send_message(message.chat.id, "Translation enabled.")


@bot.message_handler(commands=["disable_translation"])
def handle_disable_translation(message):
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        raise ValueError("User is not approved")

    disable_translation(message.from_user.id)
    bot.send_message(message.chat.id, "Translation disabled.")


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
            # bot.send_message(message.chat.id, "You are not approved.")
            raise ValueError("User is not approved")

        if (
            not message.text.strip().startswith("https://www.youtube.com/")
            or not message.text.strip().startswith("https://youtu.be/")
            or not message.text.strip().startswith("https://castro.fm/episode/")
        ):
            # bot.reply_to(message, "I don't find anything useful here.")
            raise ValueError("No data to proceed")

        answer = summarize(data=message.text.strip(), use_transcription=user.use_transcription)
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
