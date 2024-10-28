from textwrap import dedent
from typing import TYPE_CHECKING

from sentry_sdk import capture_exception
from telebot.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from config import SUPPORTED_LANGUAGES, bot
from database import (
    check_auth,
    register_user,
    select_user,
    set_target_language,
    toggle_transcription,
    toggle_translation,
    toggle_yt_transcription,
)
from parse import parse_webpage
from summary import summarize, summarize_webpage
from utils import clean_up, send_answer

if TYPE_CHECKING:
    from telebot.types import Message


@bot.message_handler(commands=["start"])
def handle_start(message: "Message") -> None:
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
def handle_info(message: "Message") -> None:
    bot.send_message(message.chat.id, f"{message.from_user.id}")


@bot.message_handler(
    commands=["myinfo"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_myinfo(message: "Message") -> None:
    user = select_user(message.from_user.id)
    msg = dedent(f"""
                UserId: {user.user_id}
                Approved: {user.approved}
                YouTube transcript: {user.use_yt_transcription}
                Audio transcript: {user.use_transcription}
                Translator: {user.use_translator}
                Target language: {user.target_language}
                """).strip()
    bot.send_message(message.chat.id, msg)


@bot.message_handler(
    commands=["toggle_transcription"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_toggle_transcription(message: "Message") -> None:
    user = select_user(message.from_user.id)
    toggle_transcription(message.from_user.id)
    bot.send_message(
        message.chat.id,
        (
            "Transcription enabled."
            if not user.use_transcription
            else "Transcription disabled."
        ),
    )


@bot.message_handler(
    commands=["toggle_translation"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_toggle_translation(message: "Message") -> None:
    user = select_user(message.from_user.id)
    toggle_translation(message.from_user.id)
    bot.send_message(
        message.chat.id,
        (
            "Translation enabled."
            if not user.use_translator
            else "Translation disabled."
        ),
    )


@bot.message_handler(
    commands=["toggle_yt_transcription"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_toggle_yt_transcription(message: "Message") -> None:
    user = select_user(message.from_user.id)
    toggle_yt_transcription(message.from_user.id)
    bot.send_message(
        message.chat.id,
        (
            "YT transcription enabled."
            if not user.use_yt_transcription
            else "YT transcription disabled."
        ),
    )


@bot.message_handler(
    commands=["set_target_language"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_set_target_language(message: "Message") -> None:
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    languages = [KeyboardButton(lang.title()) for lang in SUPPORTED_LANGUAGES]
    markup.add(*languages)

    bot.send_message(message.chat.id, "Select target language 👇", reply_markup=markup)
    bot.register_next_step_handler(message, proceed_set_target_language)


def proceed_set_target_language(message: "Message") -> None:
    set_lang = set_target_language(message.from_user.id, message.text)
    if not set_lang:
        raise ValueError("Unknown language")
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"The target language is set to {message.text}.",
        reply_markup=markup,
    )


@bot.message_handler(
    regexp=r"^https:\/\/(www\.youtube\.com\/*|youtu\.be\/|castro\.fm\/episode\/)[\S]*",
    func=lambda message: check_auth(message.from_user.id),
)
def handle_regexp(message: "Message") -> None:
    try:
        user = select_user(message.from_user.id)
        data = message.text.strip().split(" ", maxsplit=1)[0]
        answer = summarize(
            data=data,
            use_transcription=user.use_transcription,
            use_yt_transcription=user.use_yt_transcription,
        )
        send_answer(message, user, answer)

    except Exception as e:  # pylint: disable=W0718
        capture_exception(e)
        bot.reply_to(message, "An Unexpected Error Has Occurred.")
    finally:
        clean_up()


@bot.message_handler(
    regexp=r"^(?!https:\/\/(www\.youtube\.com\/|youtu\.be\/|castro\.fm\/episode\/)[\S]*)https?[\S]*",
    func=lambda message: check_auth(message.from_user.id),
)
def handle_webpages(message: "Message") -> None:
    try:
        user = select_user(message.from_user.id)
        url = message.text.strip().split(" ", maxsplit=1)[0]
        content = parse_webpage(url)
        answer = summarize_webpage(content)
        send_answer(message, user, answer)

    except Exception as e:  # pylint: disable=W0718
        capture_exception(e)
        bot.reply_to(message, "An Unexpected Error Has Occurred.")


@bot.message_handler(content_types=["text"])
def handle_text(message: "Message") -> None:
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
    else:
        bot.send_message(message.chat.id, "No data to proceed.")


if __name__ == "__main__":
    bot.infinity_polling(timeout=20)
