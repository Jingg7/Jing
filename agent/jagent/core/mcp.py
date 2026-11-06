from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import json
import re
import threading
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

try:
    from mcp import Client, StdioServerParameters
    from mcp.client.streamable_http import streamable_http_client
except ImportError:  # pragma: no cover - 缺少 SDK 时由 McpManager 给出明确提示
    Client = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    streamable_http_client = None  # type: ignore[assignment]

from .tools.base import BaseTool

MCP_CONFIG_FILENAME = ".mcp.json"
DEFAULT_CONNECT_TIMEOUT = 15.0
DEFAULT_CALL_TIMEOUT = 60.0
DEFAULT_CLOSE_TIMEOUT = 10.0
MAX_TOOL_NAME_LENGTH = 64
_INVALID_TOOL_NAME_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    cwd: str | None = None
    url: str = ""
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class McpToolDefinition:
    server_name: str
    remote_name: str
    description: str
    parameters: dict[str, Any]


def _normalize_transport(value: str) -> str:
    key = value.strip().lower().replace("-", "_")
    if key in {"streamable_http", "streamablehttp", "http"}:
        return "streamable_http"
    if key == "stdio":
        return "stdio"
    return ""


def _string_mapping(
    value: Any,
    field_name: str,
    server_name: str,
    errors: list[str],
) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        errors.append(f"MCP Server {server_name} 的 {field_name} 必须是对象")
        return None
    return {str(key): str(item) for key, item in value.items()}


def load_mcp_config(
    path: str | Path,
) -> tuple[list[McpServerConfig], list[str]]:
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        return [], []

    try:
        raw = config_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return [], [f"读取 MCP 配置失败: {config_path}: {exc}"]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], [f"MCP 配置解析失败: {config_path}: {exc}"]

    if not isinstance(data, dict):
        return [], [f"MCP 配置根节点必须是对象: {config_path}"]
    servers = data.get("mcpServers")
    if servers is None:
        return [], []
    if not isinstance(servers, dict):
        return [], [f"MCP 配置中的 mcpServers 必须是对象: {config_path}"]

    configs: list[McpServerConfig] = []
    errors: list[str] = []
    for server_name, entry in servers.items():
        name = str(server_name)
        if not isinstance(entry, dict):
            errors.append(f"MCP Server {name} 的配置必须是对象")
            continue

        raw_transport = entry.get("type", entry.get("transport"))
        if isinstance(raw_transport, str):
            transport = _normalize_transport(raw_transport)
        elif "command" in entry:
            transport = "stdio"
        elif "url" in entry:
            transport = "streamable_http"
        else:
            transport = ""
        if not transport:
            errors.append(
                f"MCP Server {name} 缺少有效的 type，"
                "支持 stdio 和 streamable_http"
            )
            continue

        if transport == "stdio":
            command = entry.get("command")
            if not isinstance(command, str) or not command.strip():
                errors.append(f"MCP Server {name} 缺少 command")
                continue
            raw_args = entry.get("args", [])
            if not isinstance(raw_args, list) or not all(
                isinstance(item, str) for item in raw_args
            ):
                errors.append(f"MCP Server {name} 的 args 必须是字符串数组")
                continue
            env = _string_mapping(entry.get("env"), "env", name, errors)
            cwd_value = entry.get("cwd")
            cwd: str | None = None
            if cwd_value is not None:
                if not isinstance(cwd_value, str):
                    errors.append(f"MCP Server {name} 的 cwd 必须是字符串")
                    continue
                cwd_path = Path(cwd_value).expanduser()
                if not cwd_path.is_absolute():
                    cwd_path = config_path.parent / cwd_path
                cwd = str(cwd_path.resolve())
            configs.append(
                McpServerConfig(
                    name=name,
                    transport="stdio",
                    command=command.strip(),
                    args=tuple(raw_args),
                    env=env,
                    cwd=cwd,
                )
            )
            continue

        url = entry.get("url")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"MCP Server {name} 缺少有效的 url")
            continue
        headers = _string_mapping(
            entry.get("headers"), "headers", name, errors
        )
        configs.append(
            McpServerConfig(
                name=name,
                transport="streamable_http",
                url=url.strip(),
                headers=headers,
            )
        )
    return configs, errors


