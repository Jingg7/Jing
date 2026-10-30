from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, AsyncIterator, Sequence

from core.events import (
    AssistantCompleted,
    AssistantStarted,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCompleted,
)
from core.history import HistoryStore
from core.llm import ChatDelta, ToolCallDelta
from core.session import AgentSession
from core.tools import BaseTool, ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "返回输入文本"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        return f"echo:{arguments['text']}"


class FakeModel:
    def __init__(self, rounds: list[list[ChatDelta]]):
        self._rounds = list(rounds)

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> AsyncIterator[ChatDelta]:
        for delta in self._rounds.pop(0):
            yield delta


class AgentSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_loop_and_history_persistence(self) -> None:
        rounds = [
            [
                ChatDelta(
                    tool_call=ToolCallDelta(
                        index=0,
                        id="call_1",
                        name="echo",
                    )
                ),
                ChatDelta(
                    tool_call=ToolCallDelta(
                        index=0,
                        arguments='{"text": "hi"}',
                    )
                ),
            ],
            [ChatDelta(content="完成")],
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"
            session = AgentSession(
                model=FakeModel(rounds),
                registry=ToolRegistry([EchoTool()]),
                history=HistoryStore(history_path),
            )

            events = [event async for event in session.send("测试")]

            self.assertIsInstance(events[0], AssistantStarted)
            self.assertIsInstance(events[1], AssistantCompleted)
            self.assertEqual(events[1].content, "")
            self.assertIsInstance(events[2], ToolCallStarted)
            self.assertIsInstance(events[3], ToolCallFinished)
            self.assertEqual(events[3].output, "echo:hi")
            self.assertIsInstance(events[4], AssistantStarted)
            self.assertIsInstance(events[5], TextDelta)
            self.assertIsInstance(events[6], AssistantCompleted)
            self.assertIsInstance(events[-1], TurnCompleted)
            self.assertEqual(events[-1].content, "完成")

            loaded = HistoryStore(history_path).load()
            self.assertEqual(
                [message["role"] for message in loaded],
                ["user", "assistant", "tool", "assistant"],
            )
            self.assertEqual(loaded[2]["content"], "echo:hi")
            self.assertEqual(loaded[3]["content"], "完成")

    async def test_clear_resets_history_and_keeps_system_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"
            history = HistoryStore(history_path)
            history.save(
                [
                    {"role": "system", "content": "旧提示词"},
                    {"role": "user", "content": "旧问题"},
                    {"role": "assistant", "content": "旧回答"},
                ]
            )
            session = AgentSession(
                model=FakeModel([]),
                registry=ToolRegistry([EchoTool()]),
                history=history,
                system_prompt="新提示词",
            )

            await session.clear()

            self.assertEqual(
                session.messages,
                ({"role": "system", "content": "新提示词"},),
            )
            self.assertEqual(HistoryStore(history_path).load(), list(session.messages))


if __name__ == "__main__":
    unittest.main()
