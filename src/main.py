import logging
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
    MODEL_LABELS,
    PROMPT_STRATEGY_LABELS,
    SUPPORTED_LANGUAGES,
    bot,
)
from database import (
    check_auth,
    register_user,
    select_user,
    set_prompt_strategy,
    set_summarizing_model,
    set_target_language,
    toggle_transcription,
    toggle_yt_transcription,
)
from exceptions import LimitExceededError
from handlers import (
    handle_audio,
    handle_document,
    handle_url,
    handle_video,
    handle_video_note,
    handle_voice,
)
from services import get_remaining_quota
from utils import clean_up

if TYPE_CHECKING:
    from telebot.types import Message

    from models import UsersOrm

logger = logging.getLogger(__name__)


# /start
@bot.message_handler(commands=["start"])
def handle_start(message: Message) -> None:
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
    if message.from_user is None:
        bot.reply_to(message, "User information is missing.")
        return
    if register_user(
        message.from_user.id,
        message.from_user.first_name or "",
        message.from_user.last_name or "",
        message.from_user.username or "",
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
def handle_info(message: Message) -> None:
    """Handle the /info command for the bot.

    This function sends back the user's Telegram ID when they use the /info command.

    Args:
        message (Message): The message object from Telegram containing user information
                           and chat details.

    Returns:
        None

    """
    if message.from_user is None:
        bot.reply_to(message, "User information is missing.")
        return
    bot.send_message(message.chat.id, f"{message.from_user.id}")


# /myinfo
@bot.message_handler(
    commands=["myinfo"],
    func=lambda message: (
        message.from_user is not None and check_auth(message.from_user.id)
    ),
)
def handle_myinfo(message: Message) -> None:
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
    if message.from_user is None:
        bot.reply_to(message, "User information is missing.")
        return
    user = select_user(message.from_user.id)
    msg = dedent(f"""
                UserId: {user.user_id}
                Approved: {user.approved}
                YouTube transcript: {user.use_yt_transcription}
                Audio transcript: {user.use_transcription}
                Target language: {user.target_language}
                Summarizing model: {user.summarizing_model}
                Prompt strategy: {user.prompt_key_for_summary}
                Daily limit: {user.daily_limit}
                Remaining quota: {get_remaining_quota(user.user_id, user.daily_limit)}
                """).strip()
    bot.send_message(message.chat.id, msg)


# /limit
@bot.message_handler(
    commands=["limit"],
    func=lambda message: (
        message.from_user is not None and check_auth(message.from_user.id)
    ),
)
def handle_limit(message: Message) -> None:
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
    if message.from_user is None:
        return
    user = select_user(message.from_user.id)
    remaining = get_remaining_quota(user.user_id, user.daily_limit)
    msg = f"Remaining limit: {remaining}"
    bot.send_message(message.chat.id, msg)


# /toggle_transcription
@bot.message_handler(
    commands=["toggle_transcription"],
    func=lambda message: (
        message.from_user is not None and check_auth(message.from_user.id)
    ),
)
def handle_toggle_transcription(message: Message) -> None:
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
    if message.from_user is None:
        bot.reply_to(message, "User information is missing.")
        return
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


# /toggle_yt_transcription
@bot.message_handler(
    commands=["toggle_yt_transcription"],
    func=lambda message: (
        message.from_user is not None and check_auth(message.from_user.id)
    ),
)
def handle_toggle_yt_transcription(message: Message) -> None:
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
    if message.from_user is None:
        bot.reply_to(message, "User information is missing.")
        return
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
    func=lambda message: (
        message.from_user is not None and check_auth(message.from_user.id)
    ),
)
def handle_set_target_language(message: Message) -> None:
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


def proceed_set_target_language(message: Message) -> None:
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
    if message.from_user is None or message.text is None:
        bot.reply_to(message, "User information or language is missing.")
        return
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
    func=lambda message: (
        message.from_user is not None and check_auth(message.from_user.id)
    ),
)
def handle_set_summarizing_model(message: Message) -> None:
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
    models = [KeyboardButton(label) for label in MODEL_LABELS.values()]
    markup.add(*models)

    bot.send_message(
        message.chat.id,
        "Select summarizing model 👇",
        reply_markup=markup,
    )
    bot.register_next_step_handler(message, proceed_set_summarizing_model)