def _sanitize_tool_name(value: str) -> str:
    cleaned = _INVALID_TOOL_NAME_CHARS.sub("_", value).strip("_")
    if not cleaned:
        cleaned = "tool"
    return cleaned[:MAX_TOOL_NAME_LENGTH]


def _format_content_block(block: Any) -> str:
    block_type = getattr(block, "type", "")
    if block_type == "text":
        return str(getattr(block, "text", ""))
    if block_type == "image":
        data = str(getattr(block, "data", ""))
        mime_type = getattr(block, "mime_type", "unknown")
        return f"[图片内容] mime_type={mime_type}, base64 长度={len(data)}"
    if block_type == "audio":
        data = str(getattr(block, "data", ""))
        mime_type = getattr(block, "mime_type", "unknown")
        return f"[音频内容] mime_type={mime_type}, base64 长度={len(data)}"
    if block_type == "resource":
        resource = getattr(block, "resource", None)
        uri = getattr(resource, "uri", "")
        text = getattr(resource, "text", None)
        if isinstance(text, str):
            return f"[资源] {uri}\n{text}"
        mime_type = getattr(resource, "mime_type", "unknown")
        return f"[资源] {uri}（{mime_type}）"
    if block_type == "resource_link":
        name = getattr(block, "name", "")
        uri = getattr(block, "uri", "")
        return f"[资源链接] {name}: {uri}"
    dump = getattr(block, "model_dump_json", None)
    if callable(dump):
        try:
            return dump()
        except Exception:
            pass
    return str(block)


def format_mcp_result(result: Any) -> str:
    parts: list[str] = []
    content = getattr(result, "content", None) or []
    for block in content:
        text = _format_content_block(block)
        if text:
            parts.append(text)

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        try:
            structured_text = json.dumps(
                structured, ensure_ascii=False, indent=2
            )
        except (TypeError, ValueError):
            structured_text = str(structured)
        parts.append(f"结构化数据:\n{structured_text}")

    body = "\n".join(parts) or "(MCP 工具未返回内容)"
    if bool(getattr(result, "is_error", False)):
        return f"MCP 工具返回错误:\n{body}"
    return body


class McpTool(BaseTool):
    def __init__(
        self,
        manager: "McpManager",
        server_name: str,
        remote_name: str,
        exposed_name: str,
        description: str,
        parameters: dict[str, Any],
    ):
        self._manager = manager
        self.server_name = server_name
        self.remote_name = remote_name
        self.name = exposed_name
        text = description.strip() or remote_name
        self.description = f"[MCP:{server_name}] {text}"
        self.parameters = parameters

    def run(self, arguments: dict[str, Any]) -> str:
        return self._manager.call_tool(
            self.server_name, self.remote_name, arguments
        )


@asynccontextmanager
async def _http_transport(
    url: str,
    headers: dict[str, str],
) -> AsyncIterator[Any]:
    import httpx2

    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(  # type: ignore[misc]
            url, http_client=http_client
        ) as streams:
            yield streams


