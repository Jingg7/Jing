from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.bootstrap import create_session
from core.config import AgentConfig, LLMConfig
from core.history import HistoryStore
from core.skills import SkillManager, compose_system_prompt
from core.tools import FileToolConfig, build_default_registry


def write_skill(
    root: Path,
    directory: str,
    name: str,
    description: str,
    body: str = "Skill body",
) -> Path:
    skill_dir = root / ".agents" / "skills" / directory
    skill_dir.mkdir(parents=True)
    description_block = "\n".join(
        f"  {line}" for line in description.splitlines()
    )
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {json.dumps(name)}\n"
        f"description: |\n{description_block}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


class SkillDiscoveryTests(unittest.TestCase):
    def test_discovers_name_and_description(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = write_skill(
                root,
                "pdf-tools",
                "pdf-tools",
                "Extract text from PDF files.",
                "Long instructions that should not be loaded at startup.",
            )
            (skill_dir / "references").mkdir()
            (skill_dir / "references" / "guide.md").write_text(
                "guide", encoding="utf-8"
            )

            manager = SkillManager.discover(root)

            self.assertEqual(len(manager.skills), 1)
            skill = manager.skills[0]
            self.assertEqual(skill.name, "pdf-tools")
            self.assertEqual(skill.description, "Extract text from PDF files.")
            self.assertEqual(skill.directory, skill_dir.resolve())

    def test_ignores_invalid_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skills_root = root / ".agents" / "skills"
            (skills_root / "missing-file").mkdir(parents=True)
            write_skill(root, "missing-description", "no-description", "")
            (skills_root / "no-frontmatter").mkdir()
            (skills_root / "no-frontmatter" / "SKILL.md").write_text(
                "# no frontmatter", encoding="utf-8"
            )

            manager = SkillManager.discover(root)

            self.assertEqual(manager.skills, ())

    def test_prompt_contains_skill_info_and_load_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_skill(
                root,
                "one",
                "one",
                "First skill.\nSecond line.",
            )

            manager = SkillManager.discover(root)
            prompt = compose_system_prompt("Base prompt.", manager)

            self.assertIn("Base prompt.", prompt)
            self.assertIn("`one`", prompt)
            self.assertIn("First skill. Second line.", prompt)
            self.assertIn("loadSkill", prompt)


class SkillLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.skill_dir = write_skill(
            self.root,
            "pdf-tools",
            "pdf-tools",
            "Work with PDF files.",
            "Full skill instructions.",
        )
        self.references = self.skill_dir / "references"
        self.references.mkdir()
        (self.references / "guide.md").write_text("guide content", encoding="utf-8")
        self.manager = SkillManager.discover(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_loads_skill_markdown_when_filename_is_omitted(self) -> None:
        output = self.manager.load("pdf-tools")

        self.assertIn("Full skill instructions.", output)
        self.assertIn("pdf-tools", output)

    def test_loads_attachment_with_skill_relative_path(self) -> None:
        output = self.manager.load("pdf-tools", "references/guide.md")

        self.assertEqual(output, "guide content")

    def test_loads_attachment_with_project_relative_path(self) -> None:
        path = ".agents/skills/pdf-tools/references/guide.md"
        self.assertEqual(self.manager.load("pdf-tools", path), "guide content")

    def test_loads_attachment_with_absolute_path(self) -> None:
        path = str(self.references / "guide.md")
        self.assertEqual(self.manager.load("pdf-tools", path), "guide content")

    def test_recursively_finds_unique_filename(self) -> None:
        (self.references / "unique.txt").write_text("unique", encoding="utf-8")

        self.assertEqual(self.manager.load("pdf-tools", "unique.txt"), "unique")

    def test_returns_candidates_for_duplicate_filenames(self) -> None:
        other = self.skill_dir / "assets"
        other.mkdir()
        (other / "guide.md").write_text("other guide", encoding="utf-8")

        output = self.manager.load("pdf-tools", "guide.md")

        self.assertIn("找到多个", output)
        self.assertIn(str((self.references / "guide.md").resolve()), output)
        self.assertIn(str((other / "guide.md").resolve()), output)

    def test_rejects_paths_outside_skill_directory(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        outside_skill = self.skill_dir.parent / "secret.txt"
        outside_skill.write_text("secret", encoding="utf-8")

        output = self.manager.load("pdf-tools", "../secret.txt")
        self.assertIn("拒绝读取 Skill 目录之外的文件", output)

        output = self.manager.load("pdf-tools", str(outside))
        self.assertIn("拒绝读取 Skill 目录之外的文件", output)

    def test_reports_unknown_skill(self) -> None:
        output = self.manager.load("missing")

        self.assertIn("未找到 Skill", output)
        self.assertIn("pdf-tools", output)

    def test_default_registry_registers_load_skill(self) -> None:
        registry = build_default_registry(
            FileToolConfig(), skills=self.manager
        )

        self.assertIn("loadSkill", registry.names())
        self.assertEqual(
            registry.execute(
                "loadSkill",
                {"name": "pdf-tools", "filename": "references/guide.md"},
            ),
            "guide content",
        )


class SkillSessionTests(unittest.TestCase):
    def test_create_session_injects_skills_and_registers_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_skill(root, "demo", "demo", "Demo skill.")
            config = AgentConfig(
                llm=LLMConfig("http://localhost:1234/v1", "test", "key"),
                history_path=root / "history.json",
            )

            session = create_session(
                config,
                model=object(),
                history=HistoryStore(root / "history.json"),
                project_root=root,
            )

            self.assertIn("`demo`", session.messages[0]["content"])
            self.assertIn(
                "loadSkill",
                [tool["function"]["name"] for tool in session.tools],
            )


if __name__ == "__main__":
    unittest.main()
