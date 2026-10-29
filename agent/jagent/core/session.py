from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from .events import (
    AgentEvent,
    AssistantCompleted,
    AssistantStarted,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCompleted,
)
from .history import HistoryStore
from .llm import ChatModel, ToolCall, ToolCallDelta
from .tools.registry import ToolRegistry


class _ToolCallBuilder:
    def __init__(self, index: int):
        self.index = index
        self.id = ""
        self.name = ""
        self.arguments = ""

    def apply(self, delta: ToolCallDelta) -> None:
        if delta.id:
            self.id = delta.id
        if delta.name:
            self.name = delta.name
        if delta.arguments:
            self.arguments += delta.arguments

    def build(self) -> ToolCall:
        return ToolCall(
            id=self.id or f"call_{self.index}",
            name=self.name,
            arguments=self.arguments or "{}",
        )


def _parse_arguments(raw: str) -> tuple[dict[str, Any], str | None]:
    if not raw or not raw.strip():
        return {}, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"参数解析失败: {exc}"
    if not isinstance(value, dict):
        return {}, "参数解析失败: 工具参数必须是 JSON 对象"
    return value, None


class AgentSession:
    def __init__(
        self,
        model: ChatModel,
        registry: ToolRegistry,
        history: HistoryStore | None = None,
        system_prompt: str | None = None,
    ):
        self._model = model
        self._registry = registry
        self._history = history
        self._messages: list[dict[str, Any]] = (
            history.load() if history is not None else []
        )
        if system_prompt and not any(
            message.get("role") == "system" for message in self._messages
        ):
            self._messages.insert(0, {"role": "system", "content": system_prompt})

    @property
    def messages(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(message) for message in self._messages)

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self._registry.schemas()

    async def _save_history(self) -> None:
        if self._history is not None:
            await asyncio.to_thread(self._history.save, self._messages)

    async def send(self, prompt: str) -> AsyncIterator[AgentEvent]:
        prompt = prompt.strip()
        if not prompt:
            return
        self._messages.append({"role": "user", "content": prompt})
        try:
            final_content = ""
            while True:
                yield AssistantStarted()
                content_parts: list[str] = []
                builders: dict[int, _ToolCallBuilder] = {}
                async for delta in self._model.stream(
                    self._messages,
                    self._registry.schemas(),
                ):
                    if delta.content:
                        content_parts.append(delta.content)
                        yield TextDelta(delta.content)
                    if delta.tool_call:
                        builder = builders.setdefault(
                            delta.tool_call.index,
                            _ToolCallBuilder(delta.tool_call.index),
                        )
                        builder.apply(delta.tool_call)

                content = "".join(content_parts)
                final_content = content
                tool_calls = [
                    builders[index].build() for index in sorted(builders)
                ]
                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": content or None,
                }
                if tool_calls:
                    assistant_message["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in tool_calls
                    ]
                self._messages.append(assistant_message)

                yield AssistantCompleted(content)
                if not tool_calls:
                    break

                for call in tool_calls:
                    arguments, error = _parse_arguments(call.arguments)
                    yield ToolCallStarted(call.name, arguments)
                    if error is None:
                        output = await asyncio.to_thread(
                            self._registry.execute,
                            call.name,
                            arguments,
                        )
                    else:
                        output = error
                    self._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": output,
                        }
                    )
                    yield ToolCallFinished(call.name, arguments, output)

            await self._save_history()
            yield TurnCompleted(final_content)
        except Exception:
            await self._save_history()
            raise
