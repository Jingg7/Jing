from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, AsyncIterator, Sequence
from unittest.mock import patch

from core.archive import ContextArchive, archive_note
from core.config import LLMConfig
from core.context import (
    ContextUsage,
    DEFAULT_CONTEXT_WINDOW,
    detect_context_window,
    estimate_messages_tokens,
    estimate_text_tokens,
    resolve_context_window,
)
from core.events import (
    CompactionCompleted,
    CompactionFailed,
    CompactionStarted,
)
from core.history import HistoryStore
from core.llm import ChatDelta, TokenUsage
from core.session import AgentSession, ContextLimitError
from core.tools import FileToolConfig, ToolRegistry, build_default_registry


class SummaryModel:
    def __init__(self, summary: str):
        self.summary = summary
        self.tools_seen: list[list[dict[str, Any]]] = []
        self.requests: list[list[dict[str, Any]]] = []

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> AsyncIterator[ChatDelta]:
        self.requests.append([dict(message) for message in messages])
        self.tools_seen.append([dict(tool) for tool in tools])
        yield ChatDelta(content=self.summary)


class FailingModel:
    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> AsyncIterator[ChatDelta]:
        raise RuntimeError("summary failed")
        yield ChatDelta()


class UsageModel:
    def __init__(self, total_tokens: int):
        self.total_tokens = total_tokens

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> AsyncIterator[ChatDelta]:
        yield ChatDelta(content="好的")
        yield ChatDelta(
            usage=TokenUsage(
                prompt_tokens=self.total_tokens - 10,
                completion_tokens=10,
                total_tokens=self.total_tokens,
            )
        )


class TokenEstimateTests(unittest.TestCase):
    def test_text_token_estimate(self) -> None:
        self.assertEqual(estimate_text_tokens(""), 0)
        self.assertEqual(estimate_text_tokens("abcd"), 1)
        self.assertEqual(estimate_text_tokens("你好"), 2)

    def test_messages_include_tools(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        without_tools = estimate_messages_tokens(messages)
        with_tools = estimate_messages_tokens(
            messages,
            [{"type": "function", "function": {"name": "echo"}}],
        )
        self.assertGreater(with_tools, without_tools)

    def test_context_usage_warning_threshold(self) -> None:
        self.assertFalse(ContextUsage(59, 100).warning)
        self.assertTrue(ContextUsage(60, 100).warning)

    def test_context_window_resolution(self) -> None:
        llm = LLMConfig("http://localhost:1234/v1", "test", "key")
        self.assertEqual(resolve_context_window(llm, 4096, probe=False), (4096, False))
        self.assertEqual(
            resolve_context_window(llm, None, probe=False),
            (DEFAULT_CONTEXT_WINDOW, True),
        )

    def test_detects_lmstudio_context_window(self) -> None:
        with patch(
            "core.context._read_json",
            return_value={
                "data": [
                    {"id": "other", "max_context_length": 8192},
                    {"id": "test-model", "max_context_length": 32768},
                ]
            },
        ):
            self.assertEqual(
                detect_context_window("http://127.0.0.1:1234/v1", "test-model"),
                32768,
            )

    def test_detects_ollama_context_window(self) -> None:
        def fake_read(url: str, payload: dict[str, Any] | None = None) -> Any:
            if url.endswith("/api/v0/models"):
                raise OSError("not lmstudio")
            return {"model_info": {"llama.context_length": 16384}}

        with patch("core.context._read_json", side_effect=fake_read):
            self.assertEqual(
                detect_context_window("http://127.0.0.1:11434/v1", "test-model"),
                16384,
            )


class ContextArchiveTests(unittest.TestCase):
    def test_saves_jsonl_and_searches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = ContextArchive(Path(temp_dir) / ".agents" / "context")
            record = archive.save(
                [
                    {"role": "user", "content": "项目使用 PostgreSQL 数据库"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "readFile",
                                    "arguments": '{"path": "db.py"}',
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "content": "DATABASE_URL=postgres://localhost/app",
                    },
                ]
            )

            self.assertTrue(record.path.is_file())
            lines = record.path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)

            output = archive.search("PostgreSQL")
            self.assertIn(record.archive_id, output)
            self.assertIn("第 1 条消息", output)
            self.assertIn("PostgreSQL", output)

            output = archive.search("readFile")
            self.assertIn("arguments=", output)
            self.assertIn("db.py", output)

            output = archive.search("postgres://", archive_id=record.archive_id)
            self.assertIn("第 3 条消息", output)

            output = archive.search("不存在的内容")
            self.assertIn("未找到", output)

    def test_rejects_invalid_archive_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = ContextArchive(Path(temp_dir))
            self.assertIn("无效的归档编号", archive.search("x", "../secret"))
            self.assertIn("未找到归档", archive.search("x", "20990101-000000"))

    def test_archive_note(self) -> None:
        from datetime import datetime

        note = archive_note("20261022-153000", datetime(2026, 10, 22, 15, 30))
        self.assertIn("2026-10-22 15:30:00", note)
        self.assertIn("20261022-153000", note)
        self.assertIn("recallContext", note)


