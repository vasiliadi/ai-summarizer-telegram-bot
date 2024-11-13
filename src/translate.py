from google.api_core import retry

from config import gemini_flash_model


@retry.Retry(predicate=retry.if_transient_error, initial=10, timeout=120)
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
    translation = gemini_flash_model.generate_content(prompt)
    return translation.text
