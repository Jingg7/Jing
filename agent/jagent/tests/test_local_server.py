from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.config import LLMConfig
from core.local_server import ensure_local_server


class EnsureLocalServerTests(unittest.TestCase):
    def _run(self, config: LLMConfig, **overrides):
        defaults = {
            "timeout": 0.01,
            "load_timeout": 0.01,
            "probe": lambda host, port, timeout=0.5: False,
            "which": lambda name: None,
            "run": lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            "popen": lambda *args, **kwargs: SimpleNamespace(),
            "sleep": lambda seconds: None,
            "log": lambda message: None,
        }
        defaults.update(overrides)
        return ensure_local_server(config, **defaults)

    def test_remote_url_is_ignored(self) -> None:
        calls: list[str] = []

        result = self._run(
            LLMConfig("https://api.openai.com/v1", "gpt-4o-mini", "key"),
            probe=lambda *args: self.fail("probe should not be called"),
            which=lambda name: calls.append(name),
        )

        self.assertFalse(result)
        self.assertEqual(calls, [])

    def test_existing_local_server_is_kept(self) -> None:
        result = self._run(
            LLMConfig("http://127.0.0.1:1234/v1", "qwen3.5-4b", "DUMMY"),
            probe=lambda *args: True,
        )

        self.assertTrue(result)

    def test_loads_model_when_lmstudio_already_running(self) -> None:
        commands: list[list[str]] = []

        def run(command, **kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        result = self._run(
            LLMConfig("http://127.0.0.1:1234/v1", "qwen3.5-4b", "DUMMY"),
            probe=lambda *args: True,
            which=lambda name: "C:/lms.exe" if name == "lms" else None,
            run=run,
        )

        self.assertTrue(result)
        self.assertEqual(
            commands,
            [
                [
                    "C:/lms.exe",
                    "load",
                    "qwen3.5-4b",
                    "--identifier",
                    "qwen3.5-4b",
                    "-y",
                ]
            ],
        )

    def test_already_loaded_model_is_not_an_error(self) -> None:
        logs: list[str] = []

        result = self._run(
            LLMConfig("http://127.0.0.1:1234/v1", "qwen3.5-4b", "DUMMY"),
            probe=lambda *args: True,
            which=lambda name: "C:/lms.exe" if name == "lms" else None,
            run=lambda *args, **kwargs: SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="Error: A model with identifier qwen3.5-4b already exists.",
            ),
            log=logs.append,
        )

        self.assertTrue(result)
        self.assertEqual(logs, [])

    def test_starts_lmstudio_and_loads_model(self) -> None:
        commands: list[list[str]] = []
        probe_results = iter([False, True])

        def probe(*args):
            return next(probe_results, True)

        def run(command, **kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        result = self._run(
            LLMConfig("http://127.0.0.1:1234/v1", "qwen3.5-4b", "DUMMY"),
            which=lambda name: "C:/lms.exe" if name == "lms" else None,
            probe=probe,
            run=run,
        )

        self.assertTrue(result)
        self.assertEqual(commands[0], ["C:/lms.exe", "server", "start"])
        self.assertEqual(
            commands[1],
            [
                "C:/lms.exe",
                "load",
                "qwen3.5-4b",
                "--identifier",
                "qwen3.5-4b",
                "-y",
            ],
        )

    def test_starts_ollama_for_colon_model(self) -> None:
        popens: list[list[str]] = []
        probe_results = iter([False, True])

        result = self._run(
            LLMConfig("http://127.0.0.1:11434/v1", "qwen2.5:7b", "ollama"),
            which=lambda name: "C:/ollama.exe" if name == "ollama" else "C:/lms.exe",
            probe=lambda *args: next(probe_results, True),
            popen=lambda command, **kwargs: popens.append(command),
        )

        self.assertTrue(result)
        self.assertEqual(popens, [["C:/ollama.exe", "serve"]])

    def test_falls_back_when_lmstudio_does_not_come_up(self) -> None:
        popens: list[list[str]] = []
        probe_results = iter([False, False, False, True])

        result = self._run(
            LLMConfig("http://127.0.0.1:1234/v1", "qwen3.5-4b", "DUMMY"),
            which=lambda name: f"C:/{name}.exe",
            probe=lambda *args: next(probe_results, True),
            popen=lambda command, **kwargs: popens.append(command),
        )

        self.assertTrue(result)
        self.assertEqual(popens, [["C:/ollama.exe", "serve"]])

    def test_returns_false_without_local_runtime(self) -> None:
        result = self._run(
            LLMConfig("http://127.0.0.1:1234/v1", "qwen3.5-4b", "DUMMY"),
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
