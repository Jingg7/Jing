"""Environment driven configuration for the MCP service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_LOG_LEVEL = "INFO"


class ConfigError(ValueError):
    """Raised when an environment variable cannot be used."""


def _get(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _get_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = _get(env, key, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from None


def _get_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = _get(env, key, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from None
    if value != value or value in (float("inf"), float("-inf")):
        raise ConfigError(f"{key} must be a finite number, got {raw!r}")
    return value


@dataclass(frozen=True)
class Settings:
    """Runtime settings, all read from environment variables."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    log_level: str = DEFAULT_LOG_LEVEL
    json_response: bool = True

    @property
    def mcp_endpoint(self) -> str:
        return f"http://{self.host}:{self.port}/mcp"

    @property
    def health_endpoint(self) -> str:
        return f"http://{self.host}:{self.port}/health"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read settings from the environment and validate them."""
    env = os.environ if env is None else env

    host = _get(env, "MCP_HOST", DEFAULT_HOST)
    port = _get_int(env, "MCP_PORT", DEFAULT_PORT)
    if not 1 <= port <= 65535:
        raise ConfigError(f"MCP_PORT must be between 1 and 65535, got {port}")

    base_url = _get(env, "PET_HOSPITAL_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ConfigError(
            "PET_HOSPITAL_BASE_URL must be an http(s) URL, got "
            f"{base_url!r}"
        )

    timeout_seconds = _get_float(env, "PET_HOSPITAL_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
    if timeout_seconds <= 0:
        raise ConfigError("PET_HOSPITAL_TIMEOUT must be greater than 0")

    max_retries = _get_int(env, "PET_HOSPITAL_MAX_RETRIES", DEFAULT_MAX_RETRIES)
    if not 0 <= max_retries <= 5:
        raise ConfigError("PET_HOSPITAL_MAX_RETRIES must be between 0 and 5")

    log_level = _get(env, "MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(f"Unsupported MCP_LOG_LEVEL: {log_level}")

    json_response = _get(env, "MCP_JSON_RESPONSE", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }

    return Settings(
        host=host,
        port=port,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        log_level=log_level,
        json_response=json_response,
    )
