"""Contract tests for the eval harness's subclass of the bot's `LLMClient`.

`EvalLLMClient` overrides one method and leans on `LLMClient`'s private
per-thread state (`_local`, `_models`, `_openrouter_provider`). A refactor of
`src/llm.py` keeps the bot working and breaks compare runs, and no bot test
notices, so these pin the seam from the harness side.
"""

import asyncio
import contextvars
import threading
from types import SimpleNamespace

import pytest
from pydantic_ai.models.openrouter import OpenRouterModel

import config
from helpers import load_eval_script
from llm import LLMClient, OpenRouterCostReporter

CANDIDATE = "vendor/unregistered-candidate"


@pytest.fixture
def eval_client(monkeypatch):
    """The module, loaded fresh so each test can swap its `LLM` singleton."""
    return load_eval_script(monkeypatch, "eval_client")


@pytest.fixture
def factory(mocker):
    """A real provider factory, wrapped so calls can be counted."""
    return mocker.Mock(wraps=config.openrouter_provider_factory)


@pytest.fixture
def llm(eval_client, factory, mocker):
    """An `EvalLLMClient` on a mock Gemini client and the counted factory."""
    return eval_client.EvalLLMClient(
        client=mocker.Mock(),
        openrouter_provider_factory=factory,
    )


def _in_thread(fn):
    """Run `fn` on a fresh thread — one with no event loop — and return its result."""
    outcome = {}

    def target():
        try:
            outcome["value"] = fn()
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(5)
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


# --- build_model ---------------------------------------------------------------


def test_build_model_accepts_an_unregistered_candidate(llm):
    """The override exists because the base class refuses exactly this id."""
    assert CANDIDATE not in config.MODEL_SPECS
    with pytest.raises(KeyError):
        LLMClient.build_model(llm, CANDIDATE)

    model = llm.build_model(CANDIDATE)

    assert isinstance(model, OpenRouterCostReporter)
    assert isinstance(model.wrapped, OpenRouterModel)
    assert model.wrapped.model_name == CANDIDATE


def test_build_model_caches_per_thread_and_shares_the_provider(llm, factory):
    """One model per id and one provider per thread, via the inherited cache."""
    first = llm.build_model(CANDIDATE)
    assert llm.build_model(CANDIDATE) is first
    llm.build_model("vendor/another-candidate")
    assert factory.call_count == 1

    other_thread = _in_thread(lambda: llm.build_model(CANDIDATE))
    assert other_thread is not first
    assert factory.call_count == 2


def test_build_model_matches_what_the_bot_builds_for_openrouter(llm, factory, mocker):
    """A candidate is built the way the bot builds a registered OpenRouter model.

    If `LLMClient.build_model` changes its OpenRouter branch — another wrapper,
    new model settings — a compare run would stop measuring the bot's path.
    """
    registered = next(
        (k for k, s in config.MODEL_SPECS.items() if s.provider == "openrouter"),
        None,
    )
    if registered is None:
        pytest.skip("no OpenRouter model is registered")
    bot = LLMClient(client=mocker.Mock(), openrouter_provider_factory=factory)

    expected = bot.build_model(registered)
    actual = llm.build_model(registered)

    assert type(actual) is type(expected)
    assert type(actual.wrapped) is type(expected.wrapped)
    assert actual.wrapped.settings == expected.wrapped.settings


# --- close_openrouter_provider -------------------------------------------------


def test_close_provider_without_one_is_a_no_op(llm):
    """A thread that never built a model has nothing to close."""
    _in_thread(llm.close_openrouter_provider)


def test_close_provider_without_a_loop_leaves_it_alone(llm, mocker):
    """No loop in the thread means `run_sync` never ran, so nothing opened."""
    close = mocker.AsyncMock()

    def scenario():
        llm._local.openrouter_provider = SimpleNamespace(
            client=SimpleNamespace(close=close),
        )
        llm.close_openrouter_provider()

    _in_thread(scenario)
    close.assert_not_awaited()


def test_close_provider_closes_its_client_and_the_loop(llm, mocker):
    """The HTTP client is closed on the thread's own loop, then the loop itself."""
    close = mocker.AsyncMock()

    def scenario():
        llm._local.openrouter_provider = SimpleNamespace(
            client=SimpleNamespace(close=close),
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        llm.close_openrouter_provider()
        return loop

    loop = _in_thread(scenario)
    close.assert_awaited_once()
    assert loop.is_closed()


# --- summarize -----------------------------------------------------------------


class FakeLLM:
    """Stands in for the module's `LLM`: records runs and provider closes."""

    def __init__(self, run):
        """Wrap `run` as the fake's `LLM.run`."""
        self.run = run
        self.closed = threading.Event()

    def close_openrouter_provider(self):
        """Record that the worker closed its provider."""
        self.closed.set()


@pytest.mark.parametrize(
    ("text", "content"),
    [
        ("the source", ["PROMPT", "the source"]),
        ("  \n", ["PROMPT"]),
    ],
)
def test_summarize_sends_what_summarize_text_sends(
    eval_client,
    monkeypatch,
    text,
    content,
):
    """Prompt and text as two parts, a blank text dropped, the pinned thinking level."""
    calls = []
    fake = FakeLLM(lambda **kw: calls.append(kw) or "summary")
    monkeypatch.setattr(eval_client, "LLM", fake)

    result = asyncio.run(eval_client.summarize("vendor/m", "PROMPT", text, "Russian"))

    assert result == "summary"
    assert calls == [
        {
            "content": content,
            "model_id": "vendor/m",
            "target_language": "Russian",
            "thinking_level": config.DEFAULT_THINKING_LEVEL,
        },
    ]
    assert fake.closed.wait(5)


def test_summarize_runs_in_the_callers_context(eval_client, monkeypatch):
    """The worker sees the caller's context, so the span nests under the item."""
    probe = contextvars.ContextVar("probe")
    monkeypatch.setattr(eval_client, "LLM", FakeLLM(lambda **_: probe.get()))

    async def main():
        probe.set("experiment item")
        return await eval_client.summarize("vendor/m", "P", "text", "Russian")

    assert asyncio.run(main()) == "experiment item"


def test_summarize_reraises_the_models_error(eval_client, monkeypatch):
    """A failed call reaches `run_experiment`, which stores it as `Error: ...`."""

    def fail(**_):
        msg = "boom"
        raise ValueError(msg)

    fake = FakeLLM(fail)
    monkeypatch.setattr(eval_client, "LLM", fake)

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(eval_client.summarize("vendor/m", "P", "text", "Russian"))
    assert fake.closed.wait(5)


def test_summarize_gives_up_on_a_hung_generation(eval_client, monkeypatch):
    """A hang ends as a TimeoutError that says so, not as a bare `Error: `.

    The worker is never released: like a real hang it is abandoned as a daemon
    thread. Releasing it would have it settle onto the already-closed loop.
    """
    never = threading.Event()
    monkeypatch.setattr(eval_client, "LLM", FakeLLM(lambda **_: never.wait()))
    monkeypatch.setattr(eval_client, "GENERATION_TIMEOUT", 0.05)

    with pytest.raises(TimeoutError, match=r"gave no answer in 0\.05 s"):
        asyncio.run(eval_client.summarize("vendor/m", "P", "text", "Russian"))
