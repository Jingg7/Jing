from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.config import AgentConfig


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
