"""The bot's `LLMClient`, unbound from the model registry.

A compare run summarises with a candidate model and needs exactly what the bot
gets — the instrumented agent, the system instruction, the thinking level and
the OpenRouter cost wrapper — for a model that is not in `config.MODEL_SPECS`
and should not be until evaluation says so. That is the only difference:
`build_model` is overridden and nothing else, so a run measures the path the bot
takes rather than a hand-built HTTP call standing next to it.

The judges in `judge.py` deliberately do **not** come through here. Opus needs
structured output against a JSON schema, which is not a request the bot ever
makes, JEV is not a chat model at all, and a judge's spend is a cost of running
the evaluation rather than a property of the model under evaluation.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import threading

import _bootstrap

REPO = _bootstrap.load()

from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings

import config
from llm import LLMClient, OpenRouterCostReporter

# One level for every run on purpose: candidates have to hold this axis fixed at
# the same value or their numbers stop being about the model.
THINKING_LEVEL = config.DEFAULT_THINKING_LEVEL

# Seconds one summary may take before the item is given up. Median generation
# is ~20 s and the slowest seen a few minutes, so this only ends a hang.
GENERATION_TIMEOUT = 600


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

    def close_openrouter_provider(self):
        """Close this thread's provider on this thread's event loop, then the loop.

        `run_sync` never enters the model as a context manager, so pydantic-ai
        never closes the provider's HTTP client, and it leaves the loop it made
        open too; `summarize` starts a thread, so a provider and a loop, per
        item. With no loop in this thread `run_sync` was never reached, so the
        client never opened a connection to close.
        """
        provider = getattr(self._local, "openrouter_provider", None)
        if provider is None:
            return
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        loop.run_until_complete(provider.client.close())
        loop.close()


LLM = EvalLLMClient(
    client=config.gemini_client,
    openrouter_provider_factory=config.openrouter_provider_factory,
)


async def summarize(model_id, prompt, text, language):
    """Summarise one dataset item, off the experiment's event loop.

    **An experiment task that calls `LLM.run` directly fails on every item.**
    `run_experiment` awaits the task inside its own running loop, while
    `LLMClient.run` ends in pydantic-ai's `run_sync`, which drives a loop
    itself — so it raises `RuntimeError: This event loop is already running`
    before any request is sent. 150 items fail in about 15 seconds, each
    recorded as an empty output, which is what a model returning nothing looks
    like too.

    A worker thread has no running loop, so `run_sync` builds its own there and
    the bot's synchronous path is reused exactly as the bot runs it rather than
    reimplemented asynchronously beside it. The context is copied into the
    thread, so the generation span still nests under the experiment item and
    `OpenRouterCostReporter` still finds it.
    """
    # Mirrors summarize_text: prompt and content as two parts, and a blank text
    # drops its part rather than sending an empty one.
    content = [prompt, text] if text.strip() else [prompt]
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    context = contextvars.copy_context()

    def settle(result, error):
        if not future.done():  # already cancelled by the timeout
            future.set_exception(error) if error else future.set_result(result)

    def post(result, error):
        # A worker that outlives its timeout can find the experiment's loop
        # already closed. Nobody awaits its answer any more, so it is dropped
        # rather than killing the thread with `Event loop is closed`.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(settle, result, error)

    def work():
        try:
            result = context.run(
                LLM.run,
                content=content,
                model_id=model_id,
                target_language=language,
                thinking_level=THINKING_LEVEL,
            )
        except Exception as exc:
            post(None, exc)
        else:
            post(result, None)
        finally:
            # After settling, so the item is not held up; a timed-out worker
            # still closes it whenever its run finally returns.
            LLM.close_openrouter_provider()

    # A daemon thread rather than `asyncio.to_thread`: a sweep has hung forever
    # on one item with its sockets in CLOSE_WAIT (evals.md, *The harness*), and
    # the default executor's threads are joined at interpreter exit, so a
    # timeout around `to_thread` would move the hang to shutdown instead of
    # ending it. The stuck thread is abandoned; the item is stored as an error.
    threading.Thread(target=work, daemon=True).start()
    try:
        return await asyncio.wait_for(future, GENERATION_TIMEOUT)
    except TimeoutError:
        # A bare TimeoutError has no message, so the stored item read "Error: ".
        msg = f"generation gave no answer in {GENERATION_TIMEOUT} s"
        raise TimeoutError(msg) from None
