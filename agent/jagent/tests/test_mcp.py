from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from core.bootstrap import create_session
from core.config import AgentConfig, LLMConfig
from core.history import HistoryStore
from core.mcp import (
    McpManager,
    McpToolDefinition,
    format_mcp_result,
    load_mcp_config,
)
from core.tools import FileToolConfig, build_default_registry
from core.session import AgentSession


class McpConfigTests(unittest.TestCase):
    def test_missing_config_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            configs, errors = load_mcp_config(Path(temp_dir) / ".mcp.json")

        self.assertEqual(configs, [])
        self.assertEqual(errors, [])

    def test_loads_stdio_and_streamable_http_servers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / ".mcp.json"
            config_path.write_text(
                """
                {
                  "mcpServers": {
                    "local": {
                      "type": "stdio",
                      "command": "python",
                      "args": ["server.py"],
                      "env": {"TOKEN": "abc"},
                      "cwd": "servers"
                    },
                    "remote": {
                      "type": "streamable_http",
                      "url": "https://example.com/mcp",
                      "headers": {"Authorization": "Bearer token"}
                    }
                  }
                }
                """,
                encoding="utf-8",
            )

            configs, errors = load_mcp_config(config_path)

            self.assertEqual(errors, [])
            self.assertEqual([config.name for config in configs], ["local", "remote"])
            local, remote = configs
            self.assertEqual(local.transport, "stdio")
            self.assertEqual(local.command, "python")
            self.assertEqual(local.args, ("server.py",))
            self.assertEqual(local.env, {"TOKEN": "abc"})
            self.assertEqual(local.cwd, str((root / "servers").resolve()))
            self.assertEqual(remote.transport, "streamable_http")
            self.assertEqual(remote.url, "https://example.com/mcp")
            self.assertEqual(remote.headers, {"Authorization": "Bearer token"})

    def test_invalid_json_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".mcp.json"
            config_path.write_text("{not json", encoding="utf-8")

            configs, errors = load_mcp_config(config_path)

        self.assertEqual(configs, [])
        self.assertTrue(any("解析失败" in error for error in errors))

    def test_invalid_server_entries_return_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".mcp.json"
            config_path.write_text(
                """
                {
                  "mcpServers": {
                    "no-command": {"type": "stdio"},
                    "no-url": {"type": "streamable_http"}
                  }
                }
                """,
                encoding="utf-8",
            )

            configs, errors = load_mcp_config(config_path)

        self.assertEqual(configs, [])
        self.assertEqual(len(errors), 2)


class McpToolMappingTests(unittest.TestCase):
    def test_prefixes_names_only_when_there_are_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = McpManager(
                Path(temp_dir) / ".mcp.json", project_root=temp_dir
            )
            manager._discovered = [
                McpToolDefinition("ServerA", "search", "A search", {}),
                McpToolDefinition("ServerB", "search", "B search", {}),
                McpToolDefinition("ServerA", "unique", "Unique", {}),
            ]

            tools = manager.build_tools(["search"])

        names = [tool.name for tool in tools]
        self.assertEqual(names, ["ServerA__search", "ServerB__search", "unique"])
        self.assertEqual(
            manager.tool_mapping["ServerB__search"], ("ServerB", "search")
        )

    def test_sanitizes_invalid_tool_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = McpManager(
                Path(temp_dir) / ".mcp.json", project_root=temp_dir
            )
            manager._discovered = [
                McpToolDefinition("ServerA", "tools/search.v1", "Search", {}),
            ]

            tools = manager.build_tools()

        self.assertEqual(tools[0].name, "tools_search_v1")

    def test_tool_call_is_forwarded_to_mapped_server_and_name(self) -> None:
        class FakeManager:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, dict[str, Any]]] = []

            def call_tool(
                self, server: str, name: str, arguments: dict[str, Any]
            ) -> str:
                self.calls.append((server, name, arguments))
                return "result"

        from core.mcp import McpTool

        fake = FakeManager()
        tool = McpTool(fake, "ServerA", "remote-tool", "exposed", "", {})
        output = tool.run({"value": 1})

        self.assertEqual(output, "result")
        self.assertEqual(fake.calls, [("ServerA", "remote-tool", {"value": 1})])
        self.assertEqual(tool.name, "exposed")


class McpResultTests(unittest.TestCase):
    def test_formats_text_and_structured_content(self) -> None:
        result = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello")],
            structured_content={"answer": 42},
            is_error=False,
        )

        output = format_mcp_result(result)

        self.assertIn("hello", output)
        self.assertIn("结构化数据", output)
        self.assertIn('"answer": 42', output)

    def test_formats_tool_error(self) -> None:
        result = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="bad input")],
            structured_content=None,
            is_error=True,
        )

        output = format_mcp_result(result)

        self.assertIn("MCP 工具返回错误", output)
        self.assertIn("bad input", output)


class McpIntegrationTests(unittest.TestCase):
    def test_default_registry_includes_discovered_mcp_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = McpManager(
                Path(temp_dir) / ".mcp.json", project_root=temp_dir
            )
            manager._discovered = [
                McpToolDefinition("ServerA", "lookup", "Lookup", {}),
            ]

            registry = build_default_registry(
                FileToolConfig(), mcp_manager=manager
            )

        self.assertIn("lookup", registry.names())
        self.assertIn("lookup", [tool["function"]["name"] for tool in registry.schemas()])

    def test_refresh_mcp_tools_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = McpManager(
                Path(temp_dir) / ".mcp.json", project_root=temp_dir
            )
            manager._discovered = []
            registry = build_default_registry(mcp_manager=manager)
            manager._discovered = [
                McpToolDefinition("ServerA", "lookup", "Lookup", {}),
            ]
            session = AgentSession(
                model=object(),
                registry=registry,
                mcp_manager=manager,
            )

            first_count = session.refresh_mcp_tools()
            first_names = registry.names()
            second_count = session.refresh_mcp_tools()
            second_names = registry.names()

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
        self.assertEqual(first_names, second_names)
        self.assertEqual(session.mcp_tool_names, ("lookup",))

    def test_invalid_mcp_config_does_not_break_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".mcp.json").write_text("{bad json", encoding="utf-8")
            config = AgentConfig(
                llm=LLMConfig("http://localhost:1234/v1", "test", "key"),
                history_path=root / "history.json",
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                session = create_session(
                    config,
                    model=object(),
                    history=HistoryStore(root / "history.json"),
                    project_root=root,
                )

        names = [tool["function"]["name"] for tool in session.tools]
        self.assertIn("readFile", names)
        self.assertIn("[MCP]", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
