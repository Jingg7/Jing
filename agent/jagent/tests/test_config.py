from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.config import (
    AgentConfig,
    DEFAULT_CONTEXT_WINDOW,
    ensure_config_file,
)


class AgentConfigTests(unittest.TestCase):
    def test_loads_config_and_resolves_relative_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            config_path.write_text(
                "[llm]\n"
                "base_url = http://localhost:1234/v1\n"
                "model = test-model\n"
                "api_key = test-key\n"
                "[agent]\n"
                "history_file = data/history.json\n"
                "max_read_bytes = 2048\n"
                "system_prompt = 测试提示词\n"
                "[search]\n"
                "baidu_qianfan_api_key = test-search-key\n",
                encoding="utf-8",
            )

            config = AgentConfig.from_file(config_path)

            self.assertEqual(config.llm.base_url, "http://localhost:1234/v1")
            self.assertEqual(config.llm.model, "test-model")
            self.assertEqual(config.llm.api_key, "test-key")
            self.assertEqual(
                config.history_path,
                (Path(temp_dir) / "data" / "history.json").resolve(),
            )
            self.assertEqual(config.max_read_bytes, 2048)
            self.assertEqual(config.system_prompt, "测试提示词")
            self.assertEqual(
                config.search.baidu_qianfan_api_key, "test-search-key"
            )

    def test_optional_context_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            config_path.write_text(
                "[llm]\n"
                "base_url = http://localhost:1234/v1\n"
                "model = test-model\n"
                "[agent]\n"
                "context_window = 65536\n",
                encoding="utf-8",
            )

            config = AgentConfig.from_file(config_path)

            self.assertEqual(config.context_window, 65536)

    def test_invalid_context_window_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            config_path.write_text(
                "[llm]\n"
                "base_url = http://localhost:1234/v1\n"
                "model = test-model\n"
                "[agent]\n"
                "context_window = 0\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                AgentConfig.from_file(config_path)

    def test_search_config_defaults_to_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            config_path.write_text(
                "[llm]\n"
                "base_url = http://localhost:1234/v1\n"
                "model = test-model\n",
                encoding="utf-8",
            )

            config = AgentConfig.from_file(config_path)

            self.assertEqual(config.search.baidu_qianfan_api_key, "")

    def test_default_config_roundtrip_and_ensure_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.ini"
            resolved, created = ensure_config_file(path)

            self.assertTrue(created)
            self.assertTrue(resolved.is_file())
            config = AgentConfig.from_file(resolved)
            self.assertEqual(config.llm.base_url, "http://127.0.0.1:1234/v1")
            self.assertEqual(config.llm.model, "qwen3.5-4b")
            self.assertEqual(config.context.default_window, DEFAULT_CONTEXT_WINDOW)
            self.assertEqual(config.tools.cli_timeout, 30)
            self.assertEqual(config.tools.web_timeout, 20)
            self.assertEqual(config.mcp.call_timeout, 60)
            self.assertEqual(config.context.warning_ratio, 0.6)
            self.assertEqual(config.context.archive_directory, Path(".agents/context"))
            self.assertEqual(config.skills.max_frontmatter_lines, 512)
            self.assertEqual(config.session.directory, Path(".agents/sessions"))
            self.assertEqual(config.ui.sidebar_width, 22)

            path.write_text("keep me", encoding="utf-8")
            _, created = ensure_config_file(path)

            self.assertFalse(created)
            self.assertEqual(path.read_text(encoding="utf-8"), "keep me")

    def test_project_parameter_sections_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            config_path.write_text(
                "[llm]\n"
                "base_url = http://localhost:1234/v1\n"
                "model = test-model\n"
                "[context]\n"
                "default_window = 65536\n"
                "warning_ratio = 0.7\n"
                "archive_directory = .agents/raw\n"
                "compaction_target_tokens = 3000\n"
                "[tools]\n"
                "max_read_bytes = 4096\n"
                "cli_timeout = 12.5\n"
                "cli_max_output_chars = 123\n"
                "web_timeout = 8\n"
                "web_connect_timeout = 3\n"
                "web_error_max_chars = 77\n"
                "[search]\n"
                "endpoint = https://search.example/api\n"
                "max_results = 4\n"
                "[skills]\n"
                "directory = .agents/custom-skills\n"
                "max_frontmatter_lines = 7\n"
                "[session]\n"
                "directory = .agents/custom-sessions\n"
                "agents_file = CUSTOM_AGENTS.md\n"
                "[ui]\n"
                "sidebar_width = 30\n"
                "sidebar_min_width = 10\n"
                "sidebar_max_width = 50\n"
                "display_max_chars = 1234\n",
                encoding="utf-8",
            )

            config = AgentConfig.from_file(config_path)

            self.assertEqual(config.context.default_window, 65536)
            self.assertEqual(config.context.warning_ratio, 0.7)
            self.assertEqual(config.context.archive_directory, Path(".agents/raw"))
            self.assertEqual(config.context.compaction_target_tokens, 3000)
            self.assertEqual(config.max_read_bytes, 4096)
            self.assertEqual(config.tools.cli_timeout, 12.5)
            self.assertEqual(config.tools.cli_max_output_chars, 123)
            self.assertEqual(config.tools.web_timeout, 8)
            self.assertEqual(config.tools.web_connect_timeout, 3)
            self.assertEqual(config.tools.web_error_max_chars, 77)
            self.assertEqual(config.search.endpoint, "https://search.example/api")
            self.assertEqual(config.search.max_results, 4)
            self.assertEqual(config.skills.directory, Path(".agents/custom-skills"))
            self.assertEqual(config.skills.max_frontmatter_lines, 7)
            self.assertEqual(config.session.directory, Path(".agents/custom-sessions"))
            self.assertEqual(config.session.agents_file, Path("CUSTOM_AGENTS.md"))
            self.assertEqual(config.ui.sidebar_width, 30)
            self.assertEqual(config.ui.display_max_chars, 1234)

    def test_missing_config_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            AgentConfig.from_file("not-exists.ini")

    def test_invalid_max_read_bytes_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            config_path.write_text(
                "[llm]\n"
                "base_url = http://localhost:1234/v1\n"
                "model = test-model\n"
                "[agent]\n"
                "max_read_bytes = 0\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                AgentConfig.from_file(config_path)
