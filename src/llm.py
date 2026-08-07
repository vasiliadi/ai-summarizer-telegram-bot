from __future__ import annotations

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
    from collections.abc import Sequence

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

    Langfuse reads a generation's cost from `gen_ai.usage.cost`, or else infers
    it by matching the model id against a model definition. Only the Gemini ids
    match one, so without this every OpenRouter generation reaches Langfuse with
    token counts and no cost, which is exactly the number the traces exist to
    compare. pydantic-ai's own estimate is no substitute: it lands on
    `operation.cost`, which Langfuse does not read, and its price table
    (`genai-prices`) has no entry for half the registered OpenRouter ids.

    The cost is OpenRouter's own, reported per request in `provider_details`
    because `build_model` asks for usage accounting, so it needs no price table
    here and follows whatever OpenRouter actually billed.

    This has to be a wrapper, and it has to sit inside the instrumented model:
    pydantic-ai opens the generation span around `wrapped.request` and closes it
    before `Agent.run_sync` returns, so nothing after the run can still reach it.
    On an untraced run `get_current_span` returns a non-recording span and the
    write is a no-op.
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
        openrouter_provider: OpenRouterProvider,
    ) -> None:
        """Store the injected providers and this client's model cache."""
        self._client = client
        self._openrouter_provider = openrouter_provider
        # Neither agent is model-, language- or user-specific: pydantic-ai takes
        # the model, the instructions and the settings per run. They differ only
        # in whether instrumentation is on.
        self._agent: Agent[None, str] = Agent()
        # Runs that carry an UploadedFile go through an agent with instrumentation
        # off: pydantic-ai would record the file pointer as the input, producing a
        # Langfuse generation with token usage but no content behind it.
        self._untraced_agent: Agent[None, str] = Agent()
        self._untraced_agent.instrument = False
        self._models: dict[str, Model] = {}

    @staticmethod
    def _is_text_only(content: str | Sequence[UserContent]) -> bool:
        """Broader than `isinstance(content, str)`: a multi-part text prompt counts."""
        if isinstance(content, str):
            return True
        return all(isinstance(part, str) for part in content)

    def build_model(self, model_id: str) -> Model:
        """Return the pydantic-ai model for a registered id, shared across calls."""
        if model_id not in self._models:
            spec = MODEL_SPECS[model_id]
            if spec.provider == "google":
                model: Model = GoogleModel(
                    model_id,
                    provider=GoogleProvider(client=self._client),
                )
            elif spec.provider == "openrouter":
                # Usage accounting is what makes OpenRouter report the cost
                # `OpenRouterCostReporter` forwards to the trace. It belongs on
                # the model rather than in `build_settings`, which owns no
                # provider branch; pydantic-ai merges the two.
                model = OpenRouterCostReporter(
                    OpenRouterModel(
                        model_id,
                        provider=self._openrouter_provider,
                        settings=OpenRouterModelSettings(
                            openrouter_usage={"include": True},
                        ),
                    ),
                )
            else:
                msg = f"No model builder for provider: {spec.provider}"
                raise ValueError(msg)
            self._models[model_id] = model
        return self._models[model_id]

    def build_settings(self, thinking_level: str) -> ModelSettings:
        """Build the per-run settings from the agnostic thinking effort.

        Deliberately owns no mapping: `thinking_level` is a pydantic-ai
        `ThinkingEffort`, and each provider's model translates it. Two
        consequences worth knowing rather than rediscovering:

        Gemini receives `include_thoughts=True` — it is hard-coded alongside the
        level in pydantic-ai's Google translation, so Gemini generates thought
        summaries that `run` then discards. Reaching that translation any other
        way is not possible; owning the mapping here to avoid it is what this
        deliberately does not do.

        `xhigh` is indistinguishable from `high` on both registered providers
        (Gemini has no XHIGH; OpenRouter's `reasoning.effort` stops at high). It
        is offered for a provider that distinguishes it, not for today.

        An unrecognized level survives this call but raises `KeyError` when the
        request is built. Only a stale `users.thinking_level` can reach that,
        since `database.set_thinking_level`'s allow-list is the only writer.
        """
        return ModelSettings(thinking=cast("ThinkingLevel", thinking_level))

    def build_uploaded_file(self, model_id: str, file: types.File) -> UploadedFile:
        """Reference a file already uploaded to the provider's file API.

        Returns:
            UploadedFile: A message part pointing at the stored file. For Google
                the identifier is the file's uri, not its name.

        Raises:
            ValueError: If the model is not served by the provider that stores
                the file. `services.GeminiHelper.upload_and_wait_for_file` only
                ever uploads to Gemini, so referencing it from anything else
                would hand the model an id it cannot resolve.

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
