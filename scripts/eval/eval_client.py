"""The bot's `LLMClient`, unbound from the model registry.

See evals.md → *The candidate summarises through the bot's client; the judges do not*.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import threading

import _bootstrap

REPO = _bootstrap.load()

import config
from llm import LLMClient

# One level for every run on purpose: candidates have to hold this axis fixed at
# the same value or their numbers stop being about the model.
THINKING_LEVEL = config.DEFAULT_THINKING_LEVEL

# Seconds one summary may take before the item is given up. Median generation
# is ~20 s and the slowest seen a few minutes, so this only ends a hang.
GENERATION_TIMEOUT = 600


class EvalLLMClient(LLMClient):
    """`LLMClient` that builds any OpenRouter id, registered or not."""

    def build_model(self, model_id: str):
        """Build (and cache) an OpenRouter model without consulting the registry."""
        if model_id not in self._models:
            self._models[model_id] = self._build_openrouter_model(model_id)
        return self._models[model_id]

    def close_openrouter_provider(self):
        """Close this thread's provider on this thread's event loop, then the loop.

        `run_sync` closes neither; with no loop here it never ran, so nothing is open.
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
    """Summarise one dataset item on a worker thread, off the experiment's event loop.

    Calling `LLM.run` directly fails every item; see evals.md → *The candidate
    summarises through the bot's client; the judges do not*.
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
        # A worker that outlives its timeout can find the loop closed; nobody awaits
        # its answer, so drop it rather than die on `Event loop is closed`.
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

    # A daemon thread, not `asyncio.to_thread`, so a hang ends at the timeout. See
    # evals.md → *The harness*.
    threading.Thread(target=work, daemon=True).start()
    try:
        return await asyncio.wait_for(future, GENERATION_TIMEOUT)
    except TimeoutError:
        # A bare TimeoutError has no message, so the stored item read "Error: ".
        msg = f"generation gave no answer in {GENERATION_TIMEOUT} s"
        raise TimeoutError(msg) from None
