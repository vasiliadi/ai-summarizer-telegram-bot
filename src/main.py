from telebot.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telebot.util import smart_split
from telegramify_markdown import markdownify

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
from summary import summarize
from translate import translate
from utils import clean_up


@bot.message_handler(commands=["start"])
def handle_start(message: Message) -> Message:
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
def handle_info(message: Message) -> Message:
    bot.send_message(message.chat.id, f"{message.from_user.id}")


@bot.message_handler(
    commands=["toggle_transcription"],
    func=lambda message: check_auth(message.from_user.id),
)
def handle_toggle_transcription(message: Message) -> Message:
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
def handle_toggle_translation(message: Message) -> Message:
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
def handle_toggle_yt_transcription(message: Message) -> Message:
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
def handle_set_target_language(message: Message) -> None:
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    languages = [KeyboardButton(lang.title()) for lang in SUPPORTED_LANGUAGES]
    markup.add(*languages)

    bot.send_message(message.chat.id, "Select target language 👇", reply_markup=markup)
    bot.register_next_step_handler(message, proceed_set_target_language)


def proceed_set_target_language(message: Message) -> Message:
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
    regexp=r"^https:\/\/[\S]*",
    func=lambda message: check_auth(message.from_user.id),
)
def handle_regexp(message: Message) -> Message:
    try:
        user = select_user(message.from_user.id)
        answer = summarize(
            data=message.text.strip(),
            use_transcription=user.use_transcription,
            use_yt_transcription=user.use_yt_transcription,
        )
        answer = markdownify(answer)

        if len(answer) > 4000:  # 4096 limit # noqa
            chunks = smart_split(answer, 4000)
            for text in chunks:
                bot.reply_to(message, text, parse_mode="MarkdownV2")
        else:
            bot.reply_to(message, answer, parse_mode="MarkdownV2")

        if user.use_translator:
            translation = translate(answer, target_language=user.target_language)
            translation = markdownify(translation)
            if len(translation) > 4096:  # noqa
                chunks = smart_split(translation, 4096)
                for text in chunks:
                    bot.reply_to(message, text, parse_mode="MarkdownV2")
            else:
                bot.reply_to(message, translation, parse_mode="MarkdownV2")

    except Exception as e:
        bot.reply_to(message, f"Unexpected: {e}")
    finally:
        clean_up()


@bot.message_handler(content_types=["text"])
def handle_text(message: Message) -> Message:
    user = select_user(message.from_user.id)
    if not user.approved:
        bot.send_message(message.chat.id, "You are not approved.")
    else:
        bot.send_message(message.chat.id, "No data to proceed.")


if __name__ == "__main__":
    bot.infinity_polling(timeout=20)
