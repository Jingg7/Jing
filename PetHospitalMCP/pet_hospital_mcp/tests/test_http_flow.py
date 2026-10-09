"""Stateless Streamable HTTP flow: /health, discovery, call - no handshake."""

from __future__ import annotations

import json
import os
import threading

import httpx
import pytest
from mcp.client import Client

from pet_hospital_mcp import PROTOCOL_VERSION, SDK_NAME, SDK_VERSION
from pet_hospital_mcp.rest_client import reset_client
from pet_hospital_mcp.server import build_server, create_app

from .conftest import (
    SAMPLE_DATA,
    build_backend_app,
    envelope,
    free_port,
    start_uvicorn,
)

ENVELOPE_META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
}


@pytest.fixture(scope="module")
def http_stack():
    backend_port = free_port()
    mcp_port = free_port()
    saved = {key: os.environ.get(key) for key in os.environ}

    os.environ["PET_HOSPITAL_BASE_URL"] = f"http://127.0.0.1:{backend_port}"
    os.environ["MCP_PORT"] = str(mcp_port)
    os.environ["MCP_HOST"] = "127.0.0.1"
    reset_client()

    backend_server, backend_thread = start_uvicorn(build_backend_app(), backend_port)

    from pet_hospital_mcp.config import load_settings

    settings = load_settings()
    server = build_server(settings)
    app = create_app(server, settings)
    mcp_server, mcp_thread = start_uvicorn(app, mcp_port)

    base_url = f"http://127.0.0.1:{mcp_port}"

    yield {
        "base_url": base_url,
        "endpoint": f"{base_url}/mcp",
        "health": f"{base_url}/health",
        "settings": settings,
        "server": server,
    }

    mcp_server.should_exit = True
    backend_server.should_exit = True
    mcp_thread.join(timeout=10)
    backend_thread.join(timeout=10)
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    reset_client()


def rpc_request(method: str, params: dict, mid: int = 1) -> tuple[dict, dict]:
    body = {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
    }
    if isinstance(params, dict) and isinstance(params.get("name"), str):
        headers["mcp-name"] = params["name"]
    return body, headers


async def post_rpc(client: httpx.AsyncClient, endpoint: str, method: str,
                   params: dict, mid: int = 1) -> httpx.Response:
    body, headers = rpc_request(method, params, mid)
    return await client.post(
        endpoint,
        content=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
    )


def parse_result(response: httpx.Response) -> dict:
    assert response.status_code == 200, response.text
    payload = json.loads(response.text)
    assert "error" not in payload, payload
    return payload["result"]


@pytest.fixture
async def no_handshake_client(http_stack):
    """Raw HTTP client used to prove no `initialize` / session id is involved."""
    async with httpx.AsyncClient(timeout=15) as client:
        yield client


async def test_health_endpoint(http_stack):
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(http_stack["health"])

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["protocolVersion"] == PROTOCOL_VERSION
    assert payload["sdk"] == {"name": SDK_NAME, "version": SDK_VERSION}
    assert payload["stateless"] is True
    assert payload["endpoint"] == "/mcp"


async def test_server_discover_without_initialize(no_handshake_client, http_stack):
    response = await post_rpc(
        no_handshake_client, http_stack["endpoint"], "server/discover",
        {"_meta": ENVELOPE_META},
    )

    result = parse_result(response)
    assert PROTOCOL_VERSION in result["supportedVersions"]
    assert result["resultType"] == "complete"
    assert "tools" in result["capabilities"]
    assert "mcp-session-id" not in {k.lower() for k in response.headers}


async def test_tools_list_without_initialize_or_session(no_handshake_client, http_stack):
    response = await post_rpc(
        no_handshake_client, http_stack["endpoint"], "tools/list",
        {"_meta": ENVELOPE_META},
    )

    result = parse_result(response)
    assert [tool["name"] for tool in result["tools"]] == ["list_pets"]
    assert set(result["tools"][0]["inputSchema"]["properties"]) >= {"page", "pageSize", "species"}
    assert "mcp-session-id" not in {k.lower() for k in response.headers}
    assert "initialize" not in response.text


async def test_tools_call_over_http_success(no_handshake_client, http_stack):
    response = await post_rpc(
        no_handshake_client, http_stack["endpoint"], "tools/call",
        {"name": "list_pets", "arguments": {"page": 1, "pageSize": 5}, "_meta": ENVELOPE_META},
    )

    result = parse_result(response)
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["total"] == len(SAMPLE_DATA["items"])
    assert set(payload) == {"items", "total", "page", "pageSize", "totalPages", "totalCost"}
    assert result["structuredContent"]["total"] == payload["total"]
    assert "mcp-session-id" not in {k.lower() for k in response.headers}


async def test_tools_call_over_http_invalid_input(no_handshake_client, http_stack):
    response = await post_rpc(
        no_handshake_client, http_stack["endpoint"], "tools/call",
        {
            "name": "list_pets",
            "arguments": {"page": 0, "species": "龙", "oops": True},
            "_meta": ENVELOPE_META,
        },
        mid=7,
    )

    result = parse_result(response)
    assert result["isError"] is True
    error = json.loads(result["content"][0]["text"])["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert {issue["field"] for issue in error["details"]["issues"]} >= {
        "page",
        "species",
        "oops",
    }


async def test_stateless_sdk_client_discovery_and_call(http_stack):
    reset_client()
    async with Client(http_stack["endpoint"]) as client:
        assert client.protocol_version == PROTOCOL_VERSION

        tools = await client.list_tools()
        assert [tool.name for tool in tools.tools] == ["list_pets"]

        result = await client.call_tool("list_pets", {"page": 1, "pageSize": 5})
        assert result.is_error is False
        payload = json.loads(result.content[0].text)
        assert payload["items"] == SAMPLE_DATA["items"]

        bad = await client.call_tool("list_pets", {"pageSize": 9999})
        assert bad.is_error is True
        assert json.loads(bad.content[0].text)["error"]["code"] == "VALIDATION_ERROR"


async def test_every_request_is_independent(no_handshake_client, http_stack):
    """Two calls on the same connection require no shared session state."""
    first = await post_rpc(
        no_handshake_client, http_stack["endpoint"], "tools/list",
        {"_meta": ENVELOPE_META}, mid=1,
    )
    second = await post_rpc(
        no_handshake_client, http_stack["endpoint"], "tools/list",
        {"_meta": ENVELOPE_META}, mid=2,
    )

    assert first.headers.get("mcp-session-id") is None
    assert second.headers.get("mcp-session-id") is None
    assert parse_result(first) == parse_result(second)
