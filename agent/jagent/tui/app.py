from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Static

from core.events import (
    AssistantCompleted,
    AssistantStarted,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)
from core.session import AgentSession

from .theme import JAGENT_THEME
from .widgets import (
    AssistantMessage,
    ErrorMessage,
    PromptInput,
    ToolResultMessage,
    UserMessage,
    WelcomeMessage,
)


class SidebarResizer(Static):
    def on_mouse_down(self, event) -> None:
        event.stop()
        self.capture_mouse()
        self.add_class("dragging")
        self.app.begin_sidebar_resize(event.screen_x)

    def on_mouse_move(self, event) -> None:
        if self.app.resizing:
            self.app.update_sidebar_resize(event.screen_x)

    def on_mouse_up(self, event) -> None:
        if self.app.resizing:
            self.app.end_sidebar_resize()
            self.release_mouse()
            event.stop()


class JAgentApp(App[None]):
    CSS_PATH = "styles.tcss"
    TITLE = "JAgent"
    SUB_TITLE = "本地文件操作助手"
    BINDINGS = [
        ("ctrl+l", "clear_chat", "清屏"),
        ("f1", "toggle_sidebar", "侧边栏"),
        ("ctrl+q", "quit", "退出"),
    ]

    def __init__(self, session: AgentSession):
        super().__init__()
        self._session = session
        self._busy = False
        self._sidebar_width = 22
        self._resizing = False
        self._resize_start_x = 0
        self._resize_start_width = 22

    @property
    def resizing(self) -> bool:
        return self._resizing

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="workspace"):
            with Vertical(id="main"):
                with Horizontal(id="toolbar"):
                    yield Static("对话", id="toolbar-title")
                    yield Static("就绪", id="status")
                with VerticalScroll(id="chat"):
                    yield WelcomeMessage()
                with Horizontal(id="input-row"):
                    yield PromptInput(placeholder="输入消息，按 Enter 发送，F1 切换侧边栏", id="prompt")
                    yield Button("发送", id="send", variant="primary")
            yield SidebarResizer(id="sidebar-resizer")
            with Vertical(id="sidebar"):
                yield Static("JAGENT", id="sidebar-title")
                with Horizontal(id="sidebar-actions"):
                    yield Button("新建", id="new-chat", classes="sidebar-action")
                    yield Button("清空", id="clear-chat", classes="sidebar-action")
                yield Static("会话", classes="sidebar-section")
                yield Static("当前会话", id="session-name")
                yield Static("工具", classes="sidebar-section")
                yield Button("列出当前目录", id="tool-list", classes="sidebar-tool")
                yield Button("获取当前目录", id="tool-cwd", classes="sidebar-tool")
                yield Button("获取时间", id="tool-date", classes="sidebar-tool")
                yield Button("查看 README", id="tool-readme", classes="sidebar-tool")
                yield Vertical(id="sidebar-spacer")
                yield Static("本地文件操作助手", id="sidebar-footer")
        yield Footer()

    async def on_mount(self) -> None:
        self.register_theme(JAGENT_THEME)
        self.theme = "jagent"
        sidebar = self.query_one("#sidebar")
        sidebar.styles.width = self._sidebar_width
        resizer = self.query_one("#sidebar-resizer")
        resizer.styles.width = 1
        await self._render_history()
        self._set_status("就绪", "#d9d9d9")
        self.query_one("#prompt", Input).focus()

    async def _render_history(self) -> None:
        history = self._session.messages
        if not history:
            return
        chat = self.query_one("#chat", VerticalScroll)
        try:
            welcome = self.query_one(WelcomeMessage)
        except Exception:
            welcome = None
        if welcome is not None:
            await welcome.remove()
        for message in history:
            role = message.get("role")
            content = message.get("content")
            if not isinstance(content, str) or not content:
                continue
            if role == "user":
                await chat.mount(UserMessage(content))
            elif role == "assistant":
                await chat.mount(AssistantMessage(content))
            elif role == "tool":
                await chat.mount(ToolResultMessage("历史结果", content))
        self._scroll_end()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._submit(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send":
            self._submit(self.query_one("#prompt", Input).value)
            return
        if event.button.id == "new-chat":
            if not self._busy:
                self._clear_chat()
            return
        if event.button.id == "clear-chat":
            if not self._busy:
                self._clear_chat()
            return
        if event.button.id == "tool-list":
            self._submit("列出当前目录下的所有文件和子目录")
            return
        if event.button.id == "tool-cwd":
            self._submit("获取当前工作目录")
            return
        if event.button.id == "tool-date":
            self._submit("获取当前日期和时间")
            return
        if event.button.id == "tool-readme":
            self._submit("读取 README.md 的内容")

    def _submit(self, value: str) -> None:
        prompt = value.strip()
        if not prompt or self._busy:
            return
        self.query_one("#prompt", Input).value = ""
        self._run_turn(prompt)

    @work(exclusive=True, group="turn")
    async def _run_turn(self, prompt: str) -> None:
        self._busy = True
        self._set_busy(True)
        self._set_status("思考中", "#bfbfbf")
        chat = self.query_one("#chat", VerticalScroll)
        failed = False

        await chat.mount(UserMessage(prompt))
        self._scroll_end()
        assistant: AssistantMessage | None = None

        try:
            async for event in self._session.send(prompt):
                if isinstance(event, AssistantStarted):
                    assistant = AssistantMessage()
                    await chat.mount(assistant)
                    self._set_status("正在生成回复", "#bfbfbf")
                    self._scroll_end()
                elif isinstance(event, TextDelta):
                    if assistant is None:
                        assistant = AssistantMessage()
                        await chat.mount(assistant)
                    assistant.append_text(event.text)
                    self._scroll_end()
                elif isinstance(event, AssistantCompleted):
                    if assistant is not None and assistant.is_empty:
                        await assistant.remove()
                    assistant = None
                elif isinstance(event, ToolCallStarted):
                    self._set_status(f"执行工具 {event.name}", "#bfbfbf")
                elif isinstance(event, ToolCallFinished):
                    await chat.mount(ToolResultMessage(event.name, event.output))
                    self._set_status("等待模型继续", "#bfbfbf")
                    self._scroll_end()
        except Exception as exc:
            failed = True
            await chat.mount(ErrorMessage(f"{type(exc).__name__}: {exc}"))
            self._scroll_end()
        finally:
            if assistant is not None and assistant.is_empty:
                await assistant.remove()
            self._busy = False
            self._set_busy(False)
            self._set_status("请求失败" if failed else "就绪", "#a6a6a6" if failed else "#d9d9d9")
            self.query_one("#prompt", Input).focus()

    def action_clear_chat(self) -> None:
        if not self._busy:
            self._clear_chat()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        resizer = self.query_one("#sidebar-resizer")
        sidebar.toggle_class("hidden")
        resizer.toggle_class("hidden")

    def begin_sidebar_resize(self, screen_x: int) -> None:
        sidebar = self.query_one("#sidebar")
        if sidebar.has_class("hidden"):
            return
        self._resizing = True
        self._resize_start_x = screen_x
        self._resize_start_width = self._sidebar_width

    def update_sidebar_resize(self, screen_x: int) -> None:
        if not self._resizing:
            return
        delta = self._resize_start_x - screen_x
        new_width = max(16, min(40, self._resize_start_width + delta))
        if new_width != self._sidebar_width:
            self._sidebar_width = new_width
            self.query_one("#sidebar").styles.width = new_width

    def end_sidebar_resize(self) -> None:
        self._resizing = False
        self.query_one("#sidebar-resizer").remove_class("dragging")

    @work(group="view")
    async def _clear_chat(self) -> None:
        await self._session.clear()
        chat = self.query_one("#chat", VerticalScroll)
        await chat.remove_children()
        await chat.mount(WelcomeMessage())
        self._scroll_end()
        self._set_status("就绪", "#d9d9d9")
        self.query_one("#prompt", Input).focus()

    def _set_busy(self, busy: bool) -> None:
        prompt = self.query_one("#prompt", Input)
        button = self.query_one("#send", Button)
        prompt.disabled = busy
        button.disabled = busy
        prompt.placeholder = (
            "正在生成回复..." if busy else "输入消息，按 Enter 发送，F1 切换侧边栏"
        )

    def _set_status(self, message: str, color: str) -> None:
        text = Text()
        text.append("● ", style=color)
        text.append(message, style="dim")
        self.query_one("#status", Static).update(text)

    def _scroll_end(self) -> None:
        self.call_after_refresh(
            self.query_one("#chat", VerticalScroll).scroll_end,
            animate=False,
        )
