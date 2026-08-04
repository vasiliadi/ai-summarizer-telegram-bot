"""Telegram bot entry point: builds and runs the BotApp from the composition root."""

from __future__ import annotations

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
    MODEL_LABELS_REVERSE,
    PROMPT_STRATEGY_LABELS,
    PROMPT_STRATEGY_LABELS_REVERSE,
    SUPPORTED_DOCUMENT_MIME_TYPES,
    SUPPORTED_LANGUAGES,
    THINKING_LEVEL_LABELS,
    THINKING_LEVEL_LABELS_REVERSE,
)
from container import build_container
from exceptions import LimitExceededError, WebParseError
from utils import clean_up

if TYPE_CHECKING:
    from collections.abc import Callable

    import telebot
    from telebot.types import Message

    from container import Container
    from database import UserRepository
    from handlers import MessageHandlers
    from models import UsersOrm
    from services import QuotaManager, Tracer


class BotApp:
    """Telegram entry point: registers handlers and routes incoming messages."""

    def __init__(
        self,
        bot: telebot.TeleBot,
        user_repo: UserRepository,
        quota_manager: QuotaManager,
        tracer: Tracer,
        handlers: MessageHandlers,
    ) -> None:
        """Store the injected collaborators used to register and run handlers."""
        self._bot = bot
        self._user_repo = user_repo
        self._quota_manager = quota_manager
        self._tracer = tracer
        self._handlers = handlers

    # /start
    def handle_start(self, message: Message) -> None:
        """Handle /start: register a new user, or welcome back an existing one."""
        if message.from_user is None:
            self._bot.reply_to(message, "User information is missing.")
            return
        if self._user_repo.register_user(
            message.from_user.id,
            message.from_user.first_name or "",
            message.from_user.last_name or "",
            message.from_user.username or "",
        ):
            self._bot.send_message(
                message.chat.id,
                "Hi there. I'm a private bot, if you know how to use me, go ahead.",
            )
        else:
            self._bot.send_message(
                message.chat.id,
                "You are good to go!",
            )

    # /info
    def handle_info(self, message: Message) -> None:
        """Handle /info: reply with the sender's Telegram user ID."""
        if message.from_user is None:
            self._bot.reply_to(message, "User information is missing.")
            return
        self._bot.send_message(message.chat.id, f"{message.from_user.id}")

    # /myinfo
    def handle_myinfo(self, message: Message) -> None:
        """Handle /myinfo: reply with the user's settings, limit, and quota."""
        if message.from_user is None:
            self._bot.reply_to(message, "User information is missing.")
            return
        user = self._user_repo.select_user(message.from_user.id)
        msg = dedent(f"""
                    UserId: {user.user_id}
                    Approved: {user.approved}
                    Target language: {user.target_language}
                    Summarizing model: {MODEL_LABELS.get(user.summarizing_model, user.summarizing_model)}
                    Prompt strategy: {PROMPT_STRATEGY_LABELS.get(user.prompt_key_for_summary, user.prompt_key_for_summary)}
                    Thinking level: {THINKING_LEVEL_LABELS.get(user.thinking_level, user.thinking_level)}
                    Daily limit: {user.daily_limit}
                    Remaining quota: {self._quota_manager.get_remaining_quota(user.user_id, user.daily_limit)}
                    """).strip()  # noqa: E501
        self._bot.send_message(message.chat.id, msg)

    def _prompt_choice(
        self,
        message: Message,
        prompt: str,
        labels: list[str],
        next_step: Callable[[Message], None],
    ) -> None:
        """Send a one-time reply keyboard of `labels` and queue a next-step handler."""
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(*(KeyboardButton(label) for label in labels))
        self._bot.send_message(message.chat.id, prompt, reply_markup=markup)
        self._bot.register_next_step_handler(message, next_step)

    # /set_target_language
    def handle_set_target_language(self, message: Message) -> None:
        """Handle the /set_target_language command for the bot."""
        self._prompt_choice(
            message,
            "Select target language 👇",
            [lang.title() for lang in SUPPORTED_LANGUAGES],
            self.proceed_set_target_language,
        )

    def proceed_set_target_language(self, message: Message) -> None:
        """Apply the language picked from the keyboard, or report it as unknown."""
        if message.from_user is None or message.text is None:
            self._bot.reply_to(message, "User information or language is missing.")
            return
        set_lang = self._user_repo.set_target_language(
            message.from_user.id,
            message.text,
        )
        if not set_lang:
            msg = "Unknown language"
            self._bot.send_message(message.chat.id, msg)
            return
        markup = ReplyKeyboardRemove()
        self._bot.send_message(
            message.chat.id,
            f"The target language is set to {message.text}.",
            reply_markup=markup,
        )

    # /set_summarizing_model
    def handle_set_summarizing_model(self, message: Message) -> None:
        """Handle the /set_summarizing_model command for the bot."""
        self._prompt_choice(
            message,
            "Select summarizing model 👇",
            list(MODEL_LABELS.values()),
            self.proceed_set_summarizing_model,
        )

    def proceed_set_summarizing_model(self, message: Message) -> None:
        """Apply the model picked from the keyboard, or report it as unknown."""
        if message.from_user is None or message.text is None:
            self._bot.reply_to(message, "User information or model is missing.")
            return
        model_id = MODEL_LABELS_REVERSE.get(message.text)
        if model_id is None:
            self._bot.send_message(message.chat.id, "Unknown model")
            return
        if not self._user_repo.set_summarizing_model(message.from_user.id, model_id):
            self._bot.send_message(
                message.chat.id,
                "Failed to update summarizing model.",
            )
            return
        markup = ReplyKeyboardRemove()
        self._bot.send_message(
            message.chat.id,
            f"The summarizing model is set to {message.text}.",
            reply_markup=markup,
        )

    # /set_prompt_strategy
    def handle_set_prompt_strategy(self, message: Message) -> None:
        """Handle the /set_prompt_strategy command for the bot."""
        self._prompt_choice(
            message,
            "Select summarization strategy 👇",
            list(PROMPT_STRATEGY_LABELS.values()),
            self.proceed_set_prompt_strategy,
        )

    def proceed_set_prompt_strategy(self, message: Message) -> None:
        """Apply the strategy picked from the keyboard, or report it as unknown."""
        if message.from_user is None or message.text is None:
            self._bot.reply_to(message, "User information or strategy is missing.")
            return
        prompt_key = PROMPT_STRATEGY_LABELS_REVERSE.get(message.text)
        if prompt_key is None:
            self._bot.send_message(message.chat.id, "Unknown strategy")
            return
        if not self._user_repo.set_prompt_strategy(message.from_user.id, prompt_key):
            self._bot.send_message(
                message.chat.id,
                "Failed to update prompt strategy.",
            )
            return
        markup = ReplyKeyboardRemove()
        self._bot.send_message(
            message.chat.id,
            f"The prompt strategy is set to {message.text}.",
            reply_markup=markup,
        )

    # /set_thinking_level
    def handle_set_thinking_level(self, message: Message) -> None:
        """Handle the /set_thinking_level command for the bot."""
        self._prompt_choice(
            message,
            "Select thinking level 👇",
            list(THINKING_LEVEL_LABELS.values()),
            self.proceed_set_thinking_level,
        )

    def proceed_set_thinking_level(self, message: Message) -> None:
        """Apply the picked thinking level, or report it as unknown."""
        if message.from_user is None or message.text is None:
            self._bot.reply_to(message, "User information or level is missing.")
            return
        level_key = THINKING_LEVEL_LABELS_REVERSE.get(message.text)
        if level_key is None:
            self._bot.send_message(message.chat.id, "Unknown level")
            return
        if not self._user_repo.set_thinking_level(message.from_user.id, level_key):
            self._bot.send_message(
                message.chat.id,
                "Failed to update thinking level.",
            )
            return
        markup = ReplyKeyboardRemove()
        self._bot.send_message(
            message.chat.id,
            f"The thinking level is set to {message.text}.",
            reply_markup=markup,
        )

    def process_message_content(self, message: Message, user: UsersOrm) -> None:
        """Route a validated message to the handler for its content type."""
        if message.content_type == "audio":
            self._handlers.handle_audio(message, user)
        elif (
            message.content_type == "document"
            and message.document is not None
            and message.document.mime_type in SUPPORTED_DOCUMENT_MIME_TYPES
        ):
            self._handlers.handle_document(message, user)
        elif message.content_type == "video_note":
            self._handlers.handle_video_note(message, user)
        elif message.content_type == "voice":
            self._handlers.handle_voice(message, user)
        elif message.content_type == "video":
            self._handlers.handle_video(message, user)
        else:
            if message.text is None:
                self._bot.send_message(message.chat.id, "No text to process.")
                return
            url = message.text.strip().split(" ", maxsplit=1)[0]
            self._handlers.handle_url(message, user, url)

    # Unified handler
    def handle_message(self, message: Message) -> None:
        """Universal entry point: authorize the sender, then route and trace it.

        Every failure the summarization pipeline raises terminates here — reported to
        Sentry, answered with a user-facing message. The command and settings handlers
        are separate entry points and are not covered by this guard.
        """
        try:
            if message.from_user is None:
                self._bot.reply_to(message, "User information is missing.")
                return
            user = self._user_repo.select_user(message.from_user.id)

            if not user.approved:
                self._bot.send_message(message.chat.id, "You are not approved.")
                return

            with self._tracer.observe_message(user.user_id, message.content_type):
                self.process_message_content(message, user)

        except LimitExceededError as e:
            capture_exception(e)
            self._bot.reply_to(
                message,
                "Daily limit has been exceeded, try again tomorrow.",
            )
        except WebParseError as e:
            capture_exception(e)
            self._bot.reply_to(
                message,
                "Check provided URL, looks like the page is not available.",
            )
        except RetryError as e:
            capture_exception(e)
            self._bot.reply_to(
                message,
                "An error occurred during execution. Please try again in 10 minutes.",
            )
        except Exception as e:
            capture_exception(e)
            self._bot.reply_to(message, f"Unexpected: {type(e).__name__}")

    def _authorized(self, message: Message) -> bool:
        """Gate the settings commands on a known, approved sender."""
        return message.from_user is not None and self._user_repo.check_auth(
            message.from_user.id,
        )

    def register(self) -> None:
        """Register every handler on the bot. Replaces the import-time decorators."""
        self._bot.message_handler(commands=["start"])(self.handle_start)
        self._bot.message_handler(commands=["info"])(self.handle_info)
        self._bot.message_handler(
            commands=["myinfo"],
            func=self._authorized,
        )(self.handle_myinfo)
        self._bot.message_handler(
            commands=["set_target_language"],
            func=self._authorized,
        )(self.handle_set_target_language)
        self._bot.message_handler(
            commands=["set_summarizing_model"],
            func=self._authorized,
        )(self.handle_set_summarizing_model)
        self._bot.message_handler(
            commands=["set_prompt_strategy"],
            func=self._authorized,
        )(self.handle_set_prompt_strategy)
        self._bot.message_handler(
            commands=["set_thinking_level"],
            func=self._authorized,
        )(self.handle_set_thinking_level)
        self._bot.message_handler(
            content_types=["text", "audio", "document", "video_note", "voice", "video"],
        )(self.handle_message)

    def run(self) -> None:
        """Start polling Telegram for updates."""
        self._bot.infinity_polling(timeout=20)

    def shutdown(self) -> None:
        """Remove temp download files and flush the tracer."""
        clean_up(all_downloads=True)
        self._tracer.shutdown()


def build_app(container: Container) -> BotApp:
    """Build the BotApp from the composition root, handlers already registered."""
    app = BotApp(
        container.bot,
        container.user_repo,
        container.quota_manager,
        container.tracer,
        container.handlers,
    )
    app.register()
    return app


if __name__ == "__main__":
    app = build_app(build_container())
    try:
        app.run()
    finally:
        app.shutdown()
