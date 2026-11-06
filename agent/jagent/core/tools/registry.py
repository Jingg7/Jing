from __future__ import annotations

from typing import Any, Iterable

from .base import BaseTool


class ToolRegistry:
    def __init__(self, tools: Iterable[BaseTool] | None = None):
        self._tools: dict[str, BaseTool] = {}
        for tool in tools or ():
            self.register(tool)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具重复注册: {tool.name}")
        self._tools[tool.name] = tool

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"未知的工具: {name}"
        try:
            return tool.execute(arguments)
        except KeyError as exc:
            return f"缺少参数: {exc}"
        except Exception as exc:
            return f"执行失败: {exc}"
