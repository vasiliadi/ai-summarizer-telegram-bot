import time
from typing import TYPE_CHECKING

from telebot.util import smart_split
from telegramify_markdown import markdownify

from config import (
    DAILY_LIMIT_KEY,
    MINUTE_LIMIT_KEY,
    bot,
    per_day_limit,
    per_minute_limit,
)
from exceptions import LimitExceededError
from translate import translate

if TYPE_CHECKING:
    from telebot.types import Message

    from models import UsersOrm


def send_answer(message: "Message", user: "UsersOrm", answer: str) -> None:
    answer_md = markdownify(answer)
    if len(answer_md) > 4000:  # 4096 limit # noqa: PLR2004
        chunks = smart_split(answer, 4000)
        for text in chunks:
            text_md = markdownify(text)
            bot.reply_to(message, text_md, parse_mode="MarkdownV2")
            time.sleep(1)
    else:
        bot.reply_to(message, answer_md, parse_mode="MarkdownV2")

    if user.use_translator:
        translation = translate(answer, target_language=user.target_language)
        translation_md = markdownify(translation)
        if len(translation_md) > 4096:  # noqa: PLR2004
            chunks = smart_split(translation, 4000)
            for text in chunks:
                text_md = markdownify(text)
                bot.reply_to(message, text_md, parse_mode="MarkdownV2")
                time.sleep(1)
        else:
            bot.reply_to(message, translation_md, parse_mode="MarkdownV2")


def check_quota(quantity: int = 1) -> bool:
    rpd = per_day_limit.check(DAILY_LIMIT_KEY, quantity=quantity)
    if rpd.limited:
        raise LimitExceededError("The daily limit for requests has been exceeded")
    rpm = per_minute_limit.check(MINUTE_LIMIT_KEY, quantity=quantity)
    if rpm.limited:
        time_to_reset = max(0, rpm.reset_after.total_seconds())
        time.sleep(time_to_reset)
    return True
