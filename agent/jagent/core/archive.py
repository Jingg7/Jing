from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

CONTEXT_DIRECTORY = Path(".agents") / "context"
ARCHIVE_SUFFIX = ".jsonl"
_ARCHIVE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_RESULTS = 20
_MAX_RESULT_CHARS = 8000
_MAX_SNIPPET_CHARS = 600


@dataclass(frozen=True)
class ArchiveRecord:
    archive_id: str
    path: Path
    created_at: datetime


def archive_note(archive_id: str, created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"此前上下文已于 {timestamp} 完成压缩，原始上下文保存在编号为 "
        f"{archive_id} 的归档文件中。如需查找历史信息，请使用 recallContext 工具。"
    )


def _format_message(message: dict[str, Any], index: int) -> str:
    role = str(message.get("role", "unknown"))
    lines = [f"第 {index} 条消息 · 角色: {role}"]
    content = message.get("content")
    if content not in (None, ""):
        lines.append(str(content))
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                function = {}
            lines.append(
                "工具调用: "
                f"id={call.get('id', '')} "
                f"name={function.get('name', '')} "
                f"arguments={function.get('arguments', '')}"
            )
    if role == "tool":
        lines.append(f"工具调用 ID: {message.get('tool_call_id', '')}")
    return "\n".join(lines)


def _snippet(
    text: str,
    keywords: Sequence[str],
    max_chars: int = _MAX_SNIPPET_CHARS,
) -> str:
    folded = text.casefold()
    positions = [
        position
        for keyword in keywords
        if (position := folded.find(keyword)) >= 0
    ]
    position = min(positions) if positions else 0
    start = max(0, position - (max_chars // 4))
    end = min(len(text), start + max_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet


class ContextArchive:
    def __init__(
        self,
        directory: str | Path = CONTEXT_DIRECTORY,
        *,
        max_results: int = _MAX_RESULTS,
        max_chars: int = _MAX_RESULT_CHARS,
        snippet_chars: int = _MAX_SNIPPET_CHARS,
    ):
        self.directory = Path(directory).expanduser()
        self.max_results = max_results
        self.max_chars = max_chars
        self.snippet_chars = snippet_chars

    def save(self, messages: Sequence[dict[str, Any]]) -> ArchiveRecord:
        self.directory.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now()
        archive_id = self._unique_id(created_at)
        path = self.directory / f"{archive_id}{ARCHIVE_SUFFIX}"
        temp_path = self.directory / f"{archive_id}{ARCHIVE_SUFFIX}.tmp"

        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                for message in messages:
                    handle.write(
                        json.dumps(dict(message), ensure_ascii=False) + "\n"
                    )
            temp_path.replace(path)
        except OSError:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return ArchiveRecord(archive_id, path, created_at)

    def list_ids(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        ids = [
            path.stem
            for path in self.directory.glob(f"*{ARCHIVE_SUFFIX}")
            if path.is_file()
        ]
        return sorted(ids, reverse=True)

    def _unique_id(self, created_at: datetime) -> str:
        base = created_at.strftime("%Y%m%d-%H%M%S")
        candidate = base
        counter = 1
        while (self.directory / f"{candidate}{ARCHIVE_SUFFIX}").exists():
            candidate = f"{base}-{counter:02d}"
            counter += 1
        return candidate

    def _resolve_id(self, archive_id: Any) -> str | None:
        if not isinstance(archive_id, str):
            return None
        value = archive_id.strip()
        if value.endswith(ARCHIVE_SUFFIX):
            value = value[: -len(ARCHIVE_SUFFIX)]
        if not value or not _ARCHIVE_ID_PATTERN.fullmatch(value):
            return None
        return value

    def search(
        self,
        text: str,
        archive_id: str | None = None,
        *,
        max_results: int | None = None,
        max_chars: int | None = None,
    ) -> str:
        result_limit = max_results or self.max_results
        char_limit = max_chars or self.max_chars
        query = str(text or "").strip()
        if not query:
            return "参数 text 不能为空"
        keywords = [word.casefold() for word in query.split() if word]
        if not keywords:
            return "参数 text 不能为空"

        if archive_id is not None:
            resolved_id = self._resolve_id(archive_id)
            if resolved_id is None:
                return f"无效的归档编号: {archive_id}"
            path = self.directory / f"{resolved_id}{ARCHIVE_SUFFIX}"
            if not path.is_file():
                available = "、".join(self.list_ids()) or "无"
                return f"未找到归档: {resolved_id}。可用归档: {available}"
            ids = [resolved_id]
        else:
            ids = self.list_ids()
            if not ids:
                return "尚无可检索的上下文归档"

        results: list[tuple[int, str, int, str, str]] = []
        for current_id in ids:
            path = self.directory / f"{current_id}{ARCHIVE_SUFFIX}"
            if not path.is_file():
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for index, line in enumerate(handle, start=1):
                        if not line.strip():
                            continue
                        try:
                            message = json.loads(line)
                        except json.JSONDecodeError:
                            message = {
                                "role": "unknown",
                                "content": line.strip(),
                            }
                        if not isinstance(message, dict):
                            continue
                        display = _format_message(message, index)
                        folded = display.casefold()
                        score = sum(folded.count(keyword) for keyword in keywords)
                        if score <= 0:
                            continue
                        results.append(
                            (
                                score,
                                current_id,
                                index,
                                str(message.get("role", "unknown")),
                                _snippet(display, keywords, self.snippet_chars),
                            )
                        )
            except OSError:
                continue

        if not results:
            scope = f"归档 {ids[0]}" if archive_id is not None else "所有归档"
            return f"在{scope}中未找到包含“{query}”的内容"

        results.sort(key=lambda item: item[0], reverse=True)
        lines = [f"找到 {len(results)} 条相关记录（关键词: {query}）："]
        used_chars = 0
        shown = 0
        truncated = False
        for score, current_id, index, role, snippet in results:
            entry = (
                f"{shown + 1}. 归档 {current_id} · 第 {index} 条消息 · "
                f"角色: {role} · 匹配 {score} 次\n{snippet}"
            )
            if shown > 0 and used_chars + len(entry) > char_limit:
                truncated = True
                break
            lines.append(entry)
            used_chars += len(entry)
            shown += 1
            if shown >= result_limit:
                truncated = len(results) > shown
                break

        if truncated:
            lines.append(
                "结果较多，已截断。请提供更具体的关键词，或使用 id 指定归档。"
            )
        return "\n\n".join(lines)