class McpManager:
    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        project_root: str | Path | None = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        call_timeout: float = DEFAULT_CALL_TIMEOUT,
        close_timeout: float = DEFAULT_CLOSE_TIMEOUT,
    ):
        root = Path(
            project_root if project_root is not None else Path.cwd()
        ).expanduser().resolve()
        self._project_root = root
        self.config_path = Path(
            config_path
            if config_path is not None
            else root / MCP_CONFIG_FILENAME
        ).expanduser().resolve()
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._close_timeout = close_timeout

        self._servers: list[McpServerConfig] = []
        self._startup_errors: list[str] = []
        self._discovered: list[McpToolDefinition] = []
        self._clients: dict[str, Any] = {}
        self._tools: list[McpTool] = []
        self._tool_mapping: dict[str, tuple[str, str]] = {}

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stack: AsyncExitStack | None = None
        self._ready = threading.Event()
        self._lock = threading.RLock()
        self._started = False
        self._starting = False
        self._prepared = False
        self._closed = False
        atexit.register(self.close)

    @property
    def startup_errors(self) -> tuple[str, ...]:
        return tuple(self._startup_errors)

    @property
    def servers(self) -> tuple[McpServerConfig, ...]:
        return tuple(self._servers)

    @property
    def connected_server_names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._clients)

    @property
    def is_starting(self) -> bool:
        return self._starting

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def server_tools(self) -> dict[str, tuple[str, ...]]:
        tools: dict[str, list[str]] = {}
        with self._lock:
            connected = set(self._clients)
        for definition in self._discovered:
            if definition.server_name in connected:
                tools.setdefault(definition.server_name, []).append(
                    definition.remote_name
                )
        return {
            name: tuple(sorted(values, key=str.casefold))
            for name, values in tools.items()
        }

    @property
    def tool_mapping(self) -> dict[str, tuple[str, str]]:
        return dict(self._tool_mapping)

    def prepare(self) -> None:
        with self._lock:
            if self._prepared or self._closed:
                return
            self._servers, config_errors = load_mcp_config(self.config_path)
            self._startup_errors.extend(config_errors)
            if not self._servers:
                self._prepared = True
                return
            if Client is None:
                self._startup_errors.append(
                    "未安装 MCP Python SDK，无法连接 MCP Server。"
                    "请先安装 mcp 依赖。"
                )
                self._prepared = True
                return
            self._prepared = True

    def start(self) -> None:
        with self._lock:
            if self._started or self._closed:
                return
            self._starting = True
            self._started = True

        self.prepare()
        if not self._servers or Client is None:
            with self._lock:
                self._starting = False
            return

        with self._lock:
            self._thread = threading.Thread(
                target=self._run_event_loop,
                name="jagent-mcp",
                daemon=True,
            )
            self._thread.start()
        if not self._ready.wait(5):
            with self._lock:
                self._startup_errors.append("MCP 客户端事件循环启动超时")
                self._starting = False
            return

        try:
            self._run(
                self._connect_all(),
                timeout=self._connect_timeout * 2 + 5,
            )
        except Exception as exc:
            with self._lock:
                self._startup_errors.append(f"MCP 初始化失败: {exc}")
        finally:
            with self._lock:
                self._starting = False

    def build_tools(
        self, reserved_names: Iterable[str] = ()
    ) -> list[McpTool]:
        used = {name.casefold() for name in reserved_names}
        tools: list[McpTool] = []
        mapping: dict[str, tuple[str, str]] = {}
        for definition in self._discovered:
            exposed_name = self._unique_tool_name(definition, used)
            used.add(exposed_name.casefold())
            tools.append(
                McpTool(
                    self,
                    definition.server_name,
                    definition.remote_name,
                    exposed_name,
                    definition.description,
                    definition.parameters,
                )
            )
            mapping[exposed_name] = (
                definition.server_name,
                definition.remote_name,
            )
        self._tools = tools
        self._tool_mapping = mapping
        return list(tools)

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        if server_name not in self._clients:
            return f"MCP Server 未连接: {server_name}"
        if not isinstance(arguments, dict):
            return "MCP 工具参数必须是对象"
        try:
            return self._run(
                self._call_tool(server_name, tool_name, arguments),
                timeout=self._call_timeout,
            )
        except TimeoutError:
            return (
                f"MCP 工具调用超时: {server_name}/{tool_name}"
                f"（{self._call_timeout:g} 秒）"
            )
        except Exception as exc:
            return (
                f"调用 MCP 工具失败: {server_name}/{tool_name}: {exc}"
            )

    def close(self, timeout: float | None = None) -> None:
        effective_timeout = timeout if timeout is not None else self._close_timeout
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._starting = False
            loop = self._loop
            thread = self._thread

        if loop is not None and loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._shutdown(), loop
                )
                future.result(timeout=effective_timeout)
            except Exception:
                pass
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(effective_timeout)

    def _run_event_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    def _run(self, coroutine: Any, *, timeout: float) -> Any:
        loop = self._loop
        if loop is None or not loop.is_running():
            raise RuntimeError("MCP 客户端事件循环未运行")
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError from exc

    async def _connect_all(self) -> None:
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        results = await asyncio.gather(
            *(self._connect_one(server) for server in self._servers)
        )
        for config, client, tools, error in results:
            if error is not None:
                self._startup_errors.append(error)
                continue
            self._clients[config.name] = client
            for tool in tools:
                self._discovered.append(
                    McpToolDefinition(
                        server_name=config.name,
                        remote_name=tool.name,
                        description=tool.description or "",
                        parameters=(
                            tool.input_schema
                            if isinstance(tool.input_schema, dict)
                            else {"type": "object", "properties": {}}
                        ),
                    )
                )

    async def _connect_one(
        self, config: McpServerConfig
    ) -> tuple[McpServerConfig, Any, list[Any], str | None]:
        try:
            assert self._stack is not None
            client = await asyncio.wait_for(
                self._stack.enter_async_context(
                    self._make_client(config)
                ),
                timeout=self._connect_timeout,
            )
            tools = await asyncio.wait_for(
                self._list_all_tools(client),
                timeout=self._connect_timeout,
            )
            return config, client, tools, None
        except Exception as exc:
            return (
                config,
                None,
                [],
                f"MCP Server {config.name} 连接失败: {exc}",
            )

    def _make_client(self, config: McpServerConfig) -> Any:
        if Client is None:  # pragma: no cover - start() 已提前处理
            raise RuntimeError("未安装 MCP Python SDK")
        if config.transport == "stdio":
            if StdioServerParameters is None:  # pragma: no cover
                raise RuntimeError("MCP SDK 缺少 stdio 支持")
            parameters = StdioServerParameters(
                command=config.command,
                args=list(config.args),
                env=config.env,
                cwd=config.cwd,
            )
            return Client(
                parameters,
                read_timeout_seconds=self._connect_timeout,
            )
        if config.headers:
            return Client(
                _http_transport(config.url, config.headers),
                read_timeout_seconds=self._call_timeout,
            )
        return Client(
            config.url,
            read_timeout_seconds=self._call_timeout,
        )

    async def _list_all_tools(self, client: Any) -> list[Any]:
        tools: list[Any] = []
        cursor: str | None = None
        while True:
            result = await client.list_tools(cursor=cursor)
            tools.extend(result.tools)
            cursor = getattr(result, "next_cursor", None)
            if not cursor:
                break
        return tools

    async def _call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        client = self._clients.get(server_name)
        if client is None:
            return f"MCP Server 未连接: {server_name}"
        try:
            result = await client.call_tool(tool_name, arguments)
        except Exception as exc:
            return (
                f"调用 MCP 工具失败: {server_name}/{tool_name}: {exc}"
            )
        return format_mcp_result(result)

    async def _shutdown(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._clients.clear()

    def _unique_tool_name(
        self,
        definition: McpToolDefinition,
        used: set[str],
    ) -> str:
        candidate = _sanitize_tool_name(definition.remote_name)
        if candidate.casefold() in used:
            candidate = _sanitize_tool_name(
                f"{definition.server_name}__{definition.remote_name}"
            )
        if candidate.casefold() not in used:
            return candidate

        stem = candidate
        suffix = 2
        while True:
            suffix_text = f"_{suffix}"
            candidate = f"{stem[: MAX_TOOL_NAME_LENGTH - len(suffix_text)]}{suffix_text}"
            if candidate.casefold() not in used:
                return candidate
            suffix += 1
