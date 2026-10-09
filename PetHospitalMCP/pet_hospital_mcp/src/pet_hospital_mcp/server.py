"""MCPServer assembly: tools, health endpoint and the Streamable HTTP app."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import PROTOCOL_VERSION, SDK_NAME, SDK_VERSION, __version__
from .config import Settings, load_settings
from .logging_config import get_logger
from .tools import list_pets as list_pets_tool

MCP_PATH = "/mcp"
HEALTH_PATH = "/health"


def _health_payload(settings: Settings) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "pet-hospital-mcp",
        "version": __version__,
        "protocolVersion": PROTOCOL_VERSION,
        "sdk": {"name": SDK_NAME, "version": SDK_VERSION},
        "transport": "streamable-http",
        "stateless": True,
        "endpoint": MCP_PATH,
        "backend": settings.base_url,
    }


async def _health(request: Request) -> JSONResponse:
    settings = load_settings()
    return JSONResponse(_health_payload(settings))


def build_server(settings: Settings | None = None) -> MCPServer:
    """Create the stateless `MCPServer` with every tool registered."""
    settings = settings or load_settings()

    server = MCPServer(
        name="pet-hospital-mcp",
        version=__version__,
        description="将 Go 宠物医院 REST API 暴露给 AI Agent 的无状态 MCP 服务",
        instructions=(
            "本服务通过 list_pets 工具查询宠物医院的宠物档案，"
            "上游为 Go REST API（GET /api/v1/pets）。"
            "所有失败均返回 {\"error\": {code, message, details}} 结构。"
        ),
        log_level="WARNING",
        warn_on_duplicate_tools=True,
    )

    list_pets_tool.register(server)

    async def health(request: Request) -> JSONResponse:
        return await _health(request)

    server.custom_route(HEALTH_PATH, methods=["GET"])(health)
    return server


def create_app(server: MCPServer, settings: Settings | None = None) -> Any:
    """Build the Starlette app used by uvicorn (stateless Streamable HTTP)."""
    settings = settings or load_settings()
    return server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=settings.json_response,
        stateless_http=True,
    )


def describe(settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    return json.dumps(
        {
            "mcp_endpoint": settings.mcp_endpoint,
            "health_endpoint": settings.health_endpoint,
            "backend": settings.base_url,
            "protocolVersion": PROTOCOL_VERSION,
            "sdk": f"{SDK_NAME}=={SDK_VERSION}",
        },
        ensure_ascii=False,
    )


__all__ = ["MCP_PATH", "HEALTH_PATH", "build_server", "create_app", "describe", "Route"]
