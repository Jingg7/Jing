from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, Sequence

from openai import AsyncOpenAI

from .config import LLMConfig


@dataclass(frozen=True)
class ToolCallDelta:
    index: int
    id: str | None = None
    name: str | None = None
    arguments: str | None = None


@dataclass(frozen=True)
class ChatDelta:
    content: str | None = None
    tool_call: ToolCallDelta | None = None


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


class ChatModel(Protocol):
    def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> AsyncIterator[ChatDelta]:
        ...


class OpenAIChatModel:
    def __init__(self, config: LLMConfig):
        self._client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        self._model = config.model

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> AsyncIterator[ChatDelta]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[dict(message) for message in messages],
            tools=[dict(tool) for tool in tools],
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield ChatDelta(content=delta.content)
            if delta.tool_calls:
                for tool_call in delta.tool_calls:
                    function = tool_call.function
                    yield ChatDelta(
                        tool_call=ToolCallDelta(
                            index=tool_call.index,
                            id=tool_call.id,
                            name=function.name if function else None,
                            arguments=function.arguments if function else None,
                        )
                    )
