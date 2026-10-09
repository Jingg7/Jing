"""HTTP client for the upstream Go Pet Hospital REST API."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping

import httpx

from .config import load_settings
from .errors import (
    BACKEND_API_ERROR,
    BACKEND_INVALID_RESPONSE,
    BACKEND_TIMEOUT,
    BACKEND_UNAVAILABLE,
    MCPToolError,
)
from .models import ListPetsSuccess

LIST_PETS_PATH = "/api/v1/pets"

#: Query parameters accepted by `GET /api/v1/pets`, forwarded verbatim.
QUERY_PARAMS: tuple[str, ...] = (
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
)

_RETRY_BACKOFF_SECONDS = (0.05, 0.15, 0.3)
_MAX_UPSTREAM_MESSAGE = 300


class PetHospitalClient:
    """Small async wrapper around the Go REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> "PetHospitalClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_pets(self, params: Mapping[str, Any]) -> ListPetsSuccess:
        """Call `GET /api/v1/pets` and return the validated `data` object."""
        query = {
            key: params[key]
            for key in QUERY_PARAMS
            if params.get(key) is not None
        }
        attempts = self.max_retries + 1
        last_error: MCPToolError | None = None

        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS[min(attempt - 1, 2)])
            try:
                response = await self._client.get(LIST_PETS_PATH, params=query)
            except httpx.TimeoutException:
                last_error = MCPToolError(
                    code=BACKEND_TIMEOUT,
                    message=f"宠物医院服务在 {self.timeout} 秒内未响应",
                    details={"base_url": self.base_url, "path": LIST_PETS_PATH},
                )
                continue
            except httpx.RequestError:
                last_error = MCPToolError(
                    code=BACKEND_UNAVAILABLE,
                    message="无法连接宠物医院服务",
                    details={"base_url": self.base_url, "path": LIST_PETS_PATH},
                )
                continue

            if response.status_code >= 500:
                last_error = _api_error(response)
                continue
            if response.status_code >= 400:
                raise _api_error(response)
            return _parse_list_pets(response, query)

        assert last_error is not None
        raise last_error


def _truncate(text: str, limit: int = _MAX_UPSTREAM_MESSAGE) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _upstream_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return _truncate(response.text)
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str) and message:
            return _truncate(message)
        code = body.get("code")
        if code is not None:
            return _truncate(f"上游返回 code={code}")
    return _truncate(str(body)) if body else f"HTTP {response.status_code}"


def _api_error(response: httpx.Response) -> MCPToolError:
    return MCPToolError(
        code=BACKEND_API_ERROR,
        message=f"宠物医院接口返回错误（HTTP {response.status_code}）",
        details={
            "http_status": response.status_code,
            "upstream_message": _upstream_message(response),
            "path": LIST_PETS_PATH,
        },
    )


def _parse_list_pets(response: httpx.Response, query: Mapping[str, Any]) -> ListPetsSuccess:
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise MCPToolError(
            code=BACKEND_INVALID_RESPONSE,
            message="宠物医院接口返回了无法解析的响应体",
            details={"http_status": response.status_code, "path": LIST_PETS_PATH},
        ) from None

    if not isinstance(body, dict):
        raise MCPToolError(
            code=BACKEND_INVALID_RESPONSE,
            message="宠物医院接口返回的响应不是 JSON 对象",
            details={"http_status": response.status_code, "path": LIST_PETS_PATH},
        )

    upstream_code = body.get("code")
    data = body.get("data")
    if upstream_code not in (None, 200) or not isinstance(data, dict):
        raise MCPToolError(
            code=BACKEND_INVALID_RESPONSE,
            message="宠物医院接口响应缺少有效的 data 字段",
            details={
                "http_status": response.status_code,
                "upstream_code": upstream_code if isinstance(upstream_code, int) else None,
                "path": LIST_PETS_PATH,
            },
        )

    try:
        return ListPetsSuccess.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError
        issues = [
            {"field": ".".join(str(part) for part in err.get("loc", ())),
             "message": err.get("msg", "")}
            for err in getattr(exc, "errors", lambda: [])()
        ]
        raise MCPToolError(
            code=BACKEND_INVALID_RESPONSE,
            message="宠物医院接口返回的数据结构不符合预期",
            details={"issues": issues[:10], "path": LIST_PETS_PATH},
        ) from None


def _build_client() -> PetHospitalClient:
    settings = load_settings()
    return PetHospitalClient(
        settings.base_url,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


_client: PetHospitalClient | None = None


def get_client() -> PetHospitalClient:
    """Process wide client, created lazily so tests can inject one first."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def set_client(client: PetHospitalClient | None) -> None:
    """Inject (or clear) the client; used by tests."""
    global _client
    _client = client


def reset_client() -> None:
    set_client(None)
