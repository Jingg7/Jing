"""`list_pets` tool: `GET /api/v1/pets` adapter."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError, WithJsonSchema, model_validator

from ..errors import INTERNAL_ERROR, VALIDATION_ERROR, MCPToolError, validation_error
from ..logging_config import log_tool_call
from ..models import ListPetsSuccess
from ..rest_client import get_client

TOOL_NAME = "list_pets"

SPECIES_VALUES = ("犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他")
STATUS_VALUES = ("待就诊", "就诊中", "住院中", "已康复", "慢性病随访")
SORT_FIELDS = (
    "id",
    "name",
    "ownerName",
    "species",
    "doctor",
    "disease",
    "status",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
)
ORDER_VALUES = ("asc", "desc")

MAX_PAGE_SIZE = 500

TOOL_DESCRIPTION = """\
按条件分页查询宠物医院的宠物档案，等价于 Go 后端的 `GET /api/v1/pets`。

用途：让 Agent 用自然语言条件检索宠物档案，并拿到分页与费用汇总。
参数（全部可选，未提供的参数不会传给后端）：
- q：关键词全文检索（匹配名称/主人/疾病等后端支持的字段）
- name：宠物姓名（精确匹配）
- ownerName：主人姓名
- ownerPhone：主人电话
- species：种类，可选值 犬/猫/兔/鸟/仓鼠/爬宠/其他
- doctor：主治医生
- disease：疾病名称
- status：就诊状态，可选值 待就诊/就诊中/住院中/已康复/慢性病随访
- min/max：总花费区间（非负，且 min <= max）
- sortBy：排序字段，可选值 id/name/ownerName/species/doctor/disease/status/totalCost/visitCount/createdAt/updatedAt
- order：排序方向，asc 或 desc
- page：页码，>= 1；pageSize：每页条数，1-500

