from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from core.sessions import SessionInfo


@dataclass(frozen=True)
class SlashCommand:
    name: str
    description: str
    takes_argument: bool = False


SLASH_COMMANDS = (
    SlashCommand("/new", "新建会话"),
    SlashCommand("/resume", "恢复已保存的会话（可附会话编号）"),
    SlashCommand("/save", "保存当前会话（可附名称）", True),
    SlashCommand("/quit", "退出 JAgent"),
    SlashCommand("/compact", "压缩上下文"),
    SlashCommand("/clear", "清空当前会话"),
    SlashCommand("/help", "显示常用命令"),
)


class SlashCommandPanel(ModalScreen[str | None]):
    BINDINGS = [("escape", "close", "关闭")]

    def __init__(self, filter_text: str = "/"):
        super().__init__()
        self._filter = filter_text.strip().casefold() or "/"

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(command.name for command in self._filtered_commands)

    def compose(self) -> ComposeResult:
        with Vertical(id="slash-panel"):
            yield Static("命令", id="slash-panel-title")
            yield Static("使用 ↑↓ 选择，Enter 确认，Esc 关闭", id="slash-panel-help")
            yield OptionList(id="slash-command-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#slash-command-list", OptionList)
        commands = self._filtered_commands
        if commands:
            for command in commands:
                option_list.add_option(
                    Option(self._render_command(command), id=command.name)
                )
            option_list.highlighted = 0
        else:
            option_list.add_option(
                Option("没有匹配的命令", id="__no-match__", disabled=True)
            )
        option_list.focus()

    @property
    def _filtered_commands(self) -> tuple[SlashCommand, ...]:
        if not self._filter.startswith("/"):
            return SLASH_COMMANDS
        return tuple(
            command
            for command in SLASH_COMMANDS
            if command.name.casefold().startswith(self._filter)
        )

    @staticmethod
    def _render_command(command: SlashCommand) -> Text:
        text = Text()
        text.append(command.name, style="bold #ffffff")
        text.append("  ")
        text.append(command.description, style="dim")
        return text

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        command = str(event.option.id or "")
        if command.startswith("/"):
            self.dismiss(command)

    def action_close(self) -> None:
        self.dismiss(None)


class SessionListPanel(ModalScreen[str | None]):
    BINDINGS = [("escape", "close", "关闭")]

    def __init__(self, sessions: Sequence[SessionInfo]):
        super().__init__()
        self._sessions = tuple(sessions)

    def compose(self) -> ComposeResult:
        with Vertical(id="session-panel"):
            yield Static("恢复会话", id="session-panel-title")
            yield Static("使用 ↑↓ 选择，Enter 恢复，Esc 关闭", id="session-panel-help")
            yield OptionList(id="session-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#session-list", OptionList)
        if self._sessions:
            for session in self._sessions:
                timestamp = session.updated_at.strftime("%Y-%m-%d %H:%M")
                prompt = Text()
                prompt.append(session.title, style="bold #ffffff")
                prompt.append(f"\n{session.session_id} · {timestamp}", style="dim")
                option_list.add_option(Option(prompt, id=session.session_id))
            option_list.highlighted = 0
        else:
            option_list.add_option(
                Option("暂无已保存的会话", id="__empty__", disabled=True)
            )
        option_list.focus()

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        session_id = str(event.option.id or "")
        if session_id and not session_id.startswith("__"):
            self.dismiss(session_id)

    def action_close(self) -> None:
        self.dismiss(None)
