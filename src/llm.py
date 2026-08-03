from __future__ import annotations

from functools import lru_cache
from textwrap import dedent
from typing import TYPE_CHECKING, cast

from pydantic_ai import Agent, UploadedFile
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings

from config import MODEL_SPECS, gemini_client
from prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from collections.abc import Sequence

    from google.genai import types
    from pydantic_ai.messages import UploadedFileProviderName, UserContent
    from pydantic_ai.models import Model
    from pydantic_ai.settings import ThinkingLevel


# A single agent serves every call: pydantic-ai takes the model, the instructions
# and the settings per run, so nothing here is model-, language- or user-specific.
_agent: Agent[None, str] = Agent()


@lru_cache
def _build_model(model_id: str) -> Model:
    """Build the provider model for a registered id, cached for reuse."""
    spec = MODEL_SPECS[model_id]
    if spec.provider == "google":
        return GoogleModel(model_id, provider=GoogleProvider(client=gemini_client))
    msg = f"No model builder for provider: {spec.provider}"
    raise ValueError(msg)


class LLMClient:
    """Provider-agnostic entry point for every summarization model call."""

    def build_model(self, model_id: str) -> Model:
        """Return the provider model for a registered model id.

        Args:
            model_id (str): A key of `config.MODEL_SPECS`.

        Returns:
            Model: The pydantic-ai model, shared across calls for that id.

        """
        return _build_model(model_id)

    def build_settings(self, model_id: str, thinking_level: str) -> ModelSettings:
        """Build the per-run settings, adding provider-specific options.

        Google goes through `google_thinking_config` rather than the agnostic
        `thinking` effort: the effort mapping also sets `include_thoughts`, so
        Gemini would generate thought summaries that `run` discards. Passing the
        level straight through keeps the request shape and stays lenient about
        an unrecognized level, which the provider decides on rather than us.

        Args:
            model_id (str): A key of `config.MODEL_SPECS`.
            thinking_level (str): One of `config.ALLOWED_THINKING_LEVELS`.

        Returns:
            ModelSettings: Settings carrying the thinking level.

        """
        if MODEL_SPECS[model_id].provider == "google":
            return GoogleModelSettings(
                google_thinking_config={
                    # Cast, not types.ThinkingLevel(...): an unrecognized level
                    # stays a plain string for the provider to rule on.
                    "thinking_level": cast("types.ThinkingLevel", thinking_level),
                },
            )
        return ModelSettings(thinking=cast("ThinkingLevel", thinking_level.lower()))

    def build_uploaded_file(self, model_id: str, file: types.File) -> UploadedFile:
        """Reference a file already uploaded to the provider's file API.

        Args:
            model_id (str): A key of `config.MODEL_SPECS`.
            file (types.File): The processed file returned by
                `services.upload_and_wait_for_file`.

        Returns:
            UploadedFile: A message part pointing at the stored file. For Google
                the identifier is the file's uri, not its name.

        Raises:
            ValueError: If the model is not served by the provider that stores
                the file. `services.upload_and_wait_for_file` only ever uploads
                to Gemini, so referencing it from anything else would hand the
                model an id it cannot resolve.

        """
        spec = MODEL_SPECS[model_id]
        if spec.provider != "google":
            msg = f"Cannot reference a Gemini file from a {spec.provider} model"
            raise ValueError(msg)
        return UploadedFile(
            file_id=cast("str", file.uri),
            media_type=cast("str", file.mime_type),
            provider_name=cast(
                "UploadedFileProviderName",
                self.build_model(model_id).system,
            ),
        )

    def run(
        self,
        content: str | Sequence[UserContent],
        model_id: str,
        target_language: str,
        thinking_level: str,
    ) -> str:
        """Run one summarization request and return the model's text output.

        Args:
            content (str | Sequence[UserContent]): The prompt, either on its own
                or followed by the file parts it refers to.
            model_id (str): A key of `config.MODEL_SPECS`.
            target_language (str): The language to write the summary in.
            thinking_level (str): One of `config.ALLOWED_THINKING_LEVELS`.

        Returns:
            str: The generated text.

        Raises:
            AttributeError: If the model returns an empty response.

        """
        instructions = dedent(
            SYSTEM_INSTRUCTION.format(language=target_language),
        ).strip()
        result = _agent.run_sync(
            content,
            model=self.build_model(model_id),
            instructions=instructions,
            model_settings=self.build_settings(
                model_id,
                thinking_level=thinking_level,
            ),
        )
        if not result.output:
            raise AttributeError
        return result.output


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

llm_client = LLMClient()


# ---------------------------------------------------------------------------
# Module-level aliases — preserve the existing public API
# ---------------------------------------------------------------------------

build_model = llm_client.build_model
build_settings = llm_client.build_settings
build_uploaded_file = llm_client.build_uploaded_file
run_model = llm_client.run