适用场景：回答“某主人的宠物有哪些”“花费最高的 10 只宠物”“当前住院中的犬类”等问题。
返回值：成功时返回 Go 响应中的 data 对象（items/total/page/pageSize/totalPages/totalCost），
items 中的每只宠物包含历史病历 records 与消费明细 charges（可能为 null）。
失败时返回 `{"error": {"code", "message", "details"}}` 统一错误结构，并将调用标记为 isError。"""


class ListPetsInput(BaseModel):
    """严格输入模型：拒绝未知字段、非法枚举、越界数值与类型错误。"""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    q: str | None = Field(default=None, description="关键词检索")
    name: str | None = Field(default=None, description="宠物姓名")
    ownerName: str | None = Field(default=None, description="主人姓名")
    ownerPhone: str | None = Field(default=None, description="主人电话")
    species: Literal["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"] | None = Field(
        default=None, description="种类"
    )
    doctor: str | None = Field(default=None, description="主治医生")
    disease: str | None = Field(default=None, description="疾病")
    status: (
        Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"] | None
    ) = Field(default=None, description="就诊状态")
    min: float | None = Field(default=None, ge=0, description="总花费下限")
    max: float | None = Field(default=None, ge=0, description="总花费上限")
    sortBy: (
        Literal[
            "id",
            "name",
            "ownerName",
            "species",
            "doctor",
            "disease",
            "status",
            "totalCost",
            "visitCount",
            "createdAt",
            "updatedAt",
        ]
        | None
    ) = Field(default=None, description="排序字段")
    order: Literal["asc", "desc"] | None = Field(default=None, description="排序方向")
    page: int | None = Field(default=None, ge=1, description="页码")
    pageSize: int | None = Field(default=None, ge=1, le=MAX_PAGE_SIZE, description="每页条数")

    @model_validator(mode="after")
    def _check_range(self) -> "ListPetsInput":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min 不能大于 max")
        return self


_INPUT_SCHEMA = ListPetsInput.model_json_schema()
_PROPERTIES: dict[str, Any] = dict(_INPUT_SCHEMA["properties"])

_SUCCESS_KEYS = ("items", "total", "page", "pageSize", "totalPages", "totalCost")


def input_schema() -> dict[str, Any]:
    """Full JSON Schema published in `tools/list`."""
    schema = dict(_INPUT_SCHEMA)
    schema["additionalProperties"] = False
    return schema


def _field_issues(exc: ValidationError) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        issues.append(
            {
                "field": location or "(root)",
                "message": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return issues


def _validate(raw: Mapping[str, Any]) -> ListPetsInput:
    try:
        return ListPetsInput.model_validate(dict(raw))
    except ValidationError as exc:
        raise validation_error(
            "查询参数校验失败", {"issues": _field_issues(exc)}
        ) from None
    except (TypeError, ValueError):
        raise validation_error("查询参数必须是 JSON 对象") from None


def _raw_arguments(ctx: Context | None, fallback: Mapping[str, Any]) -> dict[str, Any]:
    """Original `arguments` object, so unknown fields stay visible."""
    try:
        request_context = ctx.request_context if ctx is not None else None
    except Exception:
        request_context = None
    params = getattr(request_context, "params", None)
    arguments: Any = None
    if isinstance(params, Mapping):
        arguments = params.get("arguments")
    elif params is not None:
        arguments = getattr(params, "arguments", None)
    if isinstance(arguments, Mapping):
        return dict(arguments)
    return {key: value for key, value in fallback.items() if value is not None}


def _success_result(data: Mapping[str, Any]) -> CallToolResult:
    payload = {key: data[key] for key in _SUCCESS_KEYS if key in data} | {
        key: value for key, value in data.items() if key not in _SUCCESS_KEYS
    }
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structured_content=dict(payload),
    )


def _error_result(error: MCPToolError) -> CallToolResult:
    payload = error.to_payload()
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        is_error=True,
    )


async def list_pets(
    q: Annotated[Any, WithJsonSchema(_PROPERTIES["q"])] = None,
    name: Annotated[Any, WithJsonSchema(_PROPERTIES["name"])] = None,
    ownerName: Annotated[Any, WithJsonSchema(_PROPERTIES["ownerName"])] = None,
    ownerPhone: Annotated[Any, WithJsonSchema(_PROPERTIES["ownerPhone"])] = None,
    species: Annotated[Any, WithJsonSchema(_PROPERTIES["species"])] = None,
    doctor: Annotated[Any, WithJsonSchema(_PROPERTIES["doctor"])] = None,
    disease: Annotated[Any, WithJsonSchema(_PROPERTIES["disease"])] = None,
    status: Annotated[Any, WithJsonSchema(_PROPERTIES["status"])] = None,
    min: Annotated[Any, WithJsonSchema(_PROPERTIES["min"])] = None,
    max: Annotated[Any, WithJsonSchema(_PROPERTIES["max"])] = None,
    sortBy: Annotated[Any, WithJsonSchema(_PROPERTIES["sortBy"])] = None,
    order: Annotated[Any, WithJsonSchema(_PROPERTIES["order"])] = None,
    page: Annotated[Any, WithJsonSchema(_PROPERTIES["page"])] = None,
    pageSize: Annotated[Any, WithJsonSchema(_PROPERTIES["pageSize"])] = None,
    ctx: Context = None,  # type: ignore[assignment]
) -> CallToolResult:
    """Execute the tool; every outcome is a `CallToolResult` (see module docstring)."""
    started = time.perf_counter()
    provided: dict[str, Any] = {
        "q": q,
        "name": name,
        "ownerName": ownerName,
        "ownerPhone": ownerPhone,
        "species": species,
        "doctor": doctor,
        "disease": disease,
        "status": status,
        "min": min,
        "max": max,
        "sortBy": sortBy,
        "order": order,
        "page": page,
        "pageSize": pageSize,
    }
    raw = _raw_arguments(ctx, provided)

    try:
        validated = _validate(raw)
    except MCPToolError as error:
        log_tool_call(
            TOOL_NAME,
            raw,
            "error",
            (time.perf_counter() - started) * 1000,
            level=logging.WARNING,
            error_code=error.code,
        )
        return _error_result(error)

    params = validated.model_dump(exclude_none=True)

    try:
        data = await get_client().list_pets(params)
    except MCPToolError as error:
        log_tool_call(
            TOOL_NAME,
            params,
            "error",
            (time.perf_counter() - started) * 1000,
            level=logging.WARNING,
            error_code=error.code,
        )
        return _error_result(error)
    except Exception:
        log_tool_call(
            TOOL_NAME,
            params,
            "error",
            (time.perf_counter() - started) * 1000,
            level=logging.ERROR,
            error_code=INTERNAL_ERROR,
        )
        return _error_result(
            MCPToolError(code=INTERNAL_ERROR, message="适配器内部错误", details={})
        )

    log_tool_call(
        TOOL_NAME,
        params,
        "success",
        (time.perf_counter() - started) * 1000,
        extra={"total": data.total, "returned_items": len(data.items)},
    )
    payload = data.model_dump(mode="json", exclude_unset=True)
    return _success_result(payload)


def register(server: Any) -> None:
    """Attach the tool to an `MCPServer` instance."""
    server.add_tool(list_pets, name=TOOL_NAME, description=TOOL_DESCRIPTION,
                    structured_output=False)


__all__ = [
    "TOOL_NAME",
    "TOOL_DESCRIPTION",
    "ListPetsInput",
    "ListPetsSuccess",
    "list_pets",
    "input_schema",
    "register",
]
