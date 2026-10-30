from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.tools import FileToolConfig, build_default_registry


class FileToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.registry = build_default_registry(FileToolConfig())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def execute(self, name: str, **arguments: object) -> str:
        return self.registry.execute(name, arguments)

    def test_default_registry_contains_all_tools(self) -> None:
        names = set(self.registry.names())
        self.assertEqual(len(names), 16)
        self.assertIn("getDate", names)
        self.assertIn("readFile", names)
        self.assertIn("renameFileOrDirectory", names)
        self.assertIn("fetchWeb", names)
        self.assertIn("searchWeb", names)
        self.assertIn("RunCli", names)
        self.assertIn("loadSkill", names)

    def test_current_directory(self) -> None:
        output = self.execute("getCurrentDirectory")
        self.assertIn(str(Path.cwd().resolve()), output)

    def test_file_lifecycle(self) -> None:
        nested = self.root / "nested" / "child"
        self.assertIn("已创建目录", self.execute("createDirectory", path=str(nested)))

        created = self.execute(
            "createFile",
            directory=str(nested),
            filename="notes.txt",
            content="hello world\n你好",
        )
        self.assertIn("已创建文件", created)

        self.assertIn("文件已存在", self.execute(
            "createFile",
            directory=str(nested),
            filename="notes.txt",
            content="overwrite",
        ))

        listing = self.execute("listDirectory", path=str(nested))
        self.assertIn("[F] notes.txt", listing)

        file_type = self.execute("getFileType", path=str(nested / "notes.txt"))
        self.assertIn("文本文件", file_type)

        content = self.execute("readFile", path=str(nested / "notes.txt"))
        self.assertEqual(content, "hello world\n你好")

        edited = self.execute(
            "editFile",
            path=str(nested / "notes.txt"),
            old_content="world",
            content="python",
        )
        self.assertIn("已替换", edited)
        self.assertEqual(
            self.execute("readFile", path=str(nested / "notes.txt")),
            "hello python\n你好",
        )

        renamed = self.execute(
            "renameFileOrDirectory",
            old_path=str(nested / "notes.txt"),
            new_path=str(nested / "readme.md"),
        )
        self.assertIn("已重命名", renamed)
        self.assertTrue((nested / "readme.md").exists())

        self.assertIn("已删除文件", self.execute(
            "deleteFile",
            path=str(nested / "readme.md"),
        ))

        (nested / "extra.txt").write_text("extra", encoding="utf-8")
        self.assertIn("已删除目录", self.execute(
            "deleteDirectory",
            path=str(self.root / "nested"),
        ))
        self.assertFalse((self.root / "nested").exists())

    def test_binary_file_is_rejected(self) -> None:
        binary = self.root / "data.bin"
        binary.write_bytes(b"\x00\x01\x02binary")
        output = self.execute("readFile", path=str(binary))
        self.assertIn("仅支持纯文本文件", output)
        self.assertIn("二进制文件", self.execute("getFileType", path=str(binary)))

    def test_missing_argument_is_reported(self) -> None:
        self.assertEqual(self.registry.execute("readFile", {}), "缺少参数: 'path'")

    def test_unknown_tool_is_reported(self) -> None:
        self.assertIn("未知的工具", self.registry.execute("notExists", {}))

    def test_protected_directory_is_rejected(self) -> None:
        output = self.execute("deleteDirectory", path=str(Path.cwd()))
        self.assertIn("拒绝操作包含当前工作目录的路径", output)

    def test_datetime_tools(self) -> None:
        self.assertTrue(self.execute("getDate"))
        self.assertIn("闰年", self.execute("isLeapYear", year=2024))
        self.assertIn("不是闰年", self.execute("isLeapYear", year=2023))
