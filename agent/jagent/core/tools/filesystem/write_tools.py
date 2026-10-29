from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..base import BaseTool
from .common import (
    FileToolConfig,
    ensure_safe_directory_operation,
    format_size,
    read_text_file,
    resolve_path,
)


class CreateFileTool(BaseTool):
    name = "createFile"
    description = "在指定目录下创建新的文件，可选择写入初始内容"
    parameters = {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "新文件所在的目录路径",
            },
            "filename": {
                "type": "string",
                "description": "新文件的文件名，例如 demo.txt",
            },
            "content": {
                "type": "string",
                "description": "写入新文件的纯文本内容，默认为空",
            },
        },
        "required": ["directory", "filename"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        base = resolve_path(arguments["directory"] or ".")
        if not base.exists():
            return f"目录不存在: {base}"
        if not base.is_dir():
            return f"不是目录: {base}"
        target = (base / arguments["filename"]).resolve()
        if target.exists():
            return f"文件已存在: {target}"
        if not target.parent.exists():
            return f"目标目录不存在: {target.parent}"
        content = arguments.get("content", "")
        with target.open("x", encoding="utf-8", newline="") as file:
            file.write(content)
        return (
            f"已创建文件: {target}"
            f"（{format_size(len(content.encode('utf-8')))}）"
        )


class EditFileTool(BaseTool):
    name = "editFile"
    description = (
        "编辑指定纯文本文件的内容。提供 old_content 时替换文件中第一处匹配的内容，"
        "否则用 content 覆盖整个文件"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要编辑的纯文本文件路径",
            },
            "content": {
                "type": "string",
                "description": "新的文本内容",
            },
            "old_content": {
                "type": "string",
                "description": "可选，要被替换的原文本内容；不提供时覆盖整个文件",
            },
        },
        "required": ["path", "content"],
    }

    def __init__(self, config: FileToolConfig | None = None):
        self._config = config or FileToolConfig()

    def run(self, arguments: dict[str, Any]) -> str:
        target = resolve_path(arguments["path"])
        if not target.exists():
            return f"文件不存在: {target}"
        if not target.is_file():
            return f"不是文件: {target}"
        original = read_text_file(target, self._config.max_read_bytes)
        old_content = arguments.get("old_content")
        content = arguments["content"]
        if old_content:
            if old_content not in original:
                return f"未在文件中找到要替换的内容: {old_content!r}"
            updated = original.replace(old_content, content, 1)
            action = "已替换文件中的匹配内容"
        else:
            updated = content
            action = "已覆盖写入文件内容"
        with target.open("w", encoding="utf-8", newline="") as file:
            file.write(updated)
        return (
            f"{action}: {target}"
            f"（{format_size(len(updated.encode('utf-8')))}）"
        )


class CreateDirectoryTool(BaseTool):
    name = "createDirectory"
    description = "创建一个新目录，支持多级目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要创建的目录路径",
            }
        },
        "required": ["path"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        target = resolve_path(arguments["path"])
        if target.exists():
            if target.is_dir():
                return f"目录已存在: {target}"
            return f"同名文件已存在: {target}"
        target.mkdir(parents=True)
        return f"已创建目录: {target}"


class DeleteDirectoryTool(BaseTool):
    name = "deleteDirectory"
    description = "删除指定目录及其中的全部内容，支持删除非空目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要删除的目录路径",
            }
        },
        "required": ["path"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        target = resolve_path(arguments["path"])
        if not target.exists():
            return f"目录不存在: {target}"
        if not target.is_dir():
            return f"不是目录: {target}"
        ensure_safe_directory_operation(target)
        shutil.rmtree(target)
        return f"已删除目录: {target}"


class DeleteFileTool(BaseTool):
    name = "deleteFile"
    description = "删除指定文件"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要删除的文件路径",
            }
        },
        "required": ["path"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        target = resolve_path(arguments["path"])
        if not target.exists():
            return f"文件不存在: {target}"
        if target.is_dir():
            return f"不是文件: {target}"
        target.unlink()
        return f"已删除文件: {target}"


class RenameFileOrDirectoryTool(BaseTool):
    name = "renameFileOrDirectory"
    description = "重命名文件或目录，也可用于移动文件或目录"
    parameters = {
        "type": "object",
        "properties": {
            "old_path": {
                "type": "string",
                "description": "原文件或目录的路径",
            },
            "new_path": {
                "type": "string",
                "description": "新的文件或目录路径",
            },
        },
        "required": ["old_path", "new_path"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        source = resolve_path(arguments["old_path"])
        if not source.exists():
            return f"原路径不存在: {source}"
        ensure_safe_directory_operation(source)
        destination = Path(arguments["new_path"]).expanduser()
        if not destination.is_absolute():
            destination = Path.cwd() / destination
        destination = destination.resolve()
        if destination.exists():
            return f"目标路径已存在: {destination}"
        if not destination.parent.exists():
            return f"目标目录不存在: {destination.parent}"
        shutil.move(str(source), str(destination))
        return f"已重命名: {source} -> {destination}"
