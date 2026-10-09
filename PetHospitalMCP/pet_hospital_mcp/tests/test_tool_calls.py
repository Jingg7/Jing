"""Tool level behaviour: success, validation and upstream failure mapping."""

from __future__ import annotations

import json
import math

import httpx
import pytest
from mcp.client import Client

from pet_hospital_mcp.rest_client import get_client

from .conftest import SAMPLE_DATA, captured_client, envelope

SUCCESS_KEYS = {"items", "total", "page", "pageSize", "totalPages", "totalCost"}

ALL_PARAMS = {
    "q": "肠胃",
    "name": "旺财",
    "ownerName": "张三",
    "ownerPhone": "13800001111",
    "species": "犬",
    "doctor": "李医生",
    "disease": "急性肠胃炎",
    "status": "待就诊",
    "min": 100.0,
    "max": 5000.0,
    "sortBy": "totalCost",
    "order": "desc",
    "page": 2,
    "pageSize": 20,
}


async def call(server, arguments):
    async with Client(server) as client:
        return await client.call_tool("list_pets", arguments)


def error_payload(result):
    payload = json.loads(result.content[0].text)
    assert "error" in payload
    return payload["error"]


def issue_fields(error: dict) -> set[str]:
    return {issue["field"] for issue in error["details"]["issues"]}


async def test_success_returns_backend_data_block(server, inject_client, sample_data):
    client, seen = captured_client(sample_data)
    inject_client(client)

    result = await call(server, ALL_PARAMS)

    assert result.is_error is False
    payload = json.loads(result.content[0].text)
    assert set(payload) == SUCCESS_KEYS
    assert payload["total"] == 2
    assert payload["totalPages"] == 1
    assert payload["totalCost"] == 2110.93
    assert result.structured_content == payload

    request = seen["requests"][0]
    assert request.url.path == "/api/v1/pets"
    assert dict(request.url.params) == {key: str(value) for key, value in ALL_PARAMS.items()}


async def test_success_keeps_null_records_and_charges(server, inject_client, sample_data):
    client, _ = captured_client(sample_data)
    inject_client(client)

    result = await call(server, {"page": 1, "pageSize": 15})

    payload = json.loads(result.content[0].text)
    assert payload["items"][0]["records"] is not None
    assert payload["items"][1]["records"] is None
    assert payload["items"][1]["charges"] is None
    # fields the backend omitted stay omitted
    assert "ownerPhone" not in payload["items"][1]


@pytest.mark.parametrize(
    "arguments,field",
    [
        ({"page": 0}, "page"),
        ({"page": -3}, "page"),
        ({"pageSize": 0}, "pageSize"),
        ({"pageSize": 501}, "pageSize"),
        ({"min": -1}, "min"),
        ({"max": -0.5}, "max"),
        ({"min": 100, "max": 10}, "(root)"),
        ({"species": "龙"}, "species"),
        ({"status": "痊愈"}, "status"),
        ({"sortBy": "password"}, "sortBy"),
        ({"order": "up"}, "order"),
        ({"page": "1"}, "page"),
        ({"pageSize": 1.5}, "pageSize"),
        ({"q": 123}, "q"),
        ({"species": True}, "species"),
        ({"unknownParam": "x"}, "unknownParam"),
    ],
)
async def test_invalid_input_returns_unified_validation_error(
    server, arguments, field
):
    result = await call(server, arguments)

    assert result.is_error is True
    error = error_payload(result)
    assert error["code"] == "VALIDATION_ERROR"
    assert field in issue_fields(error)
    assert isinstance(error["details"], dict)


async def test_array_value_for_numeric_field_is_rejected(server):
    result = await call(server, {"page": [1, 2]})

    assert result.is_error is True
    assert error_payload(result)["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
async def test_nan_and_infinity_are_rejected(server, value):
    result = await server.call_tool("list_pets", {"min": value})

    assert result.is_error is True
    error = error_payload(result)
    assert error["code"] == "VALIDATION_ERROR"
    assert "min" in issue_fields(error)


async def test_backend_error_is_surfaced_as_unified_error(server, inject_client):
    client, _ = captured_client(
        json_body=envelope(code=404, message="记录不存在"), status_code=404
    )
    inject_client(client)

    result = await call(server, {"page": 1})

    assert result.is_error is True
    error = error_payload(result)
    assert error["code"] == "BACKEND_API_ERROR"
    assert error["details"]["http_status"] == 404
    assert error["details"]["upstream_message"] == "记录不存在"


async def test_backend_timeout_is_surfaced_as_unified_error(server, inject_client):
    client, _ = captured_client(exc=httpx.ReadTimeout("timed out"))
    inject_client(client)

    result = await call(server, {"page": 1})

    assert result.is_error is True
    assert error_payload(result)["code"] == "BACKEND_TIMEOUT"


async def test_backend_unavailable_is_surfaced_as_unified_error(server, inject_client):
    client, _ = captured_client(exc=httpx.ConnectError("refused"))
    inject_client(client)

    result = await call(server, {"page": 1})

    assert result.is_error is True
    assert error_payload(result)["code"] == "BACKEND_UNAVAILABLE"


async def test_invalid_backend_payload_is_surfaced(server, inject_client):
    client, _ = captured_client(body="<html>oops</html>")
    inject_client(client)

    result = await call(server, {"page": 1})

    assert result.is_error is True
    assert error_payload(result)["code"] == "BACKEND_INVALID_RESPONSE"


async def test_error_payload_never_leaks_internals(server, inject_client):
    client, _ = captured_client(exc=httpx.ConnectError("refused"))
    inject_client(client)

    result = await call(server, {"page": 1})
    text = result.content[0].text

    for token in ("Traceback", "httpx", "pydantic", "File \"", "mcp."):
        assert token not in text
