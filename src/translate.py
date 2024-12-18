from textwrap import dedent

from google.genai import types

from config import MODEL_ID_FOR_TRANSLATION, SAFETY_SETTINGS, gemini_client
from prompts import TRANSLATION_SYSTEM_INSTRUCTION


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
        ),
    )
    return translation.text
