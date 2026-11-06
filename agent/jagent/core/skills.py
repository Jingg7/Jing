from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

SKILLS_DIRECTORY = Path(".agents") / "skills"
SKILL_FILENAME = "SKILL.md"
MAX_FRONTMATTER_LINES = 512
DEFAULT_MAX_READ_BYTES = 1024 * 1024
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    directory: Path

    @property
    def skill_file(self) -> Path:
        return self.directory / SKILL_FILENAME


def _read_frontmatter(
    path: Path,
    max_frontmatter_lines: int = MAX_FRONTMATTER_LINES,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            if handle.readline().strip() != "---":
                return None, "缺少 YAML Frontmatter"
            lines: list[str] = []
            for _ in range(max_frontmatter_lines):
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


def normalize_skill_name(raw: str) -> str:
    candidate = re.sub(r"[\s_]+", "-", raw.strip().lower())
    candidate = re.sub(r"-{2,}", "-", candidate).strip("-")
    if not candidate or not SKILL_NAME_PATTERN.fullmatch(candidate):
        raise ValueError(
            "无效的 Skill 名称，必须由小写英文字母、数字和连字符组成，"
            "例如 pdf-tools"
        )
    return candidate


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str, str | None]:
    text = content.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, None

    data_lines: list[str] = []
    end_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip() in {"---", "..."}:
            end_index = index
            break
        data_lines.append(line)
    if end_index is None:
        return {}, text, "YAML Frontmatter 未闭合"

    try:
        data = yaml.safe_load("\n".join(data_lines)) or {}
    except yaml.YAMLError as exc:
        return {}, text, f"YAML Frontmatter 解析失败: {exc}"
    if not isinstance(data, dict):
        return {}, text, "YAML Frontmatter 必须是对象"
    body = "\n".join(lines[end_index + 1 :])
    return data, body, None


def _derive_description(body: str) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    headings: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith("#"):
            if not headings and not current and not paragraphs:
                headings.append(line.lstrip("#").strip())
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    candidate = paragraphs[0] if paragraphs else (headings[0] if headings else "")
    return _one_line(candidate)


class SkillManager:
    def __init__(
        self,
        skills: Iterable[Skill] | None = None,
        *,
        project_root: str | Path | None = None,
        skills_directory: str | Path | None = None,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_frontmatter_lines: int = MAX_FRONTMATTER_LINES,
    ):
        root = Path(
            project_root if project_root is not None else Path.cwd()
        ).expanduser().resolve()
        if skills_directory is None:
            skills_path = root / SKILLS_DIRECTORY
        else:
            skills_path = Path(skills_directory).expanduser()
            if not skills_path.is_absolute():
                skills_path = root / skills_path
        self._project_root = root
        self._skills_directory = skills_path.resolve()
        self._max_read_bytes = max_read_bytes
        self._max_frontmatter_lines = max_frontmatter_lines
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
        max_frontmatter_lines: int = MAX_FRONTMATTER_LINES,
    ) -> "SkillManager":
        root = Path(
            project_root if project_root is not None else Path.cwd()
        ).expanduser().resolve()
        directory = Path(skills_directory) if skills_directory is not None else root / SKILLS_DIRECTORY
        directory = directory.expanduser()
        if not directory.is_absolute():
            directory = root / directory
        directory = directory.resolve()

        skills: list[Skill] = []
        if directory.is_dir():
            children = sorted(directory.iterdir(), key=lambda item: item.name.lower())
            for child in children:
                if not child.is_dir():
                    continue
                skill_file = child / SKILL_FILENAME
                if not skill_file.is_file():
                    continue
                data, error = _read_frontmatter(
                    skill_file,
                    max_frontmatter_lines,
                )
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
        return cls(
            skills,
            project_root=root,
            skills_directory=directory,
            max_read_bytes=max_read_bytes,
            max_frontmatter_lines=max_frontmatter_lines,
        )

    @property
    def skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills.values())

    @property
    def skills_directory(self) -> Path:
        return self._skills_directory

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

    def create(self, name: str, content: str) -> str:
        if not isinstance(content, str) or not content.strip():
            return "Skill 内容不能为空"

        try:
            skill_name = normalize_skill_name(str(name))
        except ValueError as exc:
            return str(exc)

        target_directory = (self._skills_directory / skill_name).resolve()
        if not _is_within(target_directory, self._skills_directory):
            return f"拒绝在 Skill 目录之外创建 Skill: {target_directory}"
        if skill_name in self._skills or target_directory.exists():
            return (
                f"Skill 已存在: {skill_name}（{target_directory}），"
                "未做任何修改。如需更新请使用 editFile 等文件工具。"
            )

        metadata, body, error = _split_frontmatter(content)
        if error is not None:
            return f"无法解析 skillContext: {error}"

        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            description = _derive_description(body)
        description = _one_line(description)
        if not description:
            return (
                "无法从 skillContext 中获取有效的 description，"
                "请在 YAML Frontmatter 中提供 description 或补充正文内容"
            )

        body_text = body.strip()
        if not body_text:
            return "skillContext 缺少正文内容"

        frontmatter: dict[str, Any] = {
            "name": skill_name,
            "description": description,
        }
        for key, value in metadata.items():
            if key not in frontmatter:
                frontmatter[key] = value

        try:
            target_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return f"Skill 已存在: {skill_name}（{target_directory}），未做任何修改。"
        except OSError as exc:
            return f"创建 Skill 失败: {exc}"

        skill_file = target_directory / SKILL_FILENAME
        serialized = yaml.safe_dump(
            frontmatter,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).strip()
        text = f"---\n{serialized}\n---\n\n{body_text}\n"
        try:
            with skill_file.open("x", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except FileExistsError:
            return f"Skill 已存在: {skill_name}（{target_directory}），未做任何修改。"
        except OSError as exc:
            return f"创建 Skill 失败: {exc}"

        self._skills[skill_name] = Skill(
            name=skill_name,
            description=description,
            directory=target_directory,
        )
        return (
            f"已创建 Skill: {skill_name}\n"
            f"目录: {target_directory}\n"
            f"文件: {skill_file}\n"
            "如需添加 references/、scripts/ 等目录或其他辅助文件，"
            "请继续使用 createDirectory、createFile 等文件工具。"
        )

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
    max_frontmatter_lines: int = MAX_FRONTMATTER_LINES,
) -> SkillManager:
    return SkillManager.discover(
        project_root,
        max_read_bytes=max_read_bytes,
        skills_directory=skills_directory,
        max_frontmatter_lines=max_frontmatter_lines,
    )


def compose_system_prompt(base_prompt: str, skills: SkillManager) -> str:
    section = skills.prompt_section()
    if not section:
        return base_prompt
    base = (base_prompt or "").rstrip()
    return f"{base}\n\n{section}" if base else section
