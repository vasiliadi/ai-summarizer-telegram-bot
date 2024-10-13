from google.api_core import retry

from config import gemini_flash_model


@retry.Retry(predicate=retry.if_transient_error)
def translate(text, target_language):
    prompt = f"Translate into {target_language}: {text}"
    translation = gemini_flash_model.generate_content(prompt)
    return translation.text
