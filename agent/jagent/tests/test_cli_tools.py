from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import patch

from core.tools.cli_tools import RunCliTool


class RunCliToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = RunCliTool(timeout=5, max_output_chars=20)

    def test_schema(self) -> None:
        schema = self.tool.schema()["function"]
        self.assertEqual(schema["name"], "RunCli")
        self.assertEqual(schema["parameters"]["required"], ["command"])
        self.assertEqual(
            schema["parameters"]["properties"]["args"]["type"], "array"
        )

    @patch("core.tools.cli_tools.subprocess.run")
    def test_runs_with_argument_list_and_returns_result(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"hello\n", stderr=b""
        )

        output = self.tool.run({"command": "echo", "args": ["hello"]})

        args, kwargs = run.call_args
        self.assertEqual(args[0], ["echo", "hello"])
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["timeout"], 5)
        self.assertIn("退出码: 0", output)
        self.assertIn("hello", output)
        self.assertIn("标准错误:", output)
        self.assertIn("(空)", output)

    @patch("core.tools.cli_tools.subprocess.run")
    def test_nonzero_exit_and_stderr_are_returned(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=2, stdout=b"partial", stderr=b"something failed"
        )

        output = self.tool.run({"command": "bad", "args": []})

        self.assertIn("退出码: 2", output)
        self.assertIn("partial", output)
        self.assertIn("something failed", output)

    @patch("core.tools.cli_tools.subprocess.run")
    def test_long_output_is_truncated_and_marked(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"a" * 50, stderr=b""
        )

        output = self.tool.run({"command": "many", "args": []})

        self.assertIn("a" * 20, output)
        self.assertIn("输出已截断", output)
        self.assertIn("另有 30 个字符被省略", output)
        self.assertNotIn("a" * 21, output)

    @patch("core.tools.cli_tools.subprocess.run")
    def test_timeout_is_reported_with_partial_output(self, run) -> None:
        run.side_effect = subprocess.TimeoutExpired(
            cmd="slow", timeout=5, output=b"started", stderr=b"warning"
        )

        output = self.tool.run({"command": "slow", "args": []})

        self.assertIn("命令执行超时", output)
        self.assertIn("5 秒", output)
        self.assertIn("started", output)
        self.assertIn("warning", output)

    @patch("core.tools.cli_tools.subprocess.run")
    def test_missing_command_is_reported(self, run) -> None:
        run.side_effect = FileNotFoundError()

        output = self.tool.run({"command": "not-exists", "args": []})

        self.assertIn("未找到可执行程序", output)
        self.assertIn("not-exists", output)

    @patch("core.tools.cli_tools.subprocess.run")
    def test_empty_command_is_rejected(self, run) -> None:
        output = self.tool.run({"command": "   "})

        self.assertIn("command 不能为空", output)
        run.assert_not_called()

    @patch("core.tools.cli_tools.subprocess.run")
    def test_non_list_args_is_rejected(self, run) -> None:
        output = self.tool.run({"command": "echo", "args": "hello"})

        self.assertIn("args 必须是字符串数组", output)
        run.assert_not_called()

    def test_executes_real_process(self) -> None:
        tool = RunCliTool(timeout=30)

        output = tool.run(
            {
                "command": sys.executable,
                "args": [
                    "-c",
                    "import sys; print('ok'); "
                    "print('err', file=sys.stderr); sys.exit(3)",
                ],
            }
        )

        self.assertIn("退出码: 3", output)
        self.assertIn("ok", output)
        self.assertIn("err", output)


if __name__ == "__main__":
    unittest.main()
