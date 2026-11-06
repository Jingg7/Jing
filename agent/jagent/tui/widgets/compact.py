from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Static


class CompactPanel(ModalScreen[None]):
    BINDINGS = [("escape", "close", "关闭")]

    def __init__(self, archive_id: str, original: str, summary: str):
        super().__init__()
        self._archive_id = archive_id
        self._original = original
        self._summary = summary

    def compose(self) -> ComposeResult:
        with Vertical(id="compact-panel"):
            yield Static(
                f"上下文压缩对比 · 归档 {self._archive_id}",
                id="compact-title",
            )
            with Horizontal(id="compact-columns"):
                with Vertical(classes="compact-column"):
                    yield Static("压缩前原文", classes="compact-heading")
                    with VerticalScroll(classes="compact-scroll"):
                        yield Static(
                            self._original,
                            classes="compact-body",
                            markup=False,
                        )
                with Vertical(classes="compact-column"):
                    yield Static("压缩后结果", classes="compact-heading")
                    with VerticalScroll(classes="compact-scroll"):
                        yield Markdown(self._summary, classes="compact-body")
            yield Button("关闭", id="compact-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "compact-close":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
