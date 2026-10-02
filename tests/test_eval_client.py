"""Contract tests for the eval harness's use of the bot's `LLMClient`.

A refactor of `src/llm.py` keeps the bot working and breaks compare runs, and no
bot test notices, so these pin the seam from the harness side.
"""

import asyncio
import contextvars
import threading

import pytest

import config
from helpers import load_eval_script
from llm import LLMClient


@pytest.fixture
def eval_client(monkeypatch):
    """The module, loaded fresh so each test can swap its `LLM` singleton."""
    return load_eval_script(monkeypatch, "eval_client")


def test_candidates_run_on_the_bots_client(eval_client):
    """A compare run shares the bot's client, and with it attribution and tracing."""
    assert type(eval_client.LLM) is LLMClient
    assert eval_client.LLM._client is config.openrouter_client


# --- summarize -----------------------------------------------------------------


class FakeLLM:
    """Stands in for the module's `LLM`."""

    def __init__(self, run):
        """Wrap `run` as the fake's `LLM.run`."""
        self.run = run


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


def test_summarize_gives_up_on_a_hung_generation(eval_client, monkeypatch):
    """A hang ends as a TimeoutError that says so, not as a bare `Error: `.

    The worker is never released: like a real hang it is abandoned as a daemon
    thread.
    """
    never = threading.Event()
    monkeypatch.setattr(eval_client, "LLM", FakeLLM(lambda **_: never.wait()))
    monkeypatch.setattr(eval_client, "GENERATION_TIMEOUT", 0.05)

    with pytest.raises(TimeoutError, match=r"gave no answer in 0\.05 s"):
        asyncio.run(eval_client.summarize("vendor/m", "P", "text", "Russian"))


def test_a_worker_released_after_its_timeout_exits_quietly(eval_client, monkeypatch):
    """A hang that ends after its item timed out finds the loop closed and drops out.

    Nobody awaits its answer any more, so it must not die with `Event loop is
    closed` in the log of a finished run.
    """
    release = threading.Event()
    workers, errors = [], []
    spawn_thread = threading.Thread

    def spawn(*args, **kwargs):
        worker = spawn_thread(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(eval_client.threading, "Thread", spawn)
    monkeypatch.setattr(threading, "excepthook", errors.append)
    fake = FakeLLM(lambda **_: release.wait(5) and "late summary")
    monkeypatch.setattr(eval_client, "LLM", fake)
    monkeypatch.setattr(eval_client, "GENERATION_TIMEOUT", 0.05)

    with pytest.raises(TimeoutError):
        asyncio.run(eval_client.summarize("vendor/m", "P", "text", "Russian"))
    release.set()
    workers[0].join(5)

    assert not workers[0].is_alive()
    assert [e.exc_value for e in errors] == []
