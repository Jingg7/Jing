from __future__ import annotations

from pathlib import Path

from .config import AgentConfig
from .history import HistoryStore
from .llm import ChatModel, OpenAIChatModel
from .session import AgentSession
from .skills import SkillManager, compose_system_prompt
from .tools import FileToolConfig, ToolRegistry, build_default_registry


def create_session(
    config: AgentConfig,
    *,
    model: ChatModel | None = None,
    registry: ToolRegistry | None = None,
    history: HistoryStore | None = None,
    project_root: str | Path | None = None,
    skills: SkillManager | None = None,
) -> AgentSession:
    skill_manager = skills or SkillManager.discover(
        project_root,
        max_read_bytes=config.max_read_bytes,
    )
    return AgentSession(
        model=model or OpenAIChatModel(config.llm),
        registry=registry
        or build_default_registry(
            FileToolConfig(config.max_read_bytes),
            search_api_key=config.search.baidu_qianfan_api_key,
            skills=skill_manager,
        ),
        history=history
        if history is not None
        else HistoryStore(config.history_path),
        system_prompt=compose_system_prompt(config.system_prompt, skill_manager),
    )
