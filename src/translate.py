import logging
from textwrap import dedent

from google.genai import types
from google.genai.errors import ClientError, ServerError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import MODEL_ID_FOR_TRANSLATION, SAFETY_SETTINGS, gemini_client
from prompts import TRANSLATION_SYSTEM_INSTRUCTION

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(
        (ServerError, ClientError),
    ),
    before_sleep=before_sleep_log(logger, log_level=logging.WARNING),
    reraise=False,
)
def translate(text: str, target_language: str) -> str:
    """Translates text into the specified target language using Gemini model.

    This function uses the Gemini Flash model to perform translation and includes
    automatic retry logic for handling transient errors.

    Args:
        text (str): The text to be translated.
        target_language (str): The language to translate the text into.

    Returns:
        str: The translated text.

    """
    prompt = f"Translate into {target_language}: {text}"
    translation = gemini_client.models.generate_content(
        model=MODEL_ID_FOR_TRANSLATION,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=dedent(TRANSLATION_SYSTEM_INSTRUCTION).strip(),
            safety_settings=SAFETY_SETTINGS,
            response_mime_type="text/plain",
            max_output_tokens=8192,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return translation.text
