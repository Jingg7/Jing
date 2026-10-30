from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

SKILLS_DIRECTORY = Path(".agents") / "skills"
SKILL_FILENAME = "SKILL.md"
MAX_FRONTMATTER_LINES = 512
DEFAULT_MAX_READ_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    directory: Path

    @property
    def skill_file(self) -> Path:
        return self.directory / SKILL_FILENAME


def _read_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            if handle.readline().strip() != "---":
                return None, "缺少 YAML Frontmatter"
            lines: list[str] = []
            for _ in range(MAX_FRONTMATTER_LINES):
                line = handle.readline()
                if not line:
                    return None, "YAML Frontmatter 未闭合"
                if line.rstrip() in {"---", "..."}:
                    break
                lines.append(line)
            else:
                return None, "YAML Frontmatter 过长或未闭合"
    except OSError as exc:
        return None, f"读取失败: {exc}"

    try:
        data = yaml.safe_load("".join(lines))
    except yaml.YAMLError as exc:
        return None, f"YAML 解析失败: {exc}"
    if not isinstance(data, dict):
        return None, "YAML Frontmatter 必须是对象"
    return data, None


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _one_line(text: str) -> str:
    return " ".join(text.split())


class SkillManager:
    def __init__(
        self,
        skills: Iterable[Skill] | None = None,
        *,
        project_root: str | Path | None = None,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
    ):
        self._project_root = Path(
            project_root if project_root is not None else Path.cwd()
        ).expanduser().resolve()
        self._max_read_bytes = max_read_bytes
        self._skills: dict[str, Skill] = {}
        for skill in skills or ():
            self._skills.setdefault(skill.name, skill)

    @classmethod
    def discover(
        cls,
        project_root: str | Path | None = None,
        *,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        skills_directory: str | Path | None = None,
    ) -> "SkillManager":
        root = Path(
            project_root if project_root is not None else Path.cwd()
        ).expanduser().resolve()
        directory = (
            Path(skills_directory)
            if skills_directory is not None
            else root / SKILLS_DIRECTORY
        ).expanduser().resolve()

        skills: list[Skill] = []
        if directory.is_dir():
            children = sorted(directory.iterdir(), key=lambda item: item.name.lower())
            for child in children:
                if not child.is_dir():
                    continue
                skill_file = child / SKILL_FILENAME
                if not skill_file.is_file():
                    continue
                data, error = _read_frontmatter(skill_file)
                if error is not None or data is None:
                    continue
                name = data.get("name")
                description = data.get("description")
                if not isinstance(name, str) or not name.strip():
                    continue
                if not isinstance(description, str) or not description.strip():
                    continue
                skills.append(
                    Skill(
                        name=name.strip(),
                        description=description.strip(),
                        directory=child.resolve(),
                    )
                )
        return cls(skills, project_root=root, max_read_bytes=max_read_bytes)

    @property
    def skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def prompt_section(self) -> str:
        if not self._skills:
            return ""
        lines = ["You have access to the following skills:"]
        for skill in self._skills.values():
            lines.append(f"- `{skill.name}`: {_one_line(skill.description)}")
        lines.append("")
        lines.append(
            "Use the `loadSkill` tool to load the full instructions of a skill "
            "when needed. You can also load additional files referenced by a "
            "skill by passing the optional `filename` parameter."
        )
        return "\n".join(lines)

    def load(self, name: str, filename: str | None = None) -> str:
        skill = self._skills.get(name)
        if skill is None:
            available = "、".join(self._skills) or "无"
            return f"未找到 Skill: {name}。可用 Skill: {available}"

        raw_filename = (filename or "").strip()
        if not raw_filename:
            return self._read_file(skill, skill.skill_file)

        target, error = self._resolve_exact_path(skill, raw_filename)
        if error is not None:
            return error
        if target is not None:
            return self._read_file(skill, target)

        raw_path = Path(raw_filename)
        if len(raw_path.parts) == 1 and raw_path.name not in {"", ".", ".."}:
            matches = self._find_by_filename(skill, raw_path.name)
            if len(matches) == 1:
                return self._read_file(skill, matches[0])
            if len(matches) > 1:
                lines = [
                    f"找到多个名为 {raw_path.name} 的文件，请使用完整路径作为 "
                    "filename 重新调用 loadSkill:"
                ]
                lines.extend(f"- {match}" for match in matches)
                return "\n".join(lines)

        return f"未找到文件: {raw_filename}（Skill: {name}）"

    def _resolve_exact_path(
        self,
        skill: Skill,
        raw_filename: str,
    ) -> tuple[Path | None, str | None]:
        requested = Path(raw_filename).expanduser()
        if requested.is_absolute():
            candidates = [requested]
        else:
            candidates = [
                skill.directory / requested,
                self._project_root / requested,
            ]

        outside: Path | None = None
        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if not _is_within(resolved, skill.directory):
                if resolved.exists():
                    outside = resolved
                continue
            if resolved.is_file():
                return resolved, None

        if outside is not None:
            return None, f"拒绝读取 Skill 目录之外的文件: {outside}"
        return None, None

    def _find_by_filename(self, skill: Skill, filename: str) -> list[Path]:
        matches: set[Path] = set()
        try:
            entries = skill.directory.rglob("*")
            for entry in entries:
                if not entry.is_file() or entry.name != filename:
                    continue
                resolved = entry.resolve()
                if _is_within(resolved, skill.directory):
                    matches.add(resolved)
        except OSError:
            return []
        return sorted(matches, key=lambda path: str(path).lower())

    def _read_file(self, skill: Skill, path: Path) -> str:
        from .tools.filesystem.common import read_text_file

        resolved = path.expanduser().resolve()
        if not _is_within(resolved, skill.directory):
            return f"拒绝读取 Skill 目录之外的文件: {resolved}"
        try:
            content = read_text_file(resolved, self._max_read_bytes)
        except ValueError as exc:
            return f"读取失败: {exc}"
        return content or "(文件内容为空)"


def discover_skills(
    project_root: str | Path | None = None,
    *,
    max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
    skills_directory: str | Path | None = None,
) -> SkillManager:
    return SkillManager.discover(
        project_root,
        max_read_bytes=max_read_bytes,
        skills_directory=skills_directory,
    )


def compose_system_prompt(base_prompt: str, skills: SkillManager) -> str:
    section = skills.prompt_section()
    if not section:
        return base_prompt
    base = (base_prompt or "").rstrip()
    return f"{base}\n\n{section}" if base else section
