from __future__ import annotations

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

    from google import genai
    from google.genai import types
    from pydantic_ai.messages import UploadedFileProviderName, UserContent
    from pydantic_ai.models import Model
    from pydantic_ai.settings import ThinkingLevel


class LLMClient:
    """Provider-agnostic entry point for every summarization model call."""

    def __init__(self, client: genai.Client) -> None:
        """Store the injected Gemini client and this client's model cache."""
        self._client = client
        # A single agent serves every call: pydantic-ai takes the model, the
        # instructions and the settings per run, so nothing here is model-,
        # language- or user-specific.
        self._agent: Agent[None, str] = Agent()
        self._models: dict[str, Model] = {}

    def build_model(self, model_id: str) -> Model:
        """Return the pydantic-ai model for a registered id, shared across calls."""
        if model_id not in self._models:
            spec = MODEL_SPECS[model_id]
            if spec.provider != "google":
                msg = f"No model builder for provider: {spec.provider}"
                raise ValueError(msg)
            self._models[model_id] = GoogleModel(
                model_id,
                provider=GoogleProvider(client=self._client),
            )
        return self._models[model_id]

    def build_settings(self, model_id: str, thinking_level: str) -> ModelSettings:
        """Build the per-run settings, adding provider-specific options.

        Google goes through `google_thinking_config` rather than the agnostic
        `thinking` effort: the effort mapping also sets `include_thoughts`, so
        Gemini would generate thought summaries that `run` discards. Passing the
        level straight through keeps the request shape and stays lenient about
        an unrecognized level, which the provider decides on rather than us.
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

        `content` is the prompt on its own, or the prompt followed by the file
        parts it refers to.

        Raises:
            AttributeError: If the model returns an empty response.

        """
        instructions = dedent(
            SYSTEM_INSTRUCTION.format(language=target_language),
        ).strip()
        result = self._agent.run_sync(
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


# Module-level singleton and aliases — transitional shim (STG-135).
# summary.py still imports build_uploaded_file and run_model; removed once
# every consumer is migrated to constructor injection.
llm_client = LLMClient(gemini_client)

build_model = llm_client.build_model
build_settings = llm_client.build_settings
build_uploaded_file = llm_client.build_uploaded_file
run_model = llm_client.run
