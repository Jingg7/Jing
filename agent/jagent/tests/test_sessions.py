from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, AsyncIterator, Sequence

from core.history import HistoryStore
from core.llm import ChatDelta
from core.session import AGENTS_FILE_MARKER, AgentSession
from core.sessions import SessionStore
from core.tools import ToolRegistry


class FakeModel:
    def __init__(self) -> None:
        self.requests: list[list[dict[str, Any]]] = []

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> AsyncIterator[ChatDelta]:
        self.requests.append([dict(message) for message in messages])
        yield ChatDelta(content="ok")


class SessionStoreTests(unittest.TestCase):
    def test_create_list_and_save_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(Path(temp_dir) / "sessions")
            info = store.create("  修复   订单  ")

            self.assertEqual(info.title, "修复 订单")
            self.assertEqual(store.list_sessions(), [])

            messages = [
                {"role": "system", "content": "系统"},
                {"role": "user", "content": "hello"},
            ]
            saved = store.save(info.session_id, "订单修复", messages)

            self.assertTrue(saved.saved)
            self.assertEqual(store.list_sessions()[0].title, "订单修复")
            self.assertEqual(
                store.history(info.session_id).load(),
                messages,
            )

    def test_find_matches_id_and_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(temp_dir)
            info = store.create("登录")
            store.save(info.session_id, "登录修复", [])

            self.assertEqual(store.find(info.session_id).session_id, info.session_id)
            self.assertEqual(store.find("登录修复").session_id, info.session_id)
            self.assertIsNone(store.find("不存在的会话"))

    def test_save_rejects_invalid_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(temp_dir)
            with self.assertRaises(ValueError):
                store.save("../secret", "x", [])


class AgentsFileTests(unittest.IsolatedAsyncioTestCase):
    async def test_agents_file_is_injected_once_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agents_file = root / "AGENTS.md"
            agents_file.write_text("Always run tests\n", encoding="utf-8")
            history = HistoryStore(root / "history.json")
            session = AgentSession(
                model=FakeModel(),
                registry=ToolRegistry([]),
                history=history,
                system_prompt="系统提示词",
                agents_file=agents_file,
            )

            matches = [
                message
                for message in session.messages
                if str(message.get("content", "")).startswith(AGENTS_FILE_MARKER)
            ]
            self.assertEqual(len(matches), 1)
            self.assertIn("Always run tests", matches[0]["content"])
            self.assertEqual(
                sum(
                    str(message.get("content", "")).startswith(AGENTS_FILE_MARKER)
                    for message in history.load()
                ),
                1,
            )

            await session.switch_history(history)

            self.assertEqual(
                sum(
                    str(message.get("content", "")).startswith(AGENTS_FILE_MARKER)
                    for message in session.messages
                ),
                1,
            )

    async def test_switch_history_injects_agents_file_into_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agents_file = root / "AGENTS.md"
            agents_file.write_text("Use pytest\n", encoding="utf-8")
            path = root / "session.json"
            HistoryStore(path).save(
                [
                    {"role": "system", "content": "系统提示词"},
                    {"role": "user", "content": "旧消息"},
                ]
            )
            session = AgentSession(
                model=FakeModel(),
                registry=ToolRegistry([]),
                system_prompt="系统提示词",
                agents_file=agents_file,
            )

            await session.switch_history(HistoryStore(path))

            self.assertEqual(
                [message["role"] for message in session.messages],
                ["system", "system", "user"],
            )
            self.assertTrue(
                str(session.messages[1]["content"]).startswith(AGENTS_FILE_MARKER)
            )
            self.assertTrue(
                str(HistoryStore(path).load()[1]["content"]).startswith(
                    AGENTS_FILE_MARKER
                )
            )


if __name__ == "__main__":
    unittest.main()
