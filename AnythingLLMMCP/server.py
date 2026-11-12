"""AnythingLLM MCP Server (Streamable HTTP)."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

DEFAULT_BASE_URL = "http://localhost:3001/api"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001


class ConfigError(ValueError):
    """Raised when the AnythingLLM connection settings are invalid."""


class AnythingLLMError(RuntimeError):
    """Raised when the AnythingLLM REST API cannot be reached or returns an error."""


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    timeout_seconds: float
    host: str
    port: int


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _load_dotenv() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings() -> Settings:
    _load_dotenv()
    base_url = (_env("ANYTHINGLLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ConfigError(f"ANYTHINGLLM_BASE_URL 必须是 http(s) URL，当前值：{base_url!r}")

    api_key = _env("ANYTHINGLLM_API_KEY")
    if api_key is None:
        raise ConfigError(
            "缺少环境变量 ANYTHINGLLM_API_KEY。\n"
            "请先在 AnythingLLM 侧边栏 Settings -> Tools -> Developer API 生成 API Key，然后设置：\n"
            '  PowerShell: $env:ANYTHINGLLM_API_KEY = "your-key"\n'
            "  cmd.exe:    set ANYTHINGLLM_API_KEY=your-key\n"
            "  bash:       export ANYTHINGLLM_API_KEY=your-key"
        )

    raw_timeout = _env("ANYTHINGLLM_TIMEOUT") or str(DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise ConfigError(f"ANYTHINGLLM_TIMEOUT 必须是数字，当前值：{raw_timeout!r}") from exc
    if timeout_seconds <= 0:
        raise ConfigError("ANYTHINGLLM_TIMEOUT 必须大于 0")

    raw_port = _env("MCP_PORT") or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ConfigError(f"MCP_PORT 必须是整数，当前值：{raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"MCP_PORT 必须在 1-65535 之间，当前值：{port}")

    return Settings(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        host=_env("MCP_HOST") or DEFAULT_HOST,
        port=port,
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


server = MCPServer(
    name="anythingllm",
    version="1.0.0",
    instructions="访问本机 AnythingLLM 的 MCP Server，可查询工作区、上传文档、更新向量化并对话。",
)


def _request(
    method: str,
    path: str,
    *,
    json_body: Any | None = None,
    data: bytes | None = None,
    content_type: str | None = None,
) -> dict:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Accept": "application/json",
    }
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type

    request = urllib.request.Request(
        f"{settings.base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AnythingLLMError(
            f"{method} {path} 返回 HTTP {exc.code}：{body[:800]}"
        ) from None
    except urllib.error.URLError as exc:
        raise AnythingLLMError(
            f"无法连接 AnythingLLM（{settings.base_url}）：{exc.reason}"
        ) from None

    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise AnythingLLMError(
            f"{method} {path} 返回的不是 JSON：{raw[:800]}"
        ) from None
    return payload if isinstance(payload, dict) else {"data": payload}


def _get(path: str) -> dict:
    return _request("GET", path)


def _post(path: str, body: dict) -> dict:
    return _request("POST", path, json_body=body)


def _first_workspace() -> dict:
    workspaces = _get("/v1/workspaces").get("workspaces", [])
    if not workspaces:
        raise AnythingLLMError("AnythingLLM 中没有任何工作区，请先在界面中创建一个工作区")
    return workspaces[0]


def _resolve_slug(slug: str | None) -> str:
    if slug and slug.strip():
        return slug.strip()
    return str(_first_workspace()["slug"])


def _form_field(boundary: str, name: str, value: str) -> bytes:
    return (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode("utf-8")


def _form_file(boundary: str, name: str, path: Path) -> bytes:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
        f'filename="{path.name}"\r\nContent-Type: {content_type}\r\n\r\n'
    ).encode("utf-8")
    return head + path.read_bytes() + b"\r\n"


def _upload(path: Path, workspace: str | None) -> dict:
    boundary = f"----AnythingLLMBoundary{uuid.uuid4().hex}"
    parts: list[bytes] = []
    if workspace:
        parts.append(_form_field(boundary, "addToWorkspaces", workspace))
    parts.append(_form_file(boundary, "file", path))
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return _request(
        "POST",
        "/v1/document/upload",
        data=b"".join(parts),
        content_type=f"multipart/form-data; boundary={boundary}",
    )


@server.tool()
def first_workspace_files() -> dict:
    """提取第一个工作区的文件（文档）信息。"""
    workspaces = _get("/v1/workspaces").get("workspaces", [])
    if not workspaces:
        return {"error": "没有任何工作区"}

    ws = workspaces[0]
    detail = _get(f"/v1/workspace/{ws['slug']}").get("workspace", [])
    detail = detail[0] if detail else {}

    files = []
    for doc in detail.get("documents", []):
        try:
            meta = json.loads(doc.get("metadata") or "{}")
        except json.JSONDecodeError:
            meta = {}
        files.append(
            {
                "docId": doc.get("docId"),
                "filename": meta.get("title") or doc.get("filename"),
                "storedFile": doc.get("filename"),
                "path": doc.get("docpath"),
                "source": meta.get("docSource"),
                "originalLocation": meta.get("url"),
                "wordCount": meta.get("wordCount"),
                "tokenCount": meta.get("token_count_estimate"),
                "published": meta.get("published"),
                "pinned": doc.get("pinned"),
                "createdAt": doc.get("createdAt"),
            }
        )

    return {
        "workspace": {"name": detail.get("name") or ws.get("name"), "slug": ws.get("slug")},
        "fileCount": len(files),
        "files": files,
    }


@server.tool()
def chat_workspace(message: str, slug: str = "", mode: str = "chat") -> dict:
    """向 AnythingLLM 工作区提问并返回回答。

    Args:
        message: 要发送给工作区的问题。
        slug: 工作区 slug；留空时使用第一个工作区。
        mode: "chat" 使用模型自身知识，"query" 只根据工作区文档回答。
    """
    if not message or not message.strip():
        return {"error": "message 不能为空"}
    if mode not in {"chat", "query"}:
        return {"error": "mode 只能是 chat 或 query"}

    workspace = _resolve_slug(slug)
    payload = _post(
        f"/v1/workspace/{workspace}/chat",
        {"message": message, "mode": mode},
    )
    if payload.get("error"):
        return {"workspace": workspace, "mode": mode, "error": payload["error"]}

    sources = []
    for source in payload.get("sources") or []:
        if isinstance(source, dict):
            sources.append(
                {
                    "title": source.get("title"),
                    "url": source.get("url"),
                    "docpath": source.get("docpath") or source.get("path"),
                    "score": source.get("score"),
                }
            )

    return {
        "workspace": workspace,
        "mode": mode,
        "answer": payload.get("textResponse", ""),
        "sources": sources,
        "chatId": payload.get("id"),
    }


@server.tool()
def upload_document(file_path: str, slug: str = "") -> dict:
    """把本地文件上传到 AnythingLLM 并加入工作区向量化。

    Args:
        file_path: 本地文件路径，支持相对路径和绝对路径。
        slug: 目标工作区 slug；留空时使用第一个工作区。
    """
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return {"error": f"文件不存在：{path}"}

    workspace = _resolve_slug(slug)
    result = _upload(path, workspace)
    if not result.get("success"):
        return {
            "workspace": workspace,
            "error": result.get("error") or "上传失败",
            "response": result,
        }

    documents = result.get("documents") or []
    return {
        "workspace": workspace,
        "file": str(path),
        "documents": documents,
        "locations": [doc.get("location") for doc in documents if doc.get("location")],
    }


@server.tool()
def update_workspace_embeddings(
    slug: str = "",
    adds: list[str] | None = None,
    deletes: list[str] | None = None,
) -> dict:
    """更新工作区向量化：加入或删除文档。

    Args:
        slug: 工作区 slug；留空时使用第一个工作区。
        adds: 要加入向量化的文档 location 列表（来自 upload_document 返回的 locations）。
        deletes: 要从向量化中移除的文档 location 列表。
    """
    if not adds and not deletes:
        return {"error": "adds 和 deletes 至少需要提供一个"}

    workspace = _resolve_slug(slug)
    payload = _post(
        f"/v1/workspace/{workspace}/update-embeddings",
        {"adds": adds or [], "deletes": deletes or []},
    )
    return {
        "workspace": workspace,
        "adds": adds or [],
        "deletes": deletes or [],
        "result": payload,
    }


def main() -> int:
    global _settings
    try:
        _settings = load_settings()
    except ConfigError as exc:
        print(f"[anythingllm-mcp] 配置错误：{exc}", file=sys.stderr)
        return 2

    server.run(
        "streamable-http",
        host=_settings.host,
        port=_settings.port,
        streamable_http_path="/mcp",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
