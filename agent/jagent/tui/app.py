from __future__ import annotations

import asyncio
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Static

from core.config import AgentConfig
from core.context import ContextUsage
from core.sessions import SessionStore
from core.events import (
    AssistantCompleted,
    AssistantStarted,
    CompactionCompleted,
    CompactionFailed,
    CompactionStarted,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)
from core.session import AgentSession

from .theme import JAGENT_THEME
from .widgets import (
    AssistantMessage,
    CompactPanel,
    ErrorMessage,
    PromptInput,
    SessionListPanel,
    SlashCommandPanel,
    SLASH_COMMANDS,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
    WarningMessage,
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

    def __init__(
        self,
        session: AgentSession,
        *,
        config: AgentConfig | None = None,
        sessions: SessionStore | None = None,
    ):
        super().__init__()
        self._session = session
        self._config = config
        self._sessions = sessions or SessionStore(
            config.session.directory if config else Path(".agents") / "sessions"
        )
        self._session_id: str | None = None
        self._session_title = "未保存会话"
        self._palette_open = False
        self._suppress_palette = False
        self._busy = False
        ui_config = config.ui if config else None
        self._sidebar_width = ui_config.sidebar_width if ui_config else 22
        self._sidebar_min_width = ui_config.sidebar_min_width if ui_config else 16
        self._sidebar_max_width = ui_config.sidebar_max_width if ui_config else 40
        self._display_max_chars = (
            ui_config.display_max_chars if ui_config else 4000
        )
        self._resize_start_x = 0
        self._resize_start_width = self._sidebar_width
        self._resizing = False
        self._context_warning_shown = False

    @property
    def resizing(self) -> bool:
        return self._resizing

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="workspace"):
            with Vertical(id="main"):
                with Horizontal(id="toolbar"):
                    yield Static("对话", id="toolbar-title")
                    yield Static("上下文 --", id="context-usage")
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
                yield Static("MCP", classes="sidebar-section")
                yield Static("未加载", id="mcp-status")
                with VerticalScroll(id="mcp-list"):
                    yield Static("未加载", id="mcp-details", markup=False)
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
        self._update_session_label()
        self._load_mcp_status()
        usage = await self._refresh_context_state()
        if usage.warning:
            self._set_status("上下文已达 60%，请执行 /compact", "#d4a017")
        else:
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
                await chat.mount(
                    ToolResultMessage("历史结果", content, self._display_max_chars)
                )
        self._scroll_end()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._submit(event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._suppress_palette or self._palette_open:
            return
        value = event.value
        if self._busy:
            return
        if value == "/":
            self._palette_open = True
            self.push_screen(
                SlashCommandPanel(value),
                self._on_slash_selected,
            )

    def _on_slash_selected(self, command: str | None) -> None:
        self._palette_open = False
        self._suppress_palette = True
        try:
            if command is None:
                self.query_one("#prompt", Input).focus()
                return
            if command == "/save":
                self._set_prompt("/save ")
                return
            if command == "/resume":
                self._set_prompt("")
                self._resume_session("")
                return
            self._set_prompt("")
            self._submit(command)
        finally:
            self._suppress_palette = False

    def _set_prompt(self, value: str) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.value = value
        prompt.focus()
        if value:
            prompt.cursor_position = len(value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send":
            self._submit(self.query_one("#prompt", Input).value)
            return
        if event.button.id == "new-chat":
            if not self._busy:
                self._start_new_session()
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
        if self._handle_slash_command(prompt):
            self.query_one("#prompt", Input).value = ""
            return
        usage = self._session.context_usage
        if usage.warning:
            self._update_context_indicator()
            self._set_status(
                f"上下文已达 {usage.warning_percent}%，请先执行 /compact",
                "#d4a017",
            )
            self.query_one("#prompt", Input).focus()
            return
        self.query_one("#prompt", Input).value = ""
        self._run_turn(prompt)

    def _handle_slash_command(self, prompt: str) -> bool:
        if not prompt.startswith("/"):
            return False
        parts = prompt.split(maxsplit=1)
        command = parts[0].casefold()
        argument = parts[1].strip() if len(parts) > 1 else ""
        if command == "/compact":
            self._run_compact()
        elif command == "/new":
            self._start_new_session()
        elif command == "/resume":
            self._resume_session(argument)
        elif command == "/save":
            self._save_session(argument)
        elif command == "/quit":
            self.exit()
        elif command == "/clear":
            self._clear_chat()
        elif command == "/help":
            self._show_slash_help()
        else:
            self._mount_chat_message(ErrorMessage(f"未知命令：{command}"))
        return True

    @work(exclusive=True, group="session")
    async def _start_new_session(self) -> None:
        info = await asyncio.to_thread(self._sessions.create)
        history = self._sessions.history(info.session_id)
        await self._session.switch_history(history)
        self._session_id = info.session_id
        self._session_title = info.title
        await self._reload_chat()
        self._set_status(f"已新建会话 {info.session_id}", "#d9d9d9")

    @work(exclusive=True, group="session")
    async def _save_session(self, title: str) -> None:
        clean_title = " ".join(title.split())[:80]
        if not clean_title:
            clean_title = self._derive_session_title()
        if self._session_id is None:
            info = await asyncio.to_thread(self._sessions.create, clean_title)
            history = self._sessions.history(info.session_id)
            await asyncio.to_thread(history.save, self._session.messages)
            await self._session.switch_history(history)
            self._session_id = info.session_id
            self._sessions.save(info.session_id, clean_title, self._session.messages)
        else:
            self._sessions.save(self._session_id, clean_title, self._session.messages)
        info = self._sessions.get(self._session_id)
        self._session_title = info.title if info else clean_title
        self._update_session_label()
        self._set_status(f"已保存会话：{self._session_title}", "#d9d9d9")

    def _resume_session(self, query: str) -> None:
        if not query.strip():
            sessions = self._sessions.list_sessions()
            if not sessions:
                self._mount_chat_message(SystemMessage("暂无已保存的会话。"))
                return
            self.push_screen(SessionListPanel(sessions), self._on_session_selected)
            return
        info = self._sessions.find(query.strip())
        if info is None:
            self._mount_chat_message(ErrorMessage(f"未找到会话：{query.strip()}"))
            return
        self._switch_session(info.session_id)

    def _on_session_selected(self, session_id: str | None) -> None:
        if session_id:
            self._switch_session(session_id)

    @work(exclusive=True, group="session")
    async def _switch_session(self, session_id: str) -> None:
        try:
            history = self._sessions.history(session_id)
            await self._session.switch_history(history)
        except (FileNotFoundError, ValueError) as exc:
            await self.query_one("#chat", VerticalScroll).mount(ErrorMessage(str(exc)))
            self._scroll_end()
            return
        info = self._sessions.get(session_id)
        self._session_id = session_id
        self._session_title = info.title if info else session_id
        await self._reload_chat()
        self._set_status(f"已恢复会话：{self._session_title}", "#d9d9d9")

    def _derive_session_title(self) -> str:
        for message in self._session.messages:
            if message.get("role") != "user":
                continue
            content = str(message.get("content", "")).strip()
            if not content or content.startswith("以下是项目 AGENTS.md"):
                continue
            return " ".join(content.split())[:40]
        from datetime import datetime

        return f"会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    def _show_slash_help(self) -> None:
        lines = ["常用命令："]
        lines.extend(
            f"  {command.name}  {command.description}"
            for command in SLASH_COMMANDS
        )
        self._mount_chat_message(SystemMessage("\n".join(lines)))

    @work(group="view")
    async def _mount_chat_message(self, message) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(message)
        self._scroll_end()

    async def _reload_chat(self) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.remove_children()
        await chat.mount(WelcomeMessage())
        await self._render_history()
        self._update_session_label()
        await self._refresh_context_state()
        self.query_one("#prompt", Input).focus()

    def _update_session_label(self) -> None:
        label = self._session_title
        if self._session_id:
            label = f"{self._session_title}\n{self._session_id}"
        self.query_one("#session-name", Static).update(label)

    @work(exclusive=True, group="mcp")
    async def _load_mcp_status(self) -> None:
        self._render_mcp_sidebar()
        manager = self._session.mcp_manager
        if manager is not None:
            await asyncio.to_thread(manager.start)
            self._session.refresh_mcp_tools()
        self._render_mcp_sidebar()
        self._update_context_indicator()

    def _render_mcp_sidebar(self) -> None:
        status = self.query_one("#mcp-status", Static)
        details = self.query_one("#mcp-details", Static)
        manager = self._session.mcp_manager
        if manager is None:
            status.update("未配置")
            details.update("当前会话未启用 MCP")
            return
        servers = manager.servers
        connected = manager.connected_server_names
        errors = manager.startup_errors
        if manager.is_starting:
            status.update(
                Text(f"正在连接 {len(servers)} 个 Server...", style="#d4a017")
            )
        elif servers:
            status.update(
                Text(
                    f"已连接 {len(connected)}/{len(servers)}",
                    style="#d9d9d9" if connected else "#a6a6a6",
                )
            )
        else:
            status.update("未配置")

        lines: list[str] = []
        tools_by_server = manager.server_tools
        for server in servers:
            marker = "●" if server.name in connected else "○"
            lines.append(f"{marker} {server.name}")
            tools = tools_by_server.get(server.name, ())
            if tools:
                lines.append("  工具： " + ", ".join(tools))
            elif server.name in connected:
                lines.append("  无可用工具")
            else:
                lines.append("  未连接")
        if errors:
            lines.append("")
            lines.extend(f"! {error}" for error in errors)
        if not lines:
            lines.append("未发现 .mcp.json 配置")
        details.update("\n".join(lines))

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
                    self._update_context_indicator()
                elif isinstance(event, ToolCallStarted):
                    self._set_status(f"执行工具 {event.name}", "#bfbfbf")
                elif isinstance(event, ToolCallFinished):
                    await chat.mount(
                        ToolResultMessage(
                            event.name,
                            event.output,
                            self._display_max_chars,
                        )
                    )
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
            usage = await self._refresh_context_state()
            if failed:
                self._set_status("请求失败", "#a6a6a6")
            elif usage.warning:
                self._set_status(
                    f"上下文已达 {usage.warning_percent}%，请执行 /compact",
                    "#d4a017",
                )
            else:
                self._set_status("就绪", "#d9d9d9")
            self.query_one("#prompt", Input).focus()

    @work(exclusive=True, group="turn")
    async def _run_compact(self) -> None:
        self._busy = True
        self._set_busy(True)
        self.query_one("#prompt", Input).placeholder = "正在压缩上下文..."
        self._set_status("正在压缩上下文", "#bfbfbf")
        chat = self.query_one("#chat", VerticalScroll)
        completed: CompactionCompleted | None = None

        try:
            async for event in self._session.compact():
                if isinstance(event, CompactionStarted):
                    self._set_status(
                        f"已归档 {event.archive_id}，正在生成摘要",
                        "#bfbfbf",
                    )
                elif isinstance(event, CompactionCompleted):
                    completed = event
                elif isinstance(event, CompactionFailed):
                    await chat.mount(ErrorMessage(event.error))
                    self._scroll_end()
        except Exception as exc:
            await chat.mount(ErrorMessage(f"{type(exc).__name__}: {exc}"))
            self._scroll_end()
        finally:
            self._busy = False
            self._set_busy(False)
            if completed is not None:
                self._context_warning_shown = False
                usage = await self._refresh_context_state()
                await chat.mount(
                    SystemMessage(
                        "上下文压缩完成，归档编号："
                        f"{completed.archive_id}。如需历史细节，"
                        "Agent 可以调用 recallContext 工具。"
                    )
                )
                self._scroll_end()
                if usage.warning:
                    self._set_status(
                        f"压缩后上下文仍超过 {usage.warning_percent}%，请再次执行 /compact",
                        "#d4a017",
                    )
                else:
                    self._set_status("压缩完成", "#d9d9d9")
                self.push_screen(
                    CompactPanel(
                        completed.archive_id,
                        completed.original,
                        completed.summary,
                    )
                )
            else:
                await self._refresh_context_state()
                self._set_status("压缩失败，可重新执行 /compact", "#a6a6a6")
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
        new_width = max(
            self._sidebar_min_width,
            min(self._sidebar_max_width, self._resize_start_width + delta),
        )
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
        self._context_warning_shown = False
        await self._refresh_context_state()
        self._set_status("就绪", "#d9d9d9")
        self.query_one("#prompt", Input).focus()

    def _set_busy(self, busy: bool) -> None:
        prompt = self.query_one("#prompt", Input)
        button = self.query_one("#send", Button)
        prompt.disabled = busy
        button.disabled = busy
        prompt.placeholder = (
            "正在生成回复..." if busy else self._prompt_placeholder()
        )

    def _prompt_placeholder(self, usage: ContextUsage | None = None) -> str:
        current = usage or self._session.context_usage
        if current.warning:
            return (
                f"上下文已达 {current.warning_percent}%，"
                "请输入 /compact 压缩上下文"
            )
        return "输入消息，按 Enter 发送，F1 切换侧边栏"

    def _update_context_indicator(self) -> ContextUsage:
        usage = self._session.context_usage
        color = "#d4a017" if usage.warning else "#bfbfbf"
        text = Text()
        text.append(
            f"上下文 {usage.used_tokens / 1000:.1f}k / "
            f"{usage.window_tokens / 1000:.1f}k",
            style=color,
        )
        text.append(f" · {usage.percent:.1f}%", style=color)
        if usage.is_default_window:
            text.append("（默认）", style="dim")
        if usage.warning:
            text.append(" · 请执行 /compact", style="bold #d4a017")
        self.query_one("#context-usage", Static).update(text)
        if not self._busy:
            self.query_one("#prompt", Input).placeholder = self._prompt_placeholder(
                usage
            )
        return usage

    async def _refresh_context_state(self) -> ContextUsage:
        usage = self._update_context_indicator()
        if not usage.warning:
            self._context_warning_shown = False
            return usage
        if self._context_warning_shown:
            return usage

        self._context_warning_shown = True
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(
            WarningMessage(
                f"上下文已使用 {usage.percent}%"
                f"（{usage.used_tokens / 1000:.1f}k / "
                f"{usage.window_tokens / 1000:.1f}k），已达到 {usage.warning_percent}% 警告阈值。"
                "jagent 已暂停接受普通提示词，请输入 /compact 压缩上下文后再继续。"
            )
        )
        self._scroll_end()
        return usage

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
