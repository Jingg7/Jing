from __future__ import annotations

import subprocess
from typing import Any

from .base import BaseTool

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_OUTPUT_CHARS = 6000


class RunCliTool(BaseTool):
    name = "RunCli"
    description = (
        "在本地执行已安装的命令行程序（CLI）。"
        "command 为程序名称，args 为参数列表。"
        "返回标准输出、标准错误和退出码，便于判断执行结果。"
        "命令以运行本程序的当前用户权限执行。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的命令行程序名称或路径，例如 python、git、ls",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "传递给程序的参数列表，例如 [\"--version\"]",
            },
        },
        "required": ["command"],
    }

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ):
        self._timeout = timeout
        self._max_output_chars = max_output_chars

    def run(self, arguments: dict[str, Any]) -> str:
        command = str(arguments["command"]).strip()
        if not command:
            return "命令执行失败：command 不能为空"

        raw_args = arguments.get("args", [])
        if raw_args is None:
            raw_args = []
        if not isinstance(raw_args, list):
            return "命令执行失败：args 必须是字符串数组"

        argv = [command, *(str(arg) for arg in raw_args)]

        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                timeout=self._timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return self._format_timeout(command, exc)
        except FileNotFoundError:
            return f"命令执行失败：未找到可执行程序（{command}）"
        except OSError as exc:
            return f"命令执行失败：无法启动 {command}: {exc}"

        stdout = self._truncate(self._decode_output(result.stdout).strip())
        stderr = self._truncate(self._decode_output(result.stderr).strip())
        return "\n".join(
            [
                f"退出码: {result.returncode}",
                "标准输出:",
                stdout or "(空)",
                "标准错误:",
                stderr or "(空)",
            ]
        )

    def _format_timeout(self, command: str, exc: subprocess.TimeoutExpired) -> str:
        sections = [f"命令执行超时（超过 {self._timeout:g} 秒）: {command}"]
        stdout = self._decode_output(exc.stdout).strip()
        if stdout:
            sections.append("超时前标准输出:")
            sections.append(self._truncate(stdout))
        stderr = self._decode_output(exc.stderr).strip()
        if stderr:
            sections.append("超时前标准错误:")
            sections.append(self._truncate(stderr))
        return "\n".join(sections)

    def _truncate(self, text: str) -> str:
        limit = self._max_output_chars
        if limit <= 0 or len(text) <= limit:
            return text
        omitted = len(text) - limit
        return (
            f"{text[:limit]}\n"
            f"...[输出已截断：仅显示前 {limit} 个字符，"
            f"另有 {omitted} 个字符被省略]"
        )

    @staticmethod
    def _decode_output(data: bytes | str | None) -> str:
        if not data:
            return ""
        if isinstance(data, str):
            return data
        for encoding in ("utf-8", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
