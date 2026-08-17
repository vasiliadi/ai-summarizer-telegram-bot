"""The bot's `LLMClient`, unbound from the model registry.

Both stages summarise with a candidate model and both need exactly what the bot
gets — the instrumented agent, the system instruction, the thinking level and
the OpenRouter cost wrapper — for a model that is not in `config.MODEL_SPECS`
and should not be until evaluation says so. That is the only difference:
`build_model` is overridden and nothing else, so a run measures the path the bot
takes rather than a hand-built HTTP call standing next to it.

The judge in `judge.py` deliberately does **not** come through here. It needs a
forced tool call against a JSON schema, which is not a request the bot ever
makes, and its spend is a cost of running the evaluation rather than a property
of the model under evaluation.
"""

from __future__ import annotations

import _bootstrap

REPO = _bootstrap.load()

from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings

import config
from llm import LLMClient, OpenRouterCostReporter

# Shared by screening and compare on purpose. The two stages have to hold this
# axis fixed at the same value or their numbers stop being about the model.
THINKING_LEVEL = config.DEFAULT_THINKING_LEVEL


class EvalLLMClient(LLMClient):
    """`LLMClient` that builds any OpenRouter id, registered or not.

    Only `build_model` changes. The base class looks the id up in
    `config.MODEL_SPECS` and raises `KeyError` for a candidate that is not
    registered yet, which is exactly the model evaluation exists to judge.
    Everything else — the instrumented agent, the system instruction, the
    thinking-level settings and the cost wrapper — is inherited.
    """

    def build_model(self, model_id: str) -> OpenRouterModel:
        """Build (and cache) an OpenRouter model without consulting the registry."""
        if model_id not in self._models:
            self._models[model_id] = OpenRouterCostReporter(
                OpenRouterModel(
                    model_id,
                    provider=self._openrouter_provider,
                    settings=OpenRouterModelSettings(
                        openrouter_usage={"include": True},
                    ),
                ),
            )
        return self._models[model_id]


LLM = EvalLLMClient(
    client=config.gemini_client,
    openrouter_provider=config.openrouter_provider,
)
