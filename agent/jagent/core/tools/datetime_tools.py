from __future__ import annotations

import platform
import subprocess
from typing import Any

from .base import BaseTool


def get_date_by_command() -> str:
    if platform.system() == "Windows":
        date_out = subprocess.run(
            ["cmd", "/c", "date", "/t"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        ).stdout.strip()
        time_out = subprocess.run(
            ["cmd", "/c", "time", "/t"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        ).stdout.strip()
        return f"{date_out} {time_out}".strip()
    result = subprocess.run(["date"], capture_output=True, text=True)
    return (result.stdout or result.stderr).strip()


def check_leap_year(year: int) -> str:
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return f"{year}年是闰年"
    return f"{year}年不是闰年"


class GetDateTool(BaseTool):
    name = "getDate"
    description = "获取当前电脑的日期和时间"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        return get_date_by_command()


class IsLeapYearTool(BaseTool):
    name = "isLeapYear"
    description = "判断输入的年份是否为闰年"
    parameters = {
        "type": "object",
        "properties": {
            "year": {
                "type": "integer",
                "description": "要判断的年份，例如 2024",
            }
        },
        "required": ["year"],
    }

    def run(self, arguments: dict[str, Any]) -> str:
        return check_leap_year(int(arguments["year"]))
