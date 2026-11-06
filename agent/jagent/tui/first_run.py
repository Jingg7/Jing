from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Static


class ConfigNoticeApp(App[None]):
    TITLE = "JAgent"
    CSS = """
    Screen {
        align: center middle;
        background: #0a0a0a;
    }
    #config-panel {
        width: 72;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        background: #151515;
        border: solid #3a3a3a;
    }
    #config-title {
        height: 1;
        margin-bottom: 1;
        color: #ffffff;
        text-style: bold;
    }
    #config-body {
        height: auto;
        width: 100%;
        color: #d9d9d9;
        margin-bottom: 1;
    }
    #config-exit {
        width: 14;
        height: 3;
        border: none;
        background: #e5e5e5;
        color: #0a0a0a;
        text-style: bold;
    }
    """

    def __init__(self, config_path: Path):
        super().__init__()
        self._config_path = config_path

    def compose(self) -> ComposeResult:
        with Vertical(id="config-panel"):
            yield Static("需要配置 JAgent", id="config-title")
            yield Static(
                f"当前工作目录没有 config.ini，已自动生成：\n"
                f"{self._config_path}\n\n"
                "请根据你的模型服务修改其中的 base_url、model、api_key "
                "以及搜索 API Key，然后重新启动 jagent。",
                id="config-body",
                markup=False,
            )
            yield Button("退出", id="config-exit", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#config-exit", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-exit":
            self.exit()
