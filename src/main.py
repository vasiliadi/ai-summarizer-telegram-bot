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
    ALLOWED_MODELS_FOR_SUMMARY,
    DAILY_LIMIT_KEY,
    SUPPORTED_LANGUAGES,
    bot,
    per_day_limit,
)
from database import (
    check_auth,
    register_user,
    select_user,
    set_summarizing_model,
    set_target_language,
    toggle_transcription,
    toggle_translation,
    toggle_yt_transcription,
)
from exceptions import LimitExceededError
from parse import parse_webpage_with_requests
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


# /set_summarizing_model
@bot.message_handler(
    commands=["set_summarizing_model"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_set_summarizing_model(message: "Message") -> None:
    """Handle the /set_summarizing_model command for the bot.

    This function presents the user with a keyboard of allowed summarizing models
    to choose from. Once the user selects a model, the bot proceeds to set the
    summarizing model for the user. The function ensures that the user is
    authenticated before allowing them to set a model.

    Args:
        message (Message): The message object from Telegram containing user information
                          and chat details.

    Returns:
        None

    """
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    models = [KeyboardButton(model) for model in ALLOWED_MODELS_FOR_SUMMARY]
    markup.add(*models)

    bot.send_message(
        message.chat.id,
        "Select summarizing model 👇",
        reply_markup=markup,
    )
    bot.register_next_step_handler(message, proceed_set_summarizing_model)


def proceed_set_summarizing_model(message: "Message") -> None:
    """Process the summarizing model selection and update user settings.

    This function is called after the user selects a model from the keyboard markup.
    It attempts to set the user's summarizing model preference and sends a confirmation
    message. If the selected model is not supported, it sends an error message.

    Args:
        message (Message): The message object from Telegram containing the selected
                          model and user information.

    Returns:
        None

    """
    set_model = set_summarizing_model(message.from_user.id, message.text)
    if not set_model:
        msg = "Unknown model"
        bot.send_message(message.chat.id, msg)
        return
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"The summarizing model is set to {message.text}.",
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
            data = bot.get_file(
                message.audio.file_id,
            )  # Max 20MB https://core.telegram.org/bots/api#getfile
            answer = summarize(
                data=data,
                use_transcription=user.use_transcription,
                model=user.summarizing_model,
            )
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
                model=user.summarizing_model,
                use_yt_transcription=user.use_yt_transcription,
            )
            send_answer(message, user, answer)
        elif re.match(other_url_pattern, url):
            content = parse_webpage_with_requests(url)
            if content is None:
                bot.reply_to(message, "No content to summarize.")
            else:
                answer = summarize_webpage(
                    content=content,
                    model=user.summarizing_model,
                )
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
