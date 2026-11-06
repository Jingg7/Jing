from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from .config import DEFAULT_CONTEXT_WINDOW, DEFAULT_WARNING_RATIO, LLMConfig

WARNING_RATIO = DEFAULT_WARNING_RATIO
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0", "::"}
_HTTP_TIMEOUT = 1.5  # 未提供配置时的兼容默认值


@dataclass(frozen=True)
class ContextUsage:
    used_tokens: int
    window_tokens: int
    is_default_window: bool = False
    warning_ratio: float = WARNING_RATIO

    @property
    def ratio(self) -> float:
        if self.window_tokens <= 0:
            return 0.0
        return self.used_tokens / self.window_tokens

    @property
    def percent(self) -> float:
        return round(self.ratio * 100, 1)

    @property
    def warning_percent(self) -> float:
        return round(self.warning_ratio * 100, 1)

    @property
    def warning(self) -> bool:
        return self.window_tokens > 0 and self.ratio >= self.warning_ratio


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for character in text if ord(character) < 128)
    other_chars = len(text) - ascii_chars
    return math.ceil(ascii_chars / 4) + other_chars


def estimate_value_tokens(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return estimate_text_tokens(value)
    try:
        serialized = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = str(value)
    return estimate_text_tokens(serialized)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    total = 4
    for key, value in message.items():
        if key == "role":
            total += estimate_text_tokens(str(value))
        else:
            total += estimate_value_tokens(value)
    return total


def estimate_messages_tokens(
    messages: Sequence[dict[str, Any]],
    tools: Iterable[dict[str, Any]] = (),
) -> int:
    total = sum(estimate_message_tokens(message) for message in messages)
    total += sum(estimate_value_tokens(tool) for tool in tools)
    return total


def _api_root(base_url: str) -> str | None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return None
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{host}:{port}"


def _read_json(
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = _HTTP_TIMEOUT,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _read_probe_json(
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> Any:
    try:
        return _read_json(url, payload, timeout=timeout)
    except TypeError:
        return _read_json(url, payload)


def _as_positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _context_from_lmstudio(
    root: str,
    model: str,
    timeout: float = _HTTP_TIMEOUT,
) -> int | None:
    try:
        data = _read_probe_json(f"{root}/api/v0/models", None, timeout)
    except Exception:
        return None
    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None

    candidates = [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("id", "")) == model
    ]
    if not candidates:
        valid_items = [item for item in items if isinstance(item, dict)]
        candidates = valid_items if len(valid_items) == 1 else []
    for item in candidates:
        for key in (
            "max_context_length",
            "loaded_context_length",
            "context_length",
            "max_context",
        ):
            value = _as_positive_int(item.get(key))
            if value is not None:
                return value
    return None


def _context_from_ollama(
    root: str,
    model: str,
    timeout: float = _HTTP_TIMEOUT,
) -> int | None:
    try:
        data = _read_probe_json(f"{root}/api/show", {"model": model}, timeout)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    model_info = data.get("model_info")
    if isinstance(model_info, dict):
        for key, value in model_info.items():
            if "context_length" not in str(key):
                continue
            number = _as_positive_int(value)
            if number is not None:
                return number

    parameters = data.get("parameters")
    if isinstance(parameters, str):
        for line in parameters.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "num_ctx":
                number = _as_positive_int(parts[1])
                if number is not None:
                    return number
    return None


def detect_context_window(
    base_url: str,
    model: str,
    *,
    probe_timeout: float = _HTTP_TIMEOUT,
) -> int | None:
    root = _api_root(base_url)
    if root is None:
        return None
    for detector in (_context_from_lmstudio, _context_from_ollama):
        value = detector(root, model, probe_timeout)
        if value is not None:
            return value
    return None


def resolve_context_window(
    llm: LLMConfig,
    explicit_window: int | None = None,
    *,
    probe: bool = True,
    default_window: int = DEFAULT_CONTEXT_WINDOW,
    probe_timeout: float = _HTTP_TIMEOUT,
) -> tuple[int, bool]:
    if explicit_window is not None and explicit_window > 0:
        return explicit_window, False
    if probe:
        detected = detect_context_window(
            llm.base_url,
            llm.model,
            probe_timeout=probe_timeout,
        )
        if detected is not None:
            return detected, False
    return default_window, True
