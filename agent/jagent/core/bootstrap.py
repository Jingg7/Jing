from __future__ import annotations

from .config import AgentConfig
from .history import HistoryStore
from .llm import ChatModel, OpenAIChatModel
from .session import AgentSession
from .tools import FileToolConfig, ToolRegistry, build_default_registry


def create_session(
    config: AgentConfig,
    *,
    model: ChatModel | None = None,
    registry: ToolRegistry | None = None,
    history: HistoryStore | None = None,
) -> AgentSession:
    return AgentSession(
        model=model or OpenAIChatModel(config.llm),
        registry=registry
        or build_default_registry(
            FileToolConfig(config.max_read_bytes),
            search_api_key=config.search.baidu_qianfan_api_key,
        ),
        history=history
        if history is not None
        else HistoryStore(config.history_path),
        system_prompt=config.system_prompt,
    )
