"""Tool registration, name and JSON Schema assertions."""

from __future__ import annotations

import json

from mcp.client import Client

from pet_hospital_mcp.tools.list_pets import (
    ORDER_VALUES,
    SPECIES_VALUES,
    SORT_FIELDS,
    STATUS_VALUES,
    TOOL_DESCRIPTION,
    TOOL_NAME,
)


async def test_single_tool_registered_with_expected_name(server):
    async with Client(server) as client:
        result = await client.list_tools()

    assert [tool.name for tool in result.tools] == [TOOL_NAME]
    assert TOOL_NAME == "list_pets"


async def test_tool_description_documents_purpose_params_and_returns(server):
    async with Client(server) as client:
        result = await client.list_tools()

    description = result.tools[0].description
    assert description == TOOL_DESCRIPTION
    for token in ("用途", "参数", "适用场景", "返回值", "page", "pageSize", "isError"):
        assert token in description


async def test_input_schema_shape(server):
    async with Client(server) as client:
        result = await client.list_tools()

    schema = result.tools[0].input_schema
    assert schema["type"] == "object"
    expected = {
        "q",
        "name",
        "ownerName",
        "ownerPhone",
        "species",
        "doctor",
        "disease",
        "status",
        "min",
        "max",
        "sortBy",
        "order",
        "page",
        "pageSize",
    }
    assert set(schema["properties"]) == expected
    assert not schema.get("required")
    assert "items" not in schema  # no adapter-private parameters


def _nullable_enum(schema: dict) -> list:
    variants = schema.get("anyOf", [schema])
    for variant in variants:
        if "enum" in variant:
            return variant["enum"]
    raise AssertionError(f"no enum in {json.dumps(schema)}")


def _nullable_number_constraints(schema: dict) -> dict:
    variants = schema.get("anyOf", [schema])
    for variant in variants:
        if variant.get("type") in {"number", "integer"}:
            return variant
    raise AssertionError(f"no numeric branch in {json.dumps(schema)}")


async def test_input_schema_enums_and_bounds(server):
    async with Client(server) as client:
        result = await client.list_tools()

    props = result.tools[0].input_schema["properties"]

    assert _nullable_enum(props["species"]) == list(SPECIES_VALUES)
    assert _nullable_enum(props["status"]) == list(STATUS_VALUES)
    assert _nullable_enum(props["sortBy"]) == list(SORT_FIELDS)
    assert _nullable_enum(props["order"]) == list(ORDER_VALUES)

    page = _nullable_number_constraints(props["page"])
    assert page["minimum"] == 1

    page_size = _nullable_number_constraints(props["pageSize"])
    assert page_size["minimum"] == 1
    assert page_size["maximum"] == 500

    minimum = _nullable_number_constraints(props["min"])
    maximum = _nullable_number_constraints(props["max"])
    assert minimum["minimum"] == 0
    assert maximum["minimum"] == 0

    for key in ("q", "name", "ownerName", "ownerPhone", "doctor", "disease"):
        branch = [item for item in props[key].get("anyOf", [props[key]]) if item.get("type") == "string"]
        assert branch, f"{key} should accept a string"


async def test_no_legacy_session_or_handshake_surface(server):
    """The published surface contains nothing from the 1.x session model."""
    async with Client(server) as client:
        result = await client.list_tools()

    blob = json.dumps(result.model_dump(by_alias=True), ensure_ascii=False)
    for token in ("Mcp-Session-Id", "max_sessions", "sessionExpiresAt"):
        assert token not in blob
