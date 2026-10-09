"""Unified structured error model shared by every tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

VALIDATION_ERROR = "VALIDATION_ERROR"
BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
BACKEND_API_ERROR = "BACKEND_API_ERROR"
BACKEND_INVALID_RESPONSE = "BACKEND_INVALID_RESPONSE"
INTERNAL_ERROR = "INTERNAL_ERROR"

ERROR_CODES = (
    VALIDATION_ERROR,
    BACKEND_TIMEOUT,
    BACKEND_UNAVAILABLE,
    BACKEND_API_ERROR,
    BACKEND_INVALID_RESPONSE,
    INTERNAL_ERROR,
)


class ErrorDetail(BaseModel):
    """`error` object of the unified error envelope."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="机器可读的错误码")
    message: str = Field(description="可读的错误信息")
    details: dict[str, Any] = Field(
        default_factory=dict, description="结构化补充信息，不含堆栈"
    )


class ErrorResponse(BaseModel):
    """`{"error": {...}}` envelope returned by every failing tool call."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


@dataclass
class MCPToolError(Exception):
    """Raised inside the adapter; always rendered as the unified envelope."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)
        if self.code not in ERROR_CODES:
            self.code = INTERNAL_ERROR

    def to_model(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorDetail(code=self.code, message=self.message, details=self.details)
        )

    def to_payload(self) -> dict[str, Any]:
        return self.to_model().model_dump(mode="json")


def validation_error(message: str, details: dict[str, Any] | None = None) -> MCPToolError:
    return MCPToolError(
        code=VALIDATION_ERROR, message=message, details=details or {}
    )


def internal_error(message: str = "适配器内部错误") -> MCPToolError:
    return MCPToolError(code=INTERNAL_ERROR, message=message, details={})
