import json

import httpx
import langfuse.openai
import pytest
from openai import OpenAI

from config import ALLOWED_THINKING_LEVELS
from llm import LLMClient

FILE_PART = {"type": "file", "file": {"file_id": "or_file_mock123"}}


def _completion(content="A summary."):
    """A chat-completions reply as OpenRouter sends it, cost included."""
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": "openai/gpt-6-luna",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            },
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "total_tokens": 10,
            "cost": 0.0123,
        },
    }


def _make_client(reply):
    """Return (llm_client, requests): a real `openai` client on a canned reply."""
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=reply)

    client = OpenAI(
        api_key="mock_openrouter_key",
        base_url="https://openrouter.ai/api/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return LLMClient(client), requests


def test_build_file_part_references_the_upload_by_id():
    """Test a document reaches the model as OpenRouter's `file_id` part."""
    llm_client, _ = _make_client(_completion())

    assert llm_client.build_file_part("or_file_mock123") == FILE_PART


def test_run_sends_the_expected_text_request():
    """Test run against the real SDK: what OpenRouter receives for a text run."""
    llm_client, requests = _make_client(_completion())

    result = llm_client.run(
        content=["Summarize this.", "The content."],
        model_id="openai/gpt-6-luna",
        target_language="Ukrainian",
        thinking_level="medium",
    )

    assert result == "A summary."
    (request,) = requests
    assert request.url == "https://openrouter.ai/api/v1/chat/completions"
    body = json.loads(request.content)
    system, user = body.pop("messages")
    assert body == {"model": "openai/gpt-6-luna", "reasoning": {"effort": "medium"}}
    assert system["role"] == "system"
    assert "Ukrainian" in system["content"]
    assert user == {
        "role": "user",
        "content": [
            {"type": "text", "text": "Summarize this."},
            {"type": "text", "text": "The content."},
        ],
    }


def test_run_sends_the_expected_file_request():
    """Test a file run carries the same body, with the upload referenced by id."""
    llm_client, requests = _make_client(_completion())

    result = llm_client.run(
        content=["Summarize this.", FILE_PART],
        model_id="x-ai/grok-4.7",
        target_language="English",
        thinking_level="high",
    )

    assert result == "A summary."
    (request,) = requests
    assert request.url == "https://openrouter.ai/api/v1/chat/completions"
    body = json.loads(request.content)
    system, user = body.pop("messages")
    assert body == {"model": "x-ai/grok-4.7", "reasoning": {"effort": "high"}}
    assert system["role"] == "system"
    assert user["content"] == [{"type": "text", "text": "Summarize this."}, FILE_PART]


@pytest.mark.parametrize("thinking_level", ALLOWED_THINKING_LEVELS)
@pytest.mark.parametrize(
    "content",
    [["Summarize this."], ["Summarize this.", FILE_PART]],
)
def test_run_passes_every_allowed_level_as_reasoning_effort(thinking_level, content):
    """Test each selectable level reaches OpenRouter untranslated, on both paths."""
    llm_client, requests = _make_client(_completion())

    llm_client.run(
        content=content,
        model_id="openai/gpt-6-luna",
        target_language="English",
        thinking_level=thinking_level,
    )

    assert json.loads(requests[0].content)["reasoning"] == {"effort": thinking_level}


def test_run_instructions_are_dedented():
    """Test the system instruction is dedented and stripped before being sent."""
    llm_client, requests = _make_client(_completion())

    llm_client.run(
        content=["Summarize this."],
        model_id="openai/gpt-6-luna",
        target_language="English",
        thinking_level="high",
    )

    instructions = json.loads(requests[0].content)["messages"][0]["content"]
    assert not instructions.startswith((" ", "\n"))
    assert "\n    " not in instructions


@pytest.mark.parametrize(
    "reply",
    [
        _completion(content=""),
        _completion(content=None),
        # OpenRouter can answer 200 with an error body and no choices at all.
        {"error": {"message": "Provider returned error", "code": 502}},
    ],
)
@pytest.mark.parametrize(
    "content",
    [["Summarize this."], ["Summarize this.", FILE_PART]],
)
def test_run_raises_on_empty_output(reply, content):
    """Test an empty response raises AttributeError, which the retries catch."""
    llm_client, _ = _make_client(reply)

    with pytest.raises(AttributeError):
        llm_client.run(
            content=content,
            model_id="openai/gpt-6-luna",
            target_language="English",
            thinking_level="high",
        )


def test_run_traces_a_text_run_with_the_cost_openrouter_charged(mocker):
    """Test a text run becomes a Langfuse generation carrying OpenRouter's cost.

    The drop-in reads `usage.cost` off the reply; nothing in this codebase
    reports cost, so a langfuse bump that stops reading it fails here.
    """
    mock_get_client = mocker.patch.object(langfuse.openai, "get_client")
    llm_client, _ = _make_client(_completion())

    llm_client.run(
        content=["Summarize this.", "The content."],
        model_id="openai/gpt-6-luna",
        target_language="English",
        thinking_level="high",
    )

    langfuse_client = mock_get_client.return_value
    started = langfuse_client.start_observation.call_args.kwargs
    assert started["as_type"] == "generation"
    assert started["model"] == "openai/gpt-6-luna"
    assert started["input"][1]["content"] == [
        {"type": "text", "text": "Summarize this."},
        {"type": "text", "text": "The content."},
    ]
    finished = langfuse_client.start_observation.return_value.update.call_args.kwargs
    assert finished["output"]["content"] == "A summary."
    assert finished["cost_details"] == {"total": 0.0123}
    assert finished["usage_details"]["total_tokens"] == 10


def test_run_keeps_a_file_run_out_of_langfuse(mocker):
    """Test a run carrying a file part never reaches the Langfuse drop-in.

    The trace would hold token usage and a file id in place of the content.
    """
    mock_get_client = mocker.patch.object(langfuse.openai, "get_client")
    llm_client, requests = _make_client(_completion())

    result = llm_client.run(
        content=["Summarize this.", FILE_PART],
        model_id="openai/gpt-6-luna",
        target_language="English",
        thinking_level="high",
    )

    assert result == "A summary."
    assert len(requests) == 1
    mock_get_client.assert_not_called()
