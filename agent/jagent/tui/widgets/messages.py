from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Collapsible, Markdown, Static

MAX_DISPLAY_CHARS = 4000


def _truncate(text: str) -> str:
    if len(text) <= MAX_DISPLAY_CHARS:
        return text
    return text[:MAX_DISPLAY_CHARS] + "\n...（内容过长，已截断显示）"


def _badge(name: str, color: str) -> Text:
    text = Text()
    text.append(f" {name} ", style=f"bold #0a0a0a on {color}")
    return text


class UserMessage(Static):
    def __init__(self, content: str):
        text = _badge("你", "#ffffff")
        text.append("\n")
        text.append(content)
        super().__init__(text, classes="message user")


class AssistantMessage(Vertical):
    def __init__(self, content: str = ""):
        super().__init__(classes="message assistant")
        self._content = content
        self._label = Static(_badge("JAGENT", "#f5f5f5"), classes="message-label")
        self._markdown = Markdown(content, classes="message-content")

    def compose(self) -> ComposeResult:
        yield self._label
        yield self._markdown

    @property
    def content(self) -> str:
        return self._content

    @property
    def is_empty(self) -> bool:
        return not self._content.strip()

    def append_text(self, text: str) -> None:
        self._content += text
        self._markdown.update(self._content)

    def set_text(self, text: str) -> None:
        self._content = text
        self._markdown.update(text)


class ToolResultMessage(Vertical):
    def __init__(self, name: str, output: str):
        super().__init__(classes="message tool")
        self._collapsible = Collapsible(
            Static(Text(_truncate(output)), classes="tool-output"),
            title=f"工具 · {name}",
            collapsed=True,
        )

    def compose(self) -> ComposeResult:
        yield self._collapsible


class ErrorMessage(Static):
    def __init__(self, message: str):
        text = _badge("错误", "#a6a6a6")
        text.append("\n")
        text.append(message)
        super().__init__(text, classes="message error")


class WelcomeMessage(Static):
    def __init__(self):
        text = Text()
        text.append("JAGENT\n", style="bold #ffffff")
        text.append("本地文件操作助手\n\n", style="bold #e5e5e5")
        text.append(
            "浏览、读取和编辑纯文本文件，也可以创建、删除和重命名文件与目录。\n",
            style="#bfbfbf",
        )
        text.append("\n试试这样问\n", style="bold #d9d9d9")
        for example in (
            "列出当前目录",
            "读取 README.md",
            "在 notes 目录下创建 todo.txt",
        ):
            text.append("  › ", style="#9b9b9b")
            text.append(f"{example}\n", style="#e5e5e5")
        super().__init__(text, classes="message welcome")


class SystemMessage(Static):
    def __init__(self, content: str):
        text = Text(content, style="dim")
        super().__init__(text, classes="message system")
