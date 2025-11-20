import logging
import time
from typing import TYPE_CHECKING

from rush.exceptions import DataChangedInStoreError
from telebot.util import smart_split
from telegramify_markdown import markdownify
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import (
    DAILY_LIMIT_KEY,
    MINUTE_LIMIT_KEY,
    bot,
    per_day_limit,
    per_minute_limit,
)
from exceptions import LimitExceededError

if TYPE_CHECKING:
    from telebot.types import Message

logger = logging.getLogger(__name__)


def send_answer(message: "Message", answer: str) -> None:
    """Send a response message to the user.

    This function handles sending messages through the Telegram bot, including:
    - Converting the message to Markdown format
    - Splitting long messages into chunks if they exceed Telegram's length limit

    Args:
        message (Message): The original Telegram message to reply to
        answer (str): The text content to send as a response

    Returns:
        None

    Note:
        - Messages longer than 4000 characters are automatically split
        - There is a 1-second delay between sending chunks of split messages

    """
    answer_md = markdownify(answer)
    if len(answer_md) > 4000:  # 4096 limit # noqa: PLR2004
        chunks = smart_split(answer, 4000)
        for text in chunks:
            text_md = markdownify(text)
            bot.reply_to(message, text_md, parse_mode="MarkdownV2")
            time.sleep(1)
    else:
        bot.reply_to(message, answer_md, parse_mode="MarkdownV2")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(
        (DataChangedInStoreError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def check_quota(quantity: int = 1) -> bool:
    """Check if the request is within rate limits and handle any delays.

    This function checks both daily and per-minute rate limits. If the daily limit
    is exceeded, it raises an exception. If the per-minute limit is exceeded, it
    waits until the limit resets.

    Args:
        quantity (int, optional): Number of quota units to check. Defaults to 1.

    Returns:
        bool: True if the request is allowed to proceed.

    Raises:
        LimitExceededError: If the daily request limit has been exceeded.

    Note:
        - The function will automatically sleep if the per-minute limit is reached
        - Daily limits cannot be bypassed and will raise an exception

    """
    rpd = per_day_limit.check(DAILY_LIMIT_KEY, quantity=quantity)
    if rpd.limited:
        msg = "The daily limit for requests has been exceeded"
        raise LimitExceededError(msg)
    rpm = per_minute_limit.check(MINUTE_LIMIT_KEY, quantity=quantity)
    if rpm.limited:
        time_to_reset = max(0, rpm.reset_after.total_seconds())
        time.sleep(time_to_reset)
    return True
