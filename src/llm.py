from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

from openai.types.chat import ChatCompletion

from prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from collections.abc import Sequence

    from openai import OpenAI
    from openai.types.chat import (
        ChatCompletionContentPartParam,
        ChatCompletionMessageParam,
    )
    from openai.types.chat.chat_completion_content_part_param import File


class LLMClient:
    """Entry point for every summarization model call, all of them to OpenRouter."""

    def __init__(self, client: OpenAI) -> None:
        """Store the injected `openai` client, pointed at OpenRouter."""
        self._client = client

    def build_file_part(self, file_id: str) -> File:
        """Reference a file already uploaded to OpenRouter's Files API, by its id."""
        return {"type": "file", "file": {"file_id": file_id}}

    def run(
        self,
        content: Sequence[str | File],
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
        parts: list[ChatCompletionContentPartParam] = [
            {"type": "text", "text": part} if isinstance(part, str) else part
            for part in content
        ]
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": parts},
        ]
        reasoning = {"effort": thinking_level}
        if all(isinstance(part, str) for part in content):
            response = self._client.chat.completions.create(
                model=model_id,
                messages=messages,
                extra_body={"reasoning": reasoning},
            )
        else:
            # The generic `post` is what keeps a file run out of Langfuse. See
            # architecture.md → *Tracing (optional), text input only*.
            response = self._client.post(
                "/chat/completions",
                body={"model": model_id, "messages": messages, "reasoning": reasoning},
                cast_to=ChatCompletion,
            )
        if not response.choices or not response.choices[0].message.content:
            raise AttributeError
        return response.choices[0].message.content
