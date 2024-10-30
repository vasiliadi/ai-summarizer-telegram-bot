from google.api_core import retry

from config import gemini_flash_model


@retry.Retry(predicate=retry.if_transient_error, initial=10, timeout=120)
def translate(text: str, target_language: str) -> str:
    prompt = f"Translate into {target_language}: {text}"
    translation = gemini_flash_model.generate_content(prompt)
    return translation.text
