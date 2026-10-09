"""`GET /api/v1/pets` forwarding and upstream error mapping."""

from __future__ import annotations

import httpx
import pytest

from pet_hospital_mcp.errors import (
    BACKEND_API_ERROR,
    BACKEND_INVALID_RESPONSE,
    BACKEND_TIMEOUT,
    BACKEND_UNAVAILABLE,
    ERROR_CODES,
    MCPToolError,
)
from pet_hospital_mcp.rest_client import LIST_PETS_PATH, get_client

from .conftest import SAMPLE_DATA, captured_client, envelope

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


async def test_forwards_path_and_every_query_parameter(inject_client, sample_data):
    client, seen = captured_client(sample_data)
    inject_client(client)

    data = await get_client().list_pets(ALL_PARAMS)

    request = seen["requests"][0]
    assert request.method == "GET"
    assert request.url.path == LIST_PETS_PATH
    assert dict(request.url.params) == {key: str(value) for key, value in ALL_PARAMS.items()}
    assert data.total == 2
    assert data.page == sample_data["page"]
    assert data.pageSize == sample_data["pageSize"]
    assert data.totalPages == 1
    assert data.totalCost == 2110.93
    assert data.items[0].records is not None
    assert data.items[1].records is None
    assert data.items[1].charges is None


async def test_omits_absent_parameters(inject_client, sample_data):
    client, seen = captured_client(sample_data)
    inject_client(client)

    await get_client().list_pets({"page": 1, "pageSize": 15, "species": None, "q": None})

    assert dict(seen["requests"][0].url.params) == {"page": "1", "pageSize": "15"}


async def test_backend_4xx_maps_to_api_error(inject_client):
    client, _ = captured_client(
        json_body=envelope(code=404, message="记录不存在"), status_code=404
    )
    inject_client(client)

    with pytest.raises(MCPToolError) as excinfo:
        await get_client().list_pets({"page": 1})

    error = excinfo.value
    assert error.code == BACKEND_API_ERROR
    assert error.details["http_status"] == 404
    assert error.details["upstream_message"] == "记录不存在"


async def test_backend_5xx_retries_then_maps_to_api_error(inject_client):
    client, seen = captured_client(
        json_body={"code": 500, "message": "内部错误"}, status_code=500, max_retries=1
    )
    inject_client(client)

    with pytest.raises(MCPToolError) as excinfo:
        await get_client().list_pets({"page": 1})

    assert excinfo.value.code == BACKEND_API_ERROR
    assert len(seen["requests"]) == 2


async def test_timeout_maps_to_backend_timeout(inject_client):
    client, seen = captured_client(exc=httpx.ReadTimeout("read timed out"), max_retries=1)
    inject_client(client)

    with pytest.raises(MCPToolError) as excinfo:
        await get_client().list_pets({"page": 1})

    assert excinfo.value.code == BACKEND_TIMEOUT
    assert len(seen["requests"]) == 2
    assert "Traceback" not in excinfo.value.message


async def test_connect_error_maps_to_backend_unavailable(inject_client):
    client, _ = captured_client(exc=httpx.ConnectError("connection refused"))
    inject_client(client)

    with pytest.raises(MCPToolError) as excinfo:
        await get_client().list_pets({"page": 1})

    assert excinfo.value.code == BACKEND_UNAVAILABLE


async def test_non_json_body_maps_to_invalid_response(inject_client):
    client, _ = captured_client(body="<html>not json</html>", status_code=200)
    inject_client(client)

    with pytest.raises(MCPToolError) as excinfo:
        await get_client().list_pets({"page": 1})

    assert excinfo.value.code == BACKEND_INVALID_RESPONSE


async def test_missing_data_maps_to_invalid_response(inject_client):
    client, _ = captured_client(json_body={"code": 200, "message": "ok"})
    inject_client(client)

    with pytest.raises(MCPToolError) as excinfo:
        await get_client().list_pets({"page": 1})

    assert excinfo.value.code == BACKEND_INVALID_RESPONSE


async def test_wrong_data_shape_maps_to_invalid_response(inject_client):
    broken = dict(SAMPLE_DATA)
    broken["items"] = "not-a-list"
    client, _ = captured_client(json_body=envelope(broken))
    inject_client(client)

    with pytest.raises(MCPToolError) as excinfo:
        await get_client().list_pets({"page": 1})

    assert excinfo.value.code == BACKEND_INVALID_RESPONSE
    assert excinfo.value.details["issues"][0]["field"] == "items"


async def test_error_codes_are_the_documented_set():
    assert set(ERROR_CODES) == {
        "VALIDATION_ERROR",
        "BACKEND_TIMEOUT",
        "BACKEND_UNAVAILABLE",
        "BACKEND_API_ERROR",
        "BACKEND_INVALID_RESPONSE",
        "INTERNAL_ERROR",
    }
