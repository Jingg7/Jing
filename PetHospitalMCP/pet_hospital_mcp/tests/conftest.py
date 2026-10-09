"""Shared fixtures: mocked Go backend, MCP server, sample payloads."""

from __future__ import annotations

import copy
import os
import socket
import threading
import time
from typing import Any, Callable

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.rest_client import PetHospitalClient, reset_client, set_client
from pet_hospital_mcp.server import build_server, create_app

ENV_KEYS = (
    "MCP_HOST",
    "MCP_PORT",
    "PET_HOSPITAL_BASE_URL",
    "PET_HOSPITAL_TIMEOUT",
    "PET_HOSPITAL_MAX_RETRIES",
    "MCP_LOG_LEVEL",
    "MCP_JSON_RESPONSE",
)

SAMPLE_DATA: dict[str, Any] = {
    "items": [
        {
            "id": "PET-000180",
            "name": "团团",
            "species": "猫",
            "breed": "狸花猫",
            "gender": "母",
            "ageMonths": 78,
            "color": "三花",
            "chipNo": "CHIP-025826",
            "ownerName": "王老师",
            "ownerPhone": "17978092741",
            "ownerAddr": "北京市朝阳区望京路68号",
            "doctor": "陈医生",
            "disease": "皮肤感染",
            "status": "已康复",
            "allergy": "头孢类",
            "records": [
                {
                    "id": "MR-1",
                    "visitDate": "2024-07-20",
                    "doctor": "陈医生",
                    "diagnosis": "皮肤感染",
                    "symptoms": "皮肤红肿",
                    "treatment": "药浴",
                    "prescription": ["药浴液"],
                    "weightKg": 5.35,
                    "temperature": 38.68,
                    "followUp": "3 个月后复诊",
                    "charge": 1651.98,
                    "createdAt": "2024-07-20T13:02:00Z",
                }
            ],
            "charges": [
                {
                    "id": "CH-1",
                    "item": "血常规检查",
                    "category": "检查",
                    "amount": 528.28,
                    "doctor": "陈医生",
                    "date": "2024-07-20",
                }
            ],
            "totalCost": 2110.93,
            "visitCount": 1,
            "createdAt": "2026-09-15T13:50:11+08:00",
            "updatedAt": "2026-09-15T13:50:11+08:00",
        },
        {
            "id": "PET-000181",
            "name": "豆豆",
            "species": "犬",
            "records": None,
            "charges": None,
            "totalCost": 0,
            "visitCount": 0,
        },
    ],
    "total": 2,
    "page": 1,
    "pageSize": 15,
    "totalPages": 1,
    "totalCost": 2110.93,
}


def envelope(data: Any = None, code: int = 200, message: str = "ok") -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "time": "2026-10-07T00:00:00+08:00"}
    if data is not None:
        body["data"] = data
    return body


@pytest.fixture(autouse=True)
def isolated_client():
    """Every test starts from a clean lazily built REST client."""
    reset_client()
    yield
    reset_client()


@pytest.fixture
def inject_client():
    """Factory that injects a mocked client for the current test."""
    clients: list[PetHospitalClient] = []

    def _inject(client: PetHospitalClient) -> PetHospitalClient:
        clients.append(client)
        set_client(client)
        return client

    yield _inject
    reset_client()


@pytest.fixture
def sample_data() -> dict[str, Any]:
    return copy.deepcopy(SAMPLE_DATA)


@pytest.fixture
def settings() -> Settings:
    return Settings(base_url="http://127.0.0.1:8080", max_retries=0)


@pytest.fixture
def server(settings: Settings):
    return build_server(settings)


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
    base_url: str = "http://127.0.0.1:8080",
) -> PetHospitalClient:
    return PetHospitalClient(
        base_url,
        timeout=5.0,
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def captured_client(
    sample_data: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    body: bytes | str | None = None,
    json_body: Any = None,
    exc: Exception | None = None,
    max_retries: int = 0,
):
    """Client + a dict that records the upstream request."""
    seen: dict[str, Any] = {"requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["requests"].append(request)
        if exc is not None:
            raise exc
        if body is not None:
            return httpx.Response(status_code, content=body)
        if json_body is not None:
            return httpx.Response(status_code, json=json_body)
        return httpx.Response(status_code, json=envelope(sample_data or SAMPLE_DATA))

    return make_client(handler, max_retries=max_retries), seen


@pytest.fixture
def inject_client():
    """Factory that injects a mocked client for the current test."""
    clients: list[PetHospitalClient] = []

    def _inject(client: PetHospitalClient) -> PetHospitalClient:
        clients.append(client)
        set_client(client)
        return client

    yield _inject
    for client in clients:
        try:
            client._client.close()
        except Exception:
            pass
    reset_client()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_uvicorn(app: Any, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("uvicorn did not start in time")
    return server, thread


async def backend_list(request) -> JSONResponse:
    return JSONResponse(envelope(SAMPLE_DATA))


async def backend_health(request) -> JSONResponse:
    return JSONResponse({"status": "ok", "petCount": 2})


def build_backend_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/api/v1/pets", backend_list, methods=["GET"]),
            Route("/health", backend_health, methods=["GET"]),
        ]
    )


__all__ = [
    "SAMPLE_DATA",
    "Settings",
    "backend_list",
    "build_backend_app",
    "captured_client",
    "envelope",
    "free_port",
    "make_client",
    "start_uvicorn",
    "Response",
]