def proceed_set_summarizing_model(message: Message) -> None:
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
    if message.from_user is None or message.text is None:
        bot.reply_to(message, "User information or model is missing.")
        return
    label_to_model = {v: k for k, v in MODEL_LABELS.items()}
    model_id = label_to_model.get(message.text)
    if model_id is None:
        bot.send_message(message.chat.id, "Unknown model")
        return
    if not set_summarizing_model(message.from_user.id, model_id):
        bot.send_message(message.chat.id, "Failed to update summarizing model.")
        return
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"The summarizing model is set to {message.text}.",
        reply_markup=markup,
    )


# /set_prompt_strategy
@bot.message_handler(
    commands=["set_prompt_strategy"],
    func=lambda message: (
        message.from_user is not None and check_auth(message.from_user.id)
    ),
)
def handle_set_prompt_strategy(message: Message) -> None:
    """Handle the /set_prompt_strategy command for the bot.

    This function presents the user with a keyboard of allowed prompt strategies
    to choose from. Once the user selects a strategy, the bot proceeds to set the
    prompt strategy for the user. The function ensures that the user is
    authenticated before allowing them to set a strategy.

    Args:
        message (Message): The message object from Telegram containing user information
                          and chat details.

    Returns:
        None

    """
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    strategies = [KeyboardButton(label) for label in PROMPT_STRATEGY_LABELS.values()]
    markup.add(*strategies)

    bot.send_message(
        message.chat.id,
        "Select summarization strategy 👇",
        reply_markup=markup,
    )
    bot.register_next_step_handler(message, proceed_set_prompt_strategy)


def proceed_set_prompt_strategy(message: Message) -> None:
    """Process the prompt strategy selection and update user settings.

    This function is called after the user selects a strategy from the keyboard markup.
    It attempts to set the user's prompt strategy preference and sends a confirmation
    message. If the selected strategy is not supported, it sends an error message.

    Args:
        message (Message): The message object from Telegram containing the selected
                           strategy and user information.

    Returns:
        None

    """
    if message.from_user is None or message.text is None:
        bot.reply_to(message, "User information or strategy is missing.")
        return
    label_to_key = {v: k for k, v in PROMPT_STRATEGY_LABELS.items()}
    prompt_key = label_to_key.get(message.text)
    if prompt_key is None:
        bot.send_message(message.chat.id, "Unknown strategy")
        return
    if not set_prompt_strategy(message.from_user.id, prompt_key):
        bot.send_message(message.chat.id, "Failed to update prompt strategy.")
        return
    markup = ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        f"The prompt strategy is set to {message.text}.",
        reply_markup=markup,
    )


def process_message_content(message: Message, user: UsersOrm) -> None:
    """Process the content of a validated message.

    Args:
        message (Message): The message object from Telegram
        user (UsersOrm): The authenticated user object

    Returns:
        None

    """
    if message.content_type == "audio":
        handle_audio(message, user)
    elif (
        message.content_type == "document"
        and message.document is not None
        and message.document.mime_type
        in (
            "application/pdf",
            "text/plain",
            "text/rtf",
            "text/csv",
            "audio/ogg",
        )
    ):
        handle_document(message, user)
    elif message.content_type == "video_note":
        logger.debug("video_note found. Starting video_note handle...")
        handle_video_note(message, user)
    elif message.content_type == "voice":
        handle_voice(message, user)
    elif message.content_type == "video":
        handle_video(message, user)
    else:
        if message.text is None:
            bot.send_message(message.chat.id, "No text to process.")
            return
        url = message.text.strip().split(" ", maxsplit=1)[0]
        handle_url(message, user, url)


# Unified handler
@bot.message_handler(
    content_types=["text", "audio", "document", "video_note", "voice", "video"],
)
def handle_message(message: Message) -> None:
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
    try:
        if message.from_user is None:
            bot.reply_to(message, "User information is missing.")
            return
        user = select_user(message.from_user.id)

        if not user.approved:
            bot.send_message(message.chat.id, "You are not approved.")
            return

        process_message_content(message, user)

    except LimitExceededError as e:
        capture_exception(e)
        bot.reply_to(message, "Daily limit has been exceeded, try again tomorrow.")
    except RetryError as e:
        capture_exception(e)
        bot.reply_to(
            message,
            "An error occurred during execution. Please try again in 10 minutes.",
        )
    except Exception as e:
        capture_exception(e)
        bot.reply_to(message, f"Unexpected: {type(e).__name__}")


if __name__ == "__main__":
    try:
        bot.infinity_polling(timeout=20)
    finally:
        clean_up(all_downloads=True)
