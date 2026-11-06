from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.parse import urlparse

from .config import LLMConfig

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0", "::"}
_WILDCARD_HOSTS = {"0.0.0.0", "::"}
_LMSTUDIO_PORT = 1234
_OLLAMA_PORT = 11434
_DEFAULT_START_TIMEOUT = 60.0
_DEFAULT_LOAD_TIMEOUT = 180.0
_DEFAULT_PROBE_TIMEOUT = 0.5
_DEFAULT_POLL_INTERVAL = 0.25


def _log(message: str) -> None:
    print(f"[local-llm] {message}", file=sys.stderr)


def _local_target(base_url: str) -> tuple[str, int] | None:
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return None
    probe_host = "127.0.0.1" if host in _WILDCARD_HOSTS else host
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return probe_host, port


def _is_port_open(
    host: str,
    port: int,
    timeout: float = _DEFAULT_PROBE_TIMEOUT,
) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_until_up(
    host: str,
    port: int,
    timeout: float,
    *,
    probe: Callable[[str, int, float], bool],
    sleep: Callable[[float], None],
    probe_timeout: float = _DEFAULT_PROBE_TIMEOUT,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
) -> bool:
    attempts = max(1, int(timeout / poll_interval))
    for _ in range(attempts):
        if probe(host, port, probe_timeout):
            return True
        sleep(poll_interval)
    return probe(host, port, probe_timeout)


def _load_lmstudio_model(
    executable: str,
    model: str,
    *,
    load_timeout: float,
    run: Callable[..., Any],
    log: Callable[[str], None],
) -> bool:
    try:
        result = run(
            [
                executable,
                "load",
                model,
                "--identifier",
                model,
                "-y",
            ],
            capture_output=True,
            text=True,
            timeout=load_timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"LM Studio 加载模型失败: {exc}")
        return False

    if getattr(result, "returncode", 0) != 0:
        detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "")).strip()
        if "already exists" in detail.lower():
            return True
        log(
            f"LM Studio 加载模型失败，请确认模型名 {model} 存在。"
            + (f" 详情: {detail}" if detail else "")
        )
        return False
    return True


def _start_lmstudio(
    executable: str,
    config: LLMConfig,
    host: str,
    port: int,
    *,
    timeout: float,
    load_timeout: float,
    probe_timeout: float,
    poll_interval: float,
    probe: Callable[[str, int, float], bool],
    run: Callable[..., Any],
    sleep: Callable[[float], None],
    log: Callable[[str], None],
) -> bool:
    log("本地模型服务未运行，正在启动 LM Studio...")
    try:
        run(
            [executable, "server", "start"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"启动 LM Studio 服务失败: {exc}")
        return False

    if not _wait_until_up(
        host,
        port,
        timeout,
        probe=probe,
        sleep=sleep,
        probe_timeout=probe_timeout,
        poll_interval=poll_interval,
    ):
        log("LM Studio 服务启动超时，请手动启动后重试。")
        return False

    log(f"LM Studio 已就绪，正在加载模型 {config.model} ...")
    _load_lmstudio_model(
        executable,
        config.model,
        load_timeout=load_timeout,
        run=run,
        log=log,
    )
    return True


def _start_ollama(
    executable: str,
    config: LLMConfig,
    host: str,
    port: int,
    *,
    timeout: float,
    probe_timeout: float,
    poll_interval: float,
    probe: Callable[[str, int, float], bool],
    popen: Callable[..., Any],
    sleep: Callable[[float], None],
    log: Callable[[str], None],
) -> bool:
    log("本地模型服务未运行，正在启动 Ollama...")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        popen(
            [executable, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError as exc:
        log(f"启动 Ollama 服务失败: {exc}")
        return False

    if not _wait_until_up(
        host,
        port,
        timeout,
        probe=probe,
        sleep=sleep,
        probe_timeout=probe_timeout,
        poll_interval=poll_interval,
    ):
        log("Ollama 服务启动超时，请手动启动后重试。")
        return False

    log(f"Ollama 已就绪，模型 {config.model} 将在首次请求时加载。")
    return True


def ensure_local_server(
    config: LLMConfig,
    *,
    timeout: float = _DEFAULT_START_TIMEOUT,
    load_timeout: float = _DEFAULT_LOAD_TIMEOUT,
    probe_timeout: float = _DEFAULT_PROBE_TIMEOUT,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    probe: Callable[[str, int, float], bool] = _is_port_open,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., Any] = subprocess.run,
    popen: Callable[..., Any] = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = _log,
) -> bool:
    """本地接口不可用时尝试自动拉起 LM Studio 或 Ollama。

    仅处理指向本机的 base_url；远程接口直接返回 False，不会触发任何进程。
    返回值表示调用结束后本地服务是否可用（远程接口或无法启动时为 False）。
    """
    target = _local_target(config.base_url)
    if target is None:
        return False

    host, port = target
    server_is_up = probe(host, port, probe_timeout)

    lms = which("lms") if not server_is_up or port == _LMSTUDIO_PORT else None
    ollama = which("ollama") if not server_is_up else None

    if server_is_up:
        if lms:
            _load_lmstudio_model(
                lms,
                config.model,
                load_timeout=load_timeout,
                run=run,
                log=log,
            )
        return True

    prefer_ollama = port == _OLLAMA_PORT or ":" in config.model

    candidates: list[tuple[str, str]] = []
    if prefer_ollama:
        if ollama:
            candidates.append(("ollama", ollama))
        if lms:
            candidates.append(("lmstudio", lms))
    else:
        if lms:
            candidates.append(("lmstudio", lms))
        if ollama:
            candidates.append(("ollama", ollama))

    if not candidates:
        log("未找到 lms 或 ollama 命令，无法自动启动本地模型服务。")
        return False

    for kind, executable in candidates:
        if kind == "lmstudio":
            started = _start_lmstudio(
                executable,
                config,
                host,
                port,
                timeout=timeout,
                load_timeout=load_timeout,
                probe_timeout=probe_timeout,
                poll_interval=poll_interval,
                probe=probe,
                run=run,
                sleep=sleep,
                log=log,
            )
        else:
            started = _start_ollama(
                executable,
                config,
                host,
                port,
                timeout=timeout,
                probe_timeout=probe_timeout,
                poll_interval=poll_interval,
                probe=probe,
                popen=popen,
                sleep=sleep,
                log=log,
            )
        if started:
            return True

    return False
