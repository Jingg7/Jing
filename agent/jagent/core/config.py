from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SYSTEM_PROMPT = (
    "你是一个本地文件与网络信息助手，可以查询时间、搜索互联网、抓取网页正文、"
    "读取和编辑纯文本文件、管理目录。调用工具时请使用准确的路径和 URL。"
    "搜索或抓取失败时请说明原因。只读取纯文本文件，不要操作二进制文件。"
    "执行删除或重命名前请确认用户意图。"
)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class SearchConfig:
    baidu_qianfan_api_key: str = ""


@dataclass(frozen=True)
class AgentConfig:
    llm: LLMConfig
    history_path: Path
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_read_bytes: int = 1024 * 1024
    search: SearchConfig = field(default_factory=SearchConfig)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        history_path: str | Path | None = None,
        system_prompt: str | None = None,
    ) -> "AgentConfig":
        config_path = Path(path).expanduser().resolve()
        parser = configparser.ConfigParser(interpolation=None)
        if not parser.read(config_path, encoding="utf-8"):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        if "llm" not in parser:
            raise ValueError(f"配置文件缺少 [llm] 配置段: {config_path}")

        llm_section = parser["llm"]
        base_url = llm_section.get("base_url", "").strip()
        model = llm_section.get("model", "").strip()
        api_key = llm_section.get("api_key", "DUMMY").strip()
        if not base_url or not model:
            raise ValueError("配置文件缺少 base_url 或 model")

        history_value = history_path or parser.get(
            "agent", "history_file", fallback="history.json"
        )
        resolved_history = Path(history_value).expanduser()
        if not resolved_history.is_absolute():
            resolved_history = (config_path.parent / resolved_history).resolve()

        resolved_prompt = (
            system_prompt
            if system_prompt is not None
            else parser.get("agent", "system_prompt", fallback=DEFAULT_SYSTEM_PROMPT).strip()
        )
        max_read_bytes = parser.getint(
            "agent", "max_read_bytes", fallback=1024 * 1024
        )
        if max_read_bytes <= 0:
            raise ValueError("max_read_bytes 必须大于 0")

        search_api_key = parser.get(
            "search", "baidu_qianfan_api_key", fallback=""
        ).strip()

        return cls(
            llm=LLMConfig(base_url=base_url, model=model, api_key=api_key),
            history_path=resolved_history,
            system_prompt=resolved_prompt,
            max_read_bytes=max_read_bytes,
            search=SearchConfig(baidu_qianfan_api_key=search_api_key),
        )
