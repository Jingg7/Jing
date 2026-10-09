"""Structured logging and sensitive value masking."""

from __future__ import annotations

import io
import json
import logging

from pet_hospital_mcp.logging_config import (
    JsonFormatter,
    SENSITIVE_KEYS,
    log_tool_call,
    mask_sensitive,
    setup_logging,
)


def test_sensitive_keys_cover_camel_and_snake_case():
    assert SENSITIVE_KEYS == {
        "ownerphone",
        "owner_phone",
        "owneraddr",
        "owner_addr",
        "chipno",
        "chip_no",
    }


def test_masking_is_recursive():
    raw = {
        "ownerPhone": "13800001111",
        "owner_phone": "13800001111",
        "ownerAddr": "北京市朝阳区望京路68号",
        "owner_addr": "北京市朝阳区望京路68号",
        "chipNo": "CHIP-025826",
        "chip_no": "CHIP-025826",
        "nested": [{"chipNo": "CHIP-000001", "deep": {"ownerAddr": "somewhere"}}],
        "items": [{"ownerPhone": "17978092741", "name": "团团"}],
        "name": "团团",
    }

    masked = mask_sensitive(raw)

    assert masked["name"] == "团团"
    for key in ("ownerPhone", "owner_phone", "ownerAddr", "owner_addr", "chipNo", "chip_no"):
        assert masked[key] != raw[key]
        assert "*" in masked[key]
    assert masked["nested"][0]["chipNo"] != "CHIP-000001"
    assert masked["nested"][0]["deep"]["ownerAddr"] != "somewhere"
    assert "*" in masked["nested"][0]["deep"]["ownerAddr"]
    assert masked["items"][0]["ownerPhone"] != "17978092741"
    assert masked["items"][0]["name"] == "团团"
    # original object untouched
    assert raw["ownerPhone"] == "13800001111"


def test_tool_call_log_has_required_fields_and_masks():
    stream = io.StringIO()
    logger = setup_logging("INFO", stream=stream)
    logger.handlers[0].setFormatter(JsonFormatter())
    logger.handlers[0].stream = stream

    log_tool_call(
        "list_pets",
        {"ownerPhone": "13800001111", "chipNo": "CHIP-025826", "page": 1},
        "success",
        12.5,
        extra={"ownerAddr": "北京市朝阳区望京路68号"},
    )

    record = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert record["tool_name"] == "list_pets"
    assert record["status"] == "success"
    assert record["duration_ms"] == 12.5
    assert "timestamp" in record
    assert record["params"]["page"] == 1
    assert record["params"]["ownerPhone"] != "13800001111"
    assert record["params"]["chipNo"] != "CHIP-025826"
    assert record["ownerAddr"] != "北京市朝阳区望京路68号"
    assert "13800001111" not in json.dumps(record)


def test_error_log_carries_error_code():
    stream = io.StringIO()
    logger = setup_logging("WARNING", stream=stream)
    logger.handlers[0].setFormatter(JsonFormatter())
    logger.handlers[0].stream = stream

    log_tool_call("list_pets", {"page": 0}, "error", 3.2,
                  level=logging.WARNING, error_code="VALIDATION_ERROR")

    record = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert record["error_code"] == "VALIDATION_ERROR"
    assert record["status"] == "error"
    assert record["level"] == "WARNING"
