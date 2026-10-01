from __future__ import annotations

import threading
from textwrap import dedent
from typing import TYPE_CHECKING, cast

from opentelemetry.trace import get_current_span
from pydantic_ai import Agent, UploadedFile
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings

from config import MODEL_SPECS
from prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from google import genai
    from google.genai import types
    from pydantic_ai.messages import (
        ModelMessage,
        ModelResponse,
        UploadedFileProviderName,
        UserContent,
    )
    from pydantic_ai.models import Model, ModelRequestParameters
    from pydantic_ai.providers.openrouter import OpenRouterProvider
    from pydantic_ai.settings import ThinkingLevel


class OpenRouterCostReporter(WrapperModel):
    """Publishes the cost OpenRouter charged onto the generation span.

    Must wrap the model inside the instrumentation; see architecture.md →
    *Tracing (optional), text input only*.
    """

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Run the wrapped request, then record its cost on the current span."""
        response = await super().request(
            messages,
            model_settings,
            model_request_parameters,
        )
        cost = (response.provider_details or {}).get("cost")
        if cost is not None:
            get_current_span().set_attribute("gen_ai.usage.cost", float(cost))
        return response


class LLMClient:
    """Provider-agnostic entry point for every summarization model call."""

    def __init__(
        self,
        client: genai.Client,
        openrouter_provider_factory: Callable[[], OpenRouterProvider],
    ) -> None:
        """Store the injected Gemini client and OpenRouter provider factory."""
        self._client = client
        self._openrouter_provider_factory = openrouter_provider_factory
        self._local = threading.local()
        # Model, instructions and settings are per run, so the two agents differ
        # only in instrumentation: uploaded-file runs go through the untraced one.
        self._agent: Agent[None, str] = Agent()
        self._untraced_agent: Agent[None, str] = Agent()
        self._untraced_agent.instrument = False

    @property
    def _openrouter_provider(self) -> OpenRouterProvider:
        """Return the calling thread's OpenRouter provider, built on first use.

        See architecture.md → *One OpenRouter provider per thread*.
        """
        if not hasattr(self._local, "openrouter_provider"):
            self._local.openrouter_provider = self._openrouter_provider_factory()
        return self._local.openrouter_provider

    @property
    def _models(self) -> dict[str, Model]:
        """Return this thread's model cache: an OpenRouter model holds its provider."""
        if not hasattr(self._local, "models"):
            self._local.models = {}
        return self._local.models

    @staticmethod
    def _is_text_only(content: Sequence[UserContent]) -> bool:
        """Whether every part is text, so the run carries no uploaded file."""
        return all(isinstance(part, str) for part in content)

    def _build_openrouter_model(self, model_id: str) -> Model:
        """Build an OpenRouter model that reports its cost to the trace."""
        # Usage accounting rides on the model, not `build_settings`. See
        # architecture.md → *Tracing (optional), text input only*.
        return OpenRouterCostReporter(
            OpenRouterModel(
                model_id,
                provider=self._openrouter_provider,
                settings=OpenRouterModelSettings(openrouter_usage={"include": True}),
            ),
        )

    def build_model(self, model_id: str) -> Model:
        """Return the pydantic-ai model for a registered id, cached per thread."""
        if model_id not in self._models:
            spec = MODEL_SPECS[model_id]
            if spec.provider == "google":
                model: Model = GoogleModel(
                    model_id,
                    provider=GoogleProvider(client=self._client),
                )
            elif spec.provider == "openrouter":
                model = self._build_openrouter_model(model_id)
            else:
                msg = f"No model builder for provider: {spec.provider}"
                raise ValueError(msg)
            self._models[model_id] = model
        return self._models[model_id]

    def build_settings(self, thinking_level: str) -> ModelSettings:
        """Build the per-run settings from the agnostic thinking effort.

        Owns no per-provider mapping; see architecture.md → *Thinking levels are
        pydantic-ai's, translated by pydantic-ai*.
        """
        return ModelSettings(thinking=cast("ThinkingLevel", thinking_level))

    def build_uploaded_file(self, model_id: str, file: types.File) -> UploadedFile:
        """Reference a file already uploaded to Gemini's file API, by its uri.

        Raises:
            ValueError: If the model is not a Google one, which cannot resolve it.

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
        content: Sequence[UserContent],
        model_id: str,
        target_language: str,
        thinking_level: str,
    ) -> str:
        """Run one summarization request and return the model's text output.

        `content` is the prompt followed by the text or file parts it refers to.

        Raises:
            AttributeError: If the model returns an empty response.

        """
        instructions = dedent(
            SYSTEM_INSTRUCTION.format(language=target_language),
        ).strip()
        agent = self._agent if self._is_text_only(content) else self._untraced_agent
        result = agent.run_sync(
            content,
            model=self.build_model(model_id),
            instructions=instructions,
            model_settings=self.build_settings(thinking_level=thinking_level),
        )
        if not result.output:
            raise AttributeError
        return result.output
