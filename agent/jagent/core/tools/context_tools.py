from __future__ import annotations

from typing import Any

from ..archive import ContextArchive
from .base import BaseTool


class RecallContextTool(BaseTool):
    name = "recallContext"
    description = (
        "检索此前因上下文压缩而归档的原始对话记录。当压缩摘要缺少某些历史细节时，"
        "可以使用本工具查找原始消息。text 为必填的关键词或文本内容；id 可选，"
        "用于指定某个归档编号，省略时会在所有归档中检索。返回匹配片段、归档编号"
        "和消息位置，结果较长时会自动截断。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": (
                    "可选。上下文归档编号，例如 20261022-153000。"
                    "省略时检索所有历史归档。"
                ),
            },
            "text": {
                "type": "string",
                "description": "需要查找的关键词或文本内容",
            },
        },
        "required": ["text"],
    }

    def __init__(self, archive: ContextArchive):
        self._archive = archive

    def run(self, arguments: dict[str, Any]) -> str:
        text = arguments["text"]
        if not isinstance(text, str):
            return "参数 text 必须是字符串"
        archive_id = arguments.get("id")
        if archive_id is not None and not isinstance(archive_id, str):
            return "参数 id 必须是字符串"
        return self._archive.search(text, archive_id)