class RecallContextToolTests(unittest.TestCase):
    def test_registered_and_searches_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = ContextArchive(Path(temp_dir) / ".agents" / "context")
            record = archive.save(
                [{"role": "user", "content": "保留这条重要线索：蓝色钥匙"}]
            )
            registry = build_default_registry(
                FileToolConfig(),
                context_archive=archive,
            )

            self.assertIn("recallContext", registry.names())
            output = registry.execute(
                "recallContext",
                {"text": "蓝色钥匙", "id": record.archive_id},
            )
            self.assertIn(record.archive_id, output)
            self.assertIn("蓝色钥匙", output)


class ContextLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_api_usage_and_blocks_after_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session = AgentSession(
                model=UsageModel(total_tokens=70),
                registry=ToolRegistry([]),
                history=HistoryStore(Path(temp_dir) / "history.json"),
                system_prompt="系统提示词",
                context_window=100,
                context_window_is_default=False,
            )

            events = [event async for event in session.send("第一条消息")]

            self.assertTrue(events)
            self.assertEqual(session.context_usage.used_tokens, 70)
            self.assertTrue(session.compaction_required)
            with self.assertRaises(ContextLimitError):
                [event async for event in session.send("第二条消息")]


class CompactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_compaction_archives_and_replaces_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = HistoryStore(root / "history.json")
            history.save(
                [
                    {"role": "system", "content": "系统提示词"},
                    {"role": "user", "content": "请实现登录功能"},
                    {"role": "assistant", "content": "已经分析完需求"},
                ]
            )
            archive = ContextArchive(root / ".agents" / "context")
            model = SummaryModel("# 工作摘要\n\n用户需要登录功能。")
            session = AgentSession(
                model=model,
                registry=ToolRegistry([]),
                history=history,
                system_prompt="系统提示词",
                context_archive=archive,
                context_window=100_000,
                context_window_is_default=False,
            )

            events = [event async for event in session.compact()]

            self.assertIsInstance(events[0], CompactionStarted)
            self.assertIsInstance(events[-1], CompactionCompleted)
            completed = events[-1]
            self.assertIn("请实现登录功能", completed.original)
            self.assertIn("工作摘要", completed.summary)
            self.assertIn(completed.archive_id, completed.summary)
            self.assertIn("recallContext", completed.summary)

            archived = archive.list_ids()
            self.assertEqual(archived, [completed.archive_id])
            archive_path = archive.directory / f"{completed.archive_id}.jsonl"
            self.assertEqual(len(archive_path.read_text(encoding="utf-8").splitlines()), 3)

            self.assertEqual(
                [message["role"] for message in session.messages],
                ["system", "assistant"],
            )
            self.assertEqual(session.messages[0]["content"], "系统提示词")
            self.assertIn("工作摘要", session.messages[1]["content"])
            self.assertEqual(
                [message["role"] for message in history.load()],
                ["system", "assistant"],
            )
            self.assertEqual(model.tools_seen, [[]])
            self.assertIn("请实现登录功能", model.requests[0][1]["content"])
            self.assertLess(session.context_usage.used_tokens, 60_000)

    async def test_failed_compaction_keeps_original_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = [
                {"role": "system", "content": "系统提示词"},
                {"role": "user", "content": "不要丢失这段内容"},
            ]
            history = HistoryStore(root / "history.json")
            history.save(original)
            archive = ContextArchive(root / ".agents" / "context")
            session = AgentSession(
                model=FailingModel(),
                registry=ToolRegistry([]),
                history=history,
                system_prompt="系统提示词",
                context_archive=archive,
                context_window=100_000,
                context_window_is_default=False,
            )

            events = [event async for event in session.compact()]

            self.assertIsInstance(events[0], CompactionStarted)
            self.assertIsInstance(events[-1], CompactionFailed)
            self.assertEqual(
                [message["role"] for message in session.messages],
                ["system", "user"],
            )
            self.assertEqual(session.messages[1]["content"], "不要丢失这段内容")
            self.assertTrue(archive.list_ids())
            self.assertFalse(session.compaction_required)


if __name__ == "__main__":
    unittest.main()
