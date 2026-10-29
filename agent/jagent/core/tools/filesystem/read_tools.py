from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from ..base import BaseTool
from .common import (
    ARCHIVE_EXTENSIONS,
    AUDIO_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    EXECUTABLE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
    FileToolConfig,
    decode_text_bytes,
    format_size,
    read_text_file,
    resolve_path,
)


class GetCurrentDirectoryTool(BaseTool):
    name = "getCurrentDirectory"
    description = "获取当前工作目录的绝对路径"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        return f"当前工作目录: {Path.cwd().resolve()}"


class ListDirectoryTool(BaseTool):
    name = "listDirectory"
    description = "列出指定目录下的所有文件和子目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要列出的目录路径，默认为当前工作目录",
            }
        },
        "required": [],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        target = resolve_path(arguments.get("path") or ".")
        if not target.exists():
            return f"目录不存在: {target}"
        if not target.is_dir():
            return f"不是目录: {target}"
        entries = sorted(
            target.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
        directories = [item for item in entries if item.is_dir()]
        files = [item for item in entries if not item.is_dir()]
        lines = [
            f"目录: {target}",
            f"共 {len(entries)} 项（{len(directories)} 个目录，{len(files)} 个文件）:",
        ]
        for item in entries:
            if item.is_dir():
                lines.append(f"[D] {item.name}")
            else:
                try:
                    lines.append(f"[F] {item.name} ({format_size(item.stat().st_size)})")
                except OSError:
                    lines.append(f"[F] {item.name} (无法获取大小)")
        return "\n".join(lines)


class GetFileTypeTool(BaseTool):
    name = "getFileType"
    description = (
        "获取指定文件的文件类型，例如文本文件、图片、音频、视频、压缩包、文档、可执行文件等"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要检查的文件路径",
            }
        },
        "required": ["path"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        target = resolve_path(arguments["path"])
        if not target.exists():
            return f"路径不存在: {target}"
        if target.is_dir():
            return f"路径: {target}\n类型: 目录"
        mime, _ = mimetypes.guess_type(target.name)
        ext = target.suffix.lower()
        if ext in TEXT_EXTENSIONS or (mime and mime.startswith("text/")):
            category = "文本文件"
        elif ext in IMAGE_EXTENSIONS or (mime and mime.startswith("image/")):
            category = "图片文件"
        elif ext in AUDIO_EXTENSIONS or (mime and mime.startswith("audio/")):
            category = "音频文件"
        elif ext in VIDEO_EXTENSIONS or (mime and mime.startswith("video/")):
            category = "视频文件"
        elif ext in ARCHIVE_EXTENSIONS:
            category = "压缩包"
        elif ext in DOCUMENT_EXTENSIONS or (mime and mime.startswith("application/pdf")):
            category = "文档文件"
        elif ext in EXECUTABLE_EXTENSIONS:
            category = "可执行文件"
        else:
            try:
                sample = target.read_bytes()[:4096]
            except OSError:
                sample = b""
            category = "文本文件" if decode_text_bytes(sample) else "二进制文件"
        lines = [
            f"路径: {target}",
            f"类型: {category}",
            f"MIME: {mime or '未知'}",
            f"扩展名: {ext or '无'}",
            f"大小: {format_size(target.stat().st_size)}",
        ]
        return "\n".join(lines)


class ReadFileTool(BaseTool):
    name = "readFile"
    description = "读取指定纯文本文件的内容，仅支持纯文本格式文件，不支持二进制文件"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要读取的纯文本文件路径",
            }
        },
        "required": ["path"],
    }

    def __init__(self, config: FileToolConfig | None = None):
        self._config = config or FileToolConfig()

    def run(self, arguments: dict[str, Any]) -> str:
        content = read_text_file(arguments["path"], self._config.max_read_bytes)
        if content == "":
            return "(文件内容为空)"
        return content
