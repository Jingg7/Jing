from __future__ import annotations

from typing import Any

from ..skills import SkillManager
from .base import BaseTool


class LoadSkillTool(BaseTool):
    name = "loadSkill"
    description = (
        "加载指定 Skill 的完整说明或附件文件。仅提供 name 时返回该 Skill 的 "
        "SKILL.md 全文；同时提供 filename 时读取 Skill 目录内的对应文件。"
        "filename 支持相对于 Skill 目录、相对于项目根目录以及绝对路径。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "要加载的 Skill 名称",
            },
            "filename": {
                "type": "string",
                "description": (
                    "可选。需要加载的 Skill 附件文件路径或文件名。"
                    "省略时加载 SKILL.md。"
                ),
            },
        },
        "required": ["name"],
    }

    def __init__(self, skills: SkillManager):
        self._skills = skills

    def run(self, arguments: dict[str, Any]) -> str:
        filename = arguments.get("filename")
        if filename is not None and not isinstance(filename, str):
            return "参数 filename 必须是字符串"
        return self._skills.load(str(arguments["name"]), filename)
