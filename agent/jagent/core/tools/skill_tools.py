from __future__ import annotations

from typing import Any

from ..skills import SkillManager
from .base import BaseTool


class CreateSkillTool(BaseTool):
    name = "createSkill"
    description = (
        "根据用户的自然语言要求创建一个新的 Skill。工具会在项目根目录的 "
        ".agents/skills/<name>/SKILL.md 写入符合 Agent Skills 规范的 Markdown 文件。"
        "name 会规范化为小写英文字母、数字和连字符组成的格式；skillContext 是 "
        "SKILL.md 的完整内容，可以包含 YAML Frontmatter（建议提供 description）"
        "和正文，未提供 description 时会自动从正文首段生成。"
        "如果同名 Skill 已存在，工具不会覆盖原内容。需要 references/、scripts/ "
        "等附加目录或文件时，请继续调用 createDirectory、createFile 等文件工具。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Skill 名称，使用小写英文字母、数字和连字符，"
                    "例如 pdf-tools"
                ),
            },
            "skillContext": {
                "type": "string",
                "description": (
                    "需要写入 SKILL.md 的完整内容，包含 YAML Frontmatter"
                    "（description）和正文说明"
                ),
            },
        },
        "required": ["name", "skillContext"],
    }

    def __init__(self, skills: SkillManager):
        self._skills = skills

    def run(self, arguments: dict[str, Any]) -> str:
        name = arguments["name"]
        content = arguments["skillContext"]
        if not isinstance(name, str):
            return "参数 name 必须是字符串"
        if not isinstance(content, str):
            return "参数 skillContext 必须是字符串"
        return self._skills.create(name, content)


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
