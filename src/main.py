# ruff: noqa: D103

from textwrap import dedent
from typing import TYPE_CHECKING

from sentry_sdk import capture_exception
from telebot.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from config import (
    DAILY_LIMIT_KEY,
    PARSING_STRATEGIES,
    SUPPORTED_LANGUAGES,
    bot,
    per_day_limit,
)
from database import (
    check_auth,
    register_user,
    select_user,
    set_parsing_strategy,
    set_target_language,
    toggle_transcription,
    toggle_translation,
    toggle_yt_transcription,
)
from parse import parse_webpage
from services import send_answer
from summary import summarize, summarize_webpage
from utils import clean_up

if TYPE_CHECKING:
    from telebot.types import Message


@bot.message_handler(commands=["start"])
def handle_start(message: "Message") -> None:
    """Handle the /start command for the bot.

    This function registers new users and sends a welcome message. If the user is
    registering for the first time, they receive an initial greeting. Otherwise,
    they receive a confirmation message.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
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
                Parsing strategy: {user.parsing_strategy}
                """).strip()
    bot.send_message(message.chat.id, msg)


@bot.message_handler(
    commands=["limit"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_limit(message: "Message") -> None:
    rpd = per_day_limit.check(DAILY_LIMIT_KEY, quantity=0)
    msg = f"Remaining limit: {rpd.remaining}"
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
        msg = "Unknown language"
        raise ValueError(msg)
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"The target language is set to {message.text}.",
        reply_markup=markup,
    )


# YouTube and Castro
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
        bot.reply_to(message, f"Unexpected: {type(e).__name__}")


@bot.message_handler(
    commands=["set_parsing_strategy"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_set_parsing_strategy(message: "Message") -> None:
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    strategies = [KeyboardButton(strategy) for strategy in PARSING_STRATEGIES]
    markup.add(*strategies)

    bot.send_message(
        message.chat.id,
        "Select parsing strategy 👇",
        reply_markup=markup,
    )
    bot.register_next_step_handler(message, proceed_set_parsing_strategy)


def proceed_set_parsing_strategy(message: "Message") -> None:
    set_strategy = set_parsing_strategy(message.from_user.id, message.text)
    if not set_strategy:
        msg = "Unknown strategy"
        raise ValueError(msg)
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"Parsing strategy is set to {message.text}.",
        reply_markup=markup,
    )


# All other links
@bot.message_handler(
    regexp=r"^(?!https:\/\/(www\.youtube\.com\/|youtu\.be\/|castro\.fm\/episode\/)[\S]*)https?[\S]*",
    func=lambda message: check_auth(message.from_user.id),
)
def handle_webpages(message: "Message") -> None:
    try:
        user = select_user(message.from_user.id)
        parsing_strategy = user.parsing_strategy
        url = message.text.strip().split(" ", maxsplit=1)[0]
        content = parse_webpage(url, strategy=parsing_strategy)
        if content is None:
            bot.reply_to(message, "No content to summarize.")
        else:  # noqa: PLR5501
            if parsing_strategy == "perplexity":
                send_answer(message, user, content)
            else:
                answer = summarize_webpage(content)
                send_answer(message, user, answer)
    except Exception as e:  # pylint: disable=W0718
        capture_exception(e)
        bot.reply_to(message, f"Unexpected: {type(e).__name__}")


@bot.message_handler(
    content_types=["audio"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_audio(message: "Message") -> None:
    try:
        user = select_user(message.from_user.id)
        data = bot.get_file(message.audio.file_id)
        answer = summarize(
            data=data,
            use_transcription=user.use_transcription,
        )
        send_answer(message, user, answer)

    except Exception as e:  # pylint: disable=W0718
        capture_exception(e)
        bot.reply_to(message, f"Unexpected: {type(e).__name__}")


@bot.message_handler(content_types=["text"])
def handle_text(message: "Message") -> None:
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
    else:
        bot.send_message(message.chat.id, "No data to proceed.")


if __name__ == "__main__":
    try:
        bot.infinity_polling(timeout=20)
    finally:
        clean_up(all_downloads=True)
