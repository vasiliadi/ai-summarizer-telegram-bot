import re
from textwrap import dedent
from typing import TYPE_CHECKING

from sentry_sdk import capture_exception
from telebot.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from tenacity import RetryError

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
from exceptions import LimitExceededError
from parse import parse_webpage
from services import send_answer
from summary import summarize, summarize_webpage
from utils import clean_up

if TYPE_CHECKING:
    from telebot.types import Message


# /start
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


# /info
@bot.message_handler(commands=["info"])
def handle_info(message: "Message") -> None:
    """Handle the /info command for the bot.

    This function sends back the user's Telegram ID when they use the /info command.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
    bot.send_message(message.chat.id, f"{message.from_user.id}")


# /myinfo
@bot.message_handler(
    commands=["myinfo"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_myinfo(message: "Message") -> None:
    """Handle the /myinfo command for the bot.

    This function retrieves and sends detailed information about the user.
    It checks if the user is authenticated and then fetches their information
    from the database, including their user ID, approval status, transcription
    and translation settings, target language, and parsing strategy.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
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


# /limit
@bot.message_handler(
    commands=["limit"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_limit(message: "Message") -> None:
    """Handle the /limit command for the bot.

    This function checks the user's remaining daily limit and sends a message
    with the remaining count. It ensures that the user is authenticated before
    performing the check.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
    rpd = per_day_limit.check(DAILY_LIMIT_KEY, quantity=0)
    msg = f"Remaining limit: {rpd.remaining}"
    bot.send_message(message.chat.id, msg)


# /toggle_transcription
@bot.message_handler(
    commands=["toggle_transcription"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_toggle_transcription(message: "Message") -> None:
    """Handle the /toggle_transcription command for the bot.

    This function toggles the transcription setting for the authenticated user.
    It first checks the current transcription status, toggles it, and then sends
    a confirmation indicating whether transcription has been enabled or disabled.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
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


# /toggle_translation
@bot.message_handler(
    commands=["toggle_translation"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_toggle_translation(message: "Message") -> None:
    """Handle the /toggle_translation command for the bot.

    This function toggles the translation setting for the authenticated user.
    It first checks the current translation status, toggles it, and then sends
    a confirmation indicating whether translation has been enabled or disabled.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
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


# /toggle_yt_transcription
@bot.message_handler(
    commands=["toggle_yt_transcription"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_toggle_yt_transcription(message: "Message") -> None:
    """Handle the /toggle_yt_transcription command for the bot.

    This function toggles the YouTube transcription setting for the authenticated user.
    It first checks the current YouTube transcription status, toggles it, and then sends
    a confirmation indicating whether transcription has been enabled or disabled.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
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


# /set_target_language
@bot.message_handler(
    commands=["set_target_language"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_set_target_language(message: "Message") -> None:
    """Handle the /set_target_language command for the bot.

    This function presents the user with a keyboard of supported languages
    to choose from. Once the user selects a language, the bot proceeds to
    set the target language for the user. The function ensures that the user
    is authenticated before allowing them to set a target language.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    languages = [KeyboardButton(lang.title()) for lang in SUPPORTED_LANGUAGES]
    markup.add(*languages)

    bot.send_message(message.chat.id, "Select target language 👇", reply_markup=markup)
    bot.register_next_step_handler(message, proceed_set_target_language)


def proceed_set_target_language(message: "Message") -> None:
    """Process the target language selection and update user settings.

    This function is called after the user selects a language from the keyboard markup.
    It attempts to set the user's target language preference and sends a confirmation
    message. If the selected language is not supported, it raises a ValueError.

    Args:
        message (Message): The message object from Telegram containing the selected
                          language and user information.

    Raises:
        ValueError: If the selected language is not supported.

    Returns:
        None

    """
    set_lang = set_target_language(message.from_user.id, message.text)
    if not set_lang:
        msg = "Unknown language"
        bot.send_message(message.chat.id, msg)
        return
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"The target language is set to {message.text}.",
        reply_markup=markup,
    )


# /set_parsing_strategy
@bot.message_handler(
    commands=["set_parsing_strategy"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_set_parsing_strategy(message: "Message") -> None:
    """Handle the /set_parsing_strategy command for the bot.

    This function presents the user with a keyboard of available parsing strategies
    to choose from. Once the user selects a strategy, the bot proceeds to set the
    parsing strategy for the user. The function ensures that the user is authenticated
    before allowing them to set a parsing strategy.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
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
    """Process the parsing strategy selection and update user settings.

    This function is called after the user selects a parsing strategy from
    the keyboard markup. It attempts to set the user's parsing strategy preference
    and sends a confirmation message.
    If the selected strategy is not supported, it raises a ValueError.

    Args:
        message (Message): The message object from Telegram containing the selected
                           parsing strategy and user information.

    Raises:
        ValueError: If the selected parsing strategy is not supported.

    Returns:
        None

    """
    set_strategy = set_parsing_strategy(message.from_user.id, message.text)
    if not set_strategy:
        msg = "Unknown strategy"
        bot.send_message(message.chat.id, msg)
        return
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"Parsing strategy is set to {message.text}.",
        reply_markup=markup,
    )


# Unified handler
@bot.message_handler(content_types=["text", "audio"])
def handle_message(message: "Message") -> None:
    """Universal message handler for the bot.

    This function processes various types of content:
    - YouTube and Castro.fm URLs
    - Other webpage URLs
    - Audio files
    - General text messages

    Args:
        message (Message): The message object from Telegram

    Raises:
        LimitExceededError: When user exceeds daily limit
        RetryError: When multiple processing attempts fail
        Exception: For any other unexpected errors

    Returns:
        None

    """
    user = select_user(message.from_user.id)

    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
        return

    try:
        # Handle audio files
        if message.content_type == "audio":
            data = bot.get_file(message.audio.file_id)
            answer = summarize(data=data, use_transcription=user.use_transcription)
            send_answer(message, user, answer)
            return

        url = message.text.strip().split(" ", maxsplit=1)[0]

        # YouTube/Castro pattern
        yt_castro_pattern = (
            r"^https:\/\/(www\.youtube\.com\/*|youtu\.be\/|castro\.fm\/episode\/)[\S]*"
        )
        # Other URLs pattern
        other_url_pattern = r"^(?!https:\/\/(www\.youtube\.com\/|youtu\.be\/|castro\.fm\/episode\/)[\S]*)https?[\S]*"  # noqa: E501

        if re.match(yt_castro_pattern, url):
            answer = summarize(
                data=url,
                use_transcription=user.use_transcription,
                use_yt_transcription=user.use_yt_transcription,
            )
            send_answer(message, user, answer)
        elif re.match(other_url_pattern, url):
            content = parse_webpage(url, strategy=user.parsing_strategy)
            if content is None:
                bot.reply_to(message, "No content to summarize.")
            else:
                answer = summarize_webpage(content)
                send_answer(message, user, answer)
        else:
            bot.send_message(message.chat.id, "No data to proceed.")

    except LimitExceededError as e:
        capture_exception(e)
        bot.reply_to(message, "Daily limit has been exceeded, try again tomorrow.")
    except RetryError as e:
        capture_exception(e)
        bot.reply_to(
            message,
            "An error occurred during execution. Please try again in 10 minutes.",
        )
    except Exception as e:  # pylint: disable=W0718
        capture_exception(e)
        bot.reply_to(message, f"Unexpected: {type(e).__name__}")


if __name__ == "__main__":
    try:
        bot.infinity_polling(timeout=20)
    finally:
        clean_up(all_downloads=True)
