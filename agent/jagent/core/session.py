from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

from .archive import ContextArchive, archive_note
from .compaction import build_compaction_messages, build_transcript
from .config import (
    DEFAULT_COMPACTION_TARGET_TOKENS,
    DEFAULT_WARNING_RATIO,
)
from .context import (
    DEFAULT_CONTEXT_WINDOW,
    ContextUsage,
    estimate_messages_tokens,
)
from .events import (
    AgentEvent,
    AssistantCompleted,
    AssistantStarted,
    CompactionCompleted,
    CompactionFailed,
    CompactionStarted,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCompleted,
)
from .history import HistoryStore
from .llm import ChatModel, TokenUsage, ToolCall, ToolCallDelta
from .tools.registry import ToolRegistry


class ContextLimitError(RuntimeError):
    pass

AGENTS_FILE_MARKER = "以下是项目 AGENTS.md 的内容，请在后续工作中遵守："


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
        context_archive: ContextArchive | None = None,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        context_window_is_default: bool = True,
        context_warning_ratio: float = DEFAULT_WARNING_RATIO,
        compaction_target_tokens: int = DEFAULT_COMPACTION_TARGET_TOKENS,
        agents_file: str | Path | None = None,
        mcp_manager: Any | None = None,
    ):
        self._model = model
        self._registry = registry
        self._history = history
        self._context_archive = context_archive
        self._context_window = max(1, context_window)
        self._context_window_is_default = context_window_is_default
        self._context_warning_ratio = context_warning_ratio
        self._compaction_target_tokens = compaction_target_tokens
        self._agents_file = Path(agents_file).expanduser() if agents_file else None
        self._mcp_manager = mcp_manager
        self._mcp_tool_names: set[str] = set()
        self._used_tokens: int | None = None
        self._compacting = False
        self._messages: list[dict[str, Any]] = (
            history.load() if history is not None else []
        )
        self._system_prompt = system_prompt
        if system_prompt:
            self._apply_system_prompt(system_prompt)
        injected = self._inject_agents_file()
        if injected and self._history is not None:
            try:
                self._history.save(self._messages)
            except OSError:
                pass

    @property
    def mcp_manager(self) -> Any | None:
        return self._mcp_manager

    @property
    def mcp_tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._mcp_tool_names))

    @property
    def history_store(self) -> HistoryStore | None:
        return self._history

    def _apply_system_prompt(self, system_prompt: str) -> None:
        for message in self._messages:
            if message.get("role") == "system":
                message["content"] = system_prompt
                break
        else:
            self._messages.insert(0, {"role": "system", "content": system_prompt})

    def _inject_agents_file(self) -> bool:
        path = self._agents_file
        if path is None or not path.is_file():
            return False
        try:
            content = path.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeDecodeError):
            return False
        if not content:
            return False
        for message in self._messages:
            if (
                message.get("role") == "system"
                and str(message.get("content", "")).startswith(AGENTS_FILE_MARKER)
            ):
                return False
        message = {
            "role": "system",
            "content": f"{AGENTS_FILE_MARKER}\n\n{content}",
        }
        insert_at = next(
            (
                index + 1
                for index, existing in enumerate(self._messages)
                if existing.get("role") == "system"
            ),
            0,
        )
        self._messages.insert(insert_at, message)
        return True

    async def switch_history(self, history: HistoryStore) -> None:
        self._history = history
        self._messages = await asyncio.to_thread(history.load)
        if self._system_prompt:
            self._apply_system_prompt(self._system_prompt)
        injected = self._inject_agents_file()
        self._used_tokens = None
        if injected:
            await self._save_history()

    def refresh_mcp_tools(self) -> int:
        manager = self._mcp_manager
        if manager is None:
            return 0
        base_names = [
            name
            for name in self._registry.names()
            if name not in self._mcp_tool_names
        ]
        try:
            tools = manager.build_tools(base_names)
        except Exception:
            return len(self._mcp_tool_names)
        new_names = {tool.name for tool in tools}
        for name in self._mcp_tool_names.difference(new_names):
            self._registry.unregister(name)
        for tool in tools:
            self._registry.unregister(tool.name)
            self._registry.register(tool)
        self._mcp_tool_names = new_names
        self._refresh_usage()
        return len(tools)

    @property
    def messages(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(message) for message in self._messages)

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self._registry.schemas()

    @property
    def context_usage(self) -> ContextUsage:
        used = self._used_tokens
        if used is None:
            used = estimate_messages_tokens(
                self._messages,
                self._registry.schemas(),
            )
        return ContextUsage(
            used_tokens=used,
            window_tokens=self._context_window,
            is_default_window=self._context_window_is_default,
            warning_ratio=self._context_warning_ratio,
        )

    @property
    def compaction_required(self) -> bool:
        return self.context_usage.warning

    def _refresh_usage(self, usage: TokenUsage | None = None) -> None:
        if usage is not None:
            total = usage.total_tokens or (
                usage.prompt_tokens + usage.completion_tokens
            )
            if total > 0:
                self._used_tokens = total
                return
        self._used_tokens = estimate_messages_tokens(
            self._messages,
            self._registry.schemas(),
        )

    async def clear(self) -> None:
        system_messages = [
            dict(message)
            for message in self._messages
            if message.get("role") == "system"
        ]
        self._messages = system_messages[:1]
        self._inject_agents_file()
        self._used_tokens = None
        await self._save_history()

    async def _save_history(self) -> None:
        if self._history is not None:
            await asyncio.to_thread(self._history.save, self._messages)

    async def _summarize(self, messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        async for delta in self._model.stream(
            build_compaction_messages(
                messages,
                self._compaction_target_tokens,
            ),
            [],
        ):
            if delta.content:
                parts.append(delta.content)
        return "".join(parts)

    async def compact(self) -> AsyncIterator[AgentEvent]:
        if self._compacting:
            yield CompactionFailed("上下文压缩正在进行，请等待当前压缩完成")
            return
        if self._context_archive is None:
            yield CompactionFailed("未配置上下文归档目录，无法执行压缩")
            return

        self._compacting = True
        try:
            original_messages = [dict(message) for message in self._messages]
            original_transcript = build_transcript(original_messages)

            try:
                record = await asyncio.to_thread(
                    self._context_archive.save,
                    original_messages,
                )
            except Exception as exc:
                yield CompactionFailed(f"保存原始上下文失败: {exc}")
                return

            yield CompactionStarted(record.archive_id)

            try:
                summary = await self._summarize(original_messages)
            except Exception as exc:
                yield CompactionFailed(f"生成摘要失败: {exc}")
                return
            if not summary.strip():
                yield CompactionFailed("生成摘要失败: 模型返回了空内容")
                return

            note = archive_note(record.archive_id, record.created_at)
            compressed = f"{summary.strip()}\n\n---\n\n> {note}"
            system_messages = [
                dict(message)
                for message in original_messages
                if message.get("role") == "system"
            ]
            previous_messages = self._messages
            self._messages = system_messages + [
                {"role": "assistant", "content": compressed}
            ]
            self._refresh_usage()

            try:
                await self._save_history()
            except Exception as exc:
                self._messages = previous_messages
                self._refresh_usage()
                yield CompactionFailed(f"保存压缩结果失败: {exc}")
                return

            yield CompactionCompleted(
                archive_id=record.archive_id,
                original=original_transcript,
                summary=compressed,
            )
        finally:
            self._compacting = False

    async def send(self, prompt: str) -> AsyncIterator[AgentEvent]:
        prompt = prompt.strip()
        if not prompt:
            return
        if self._compacting:
            raise RuntimeError("上下文压缩正在进行，暂时不能发送新消息")
        if self.compaction_required:
            usage = self.context_usage
            raise ContextLimitError(
                "上下文使用量已达到 "
                f"{usage.percent}%"
                f"（阈值 {usage.warning_percent}%），请先执行 /compact 压缩上下文"
            )

        self._messages.append({"role": "user", "content": prompt})
        self._refresh_usage()
        try:
            final_content = ""
            while True:
                yield AssistantStarted()
                content_parts: list[str] = []
                builders: dict[int, _ToolCallBuilder] = {}
                usage: TokenUsage | None = None
                async for delta in self._model.stream(
                    self._messages,
                    self._registry.schemas(),
                ):
                    if delta.usage is not None:
                        usage = delta.usage
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
                self._refresh_usage(usage)

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
