from __future__ import annotations

import sys
from pathlib import Path

from .archive import ContextArchive
from .config import AgentConfig
from .context import resolve_context_window
from .history import HistoryStore
from .llm import ChatModel, OpenAIChatModel
from .local_server import ensure_local_server
from .mcp import MCP_CONFIG_FILENAME, McpManager
from .session import AgentSession
from .skills import SkillManager, compose_system_prompt
from .tools import FileToolConfig, ToolRegistry, build_default_registry


def _rooted_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def create_session(
    config: AgentConfig,
    *,
    model: ChatModel | None = None,
    registry: ToolRegistry | None = None,
    history: HistoryStore | None = None,
    project_root: str | Path | None = None,
    skills: SkillManager | None = None,
    mcp_manager: McpManager | None = None,
    mcp_config_path: str | Path | None = None,
    context_archive: ContextArchive | None = None,
    context_window: int | None = None,
) -> AgentSession:
    if model is None:
        ensure_local_server(
            config.llm,
            timeout=config.llm.start_timeout,
            load_timeout=config.llm.load_timeout,
            probe_timeout=config.llm.probe_timeout,
            poll_interval=config.llm.poll_interval,
        )
    root = Path(
        project_root if project_root is not None else Path.cwd()
    ).expanduser().resolve()
    skill_manager = skills or SkillManager.discover(
        root,
        max_read_bytes=config.max_read_bytes,
        skills_directory=config.skills.directory,
        max_frontmatter_lines=config.skills.max_frontmatter_lines,
    )
    archive = context_archive or ContextArchive(
        _rooted_path(root, config.context.archive_directory),
        max_results=config.context.archive_max_results,
        max_chars=config.context.archive_max_chars,
        snippet_chars=config.context.archive_snippet_chars,
    )
    if context_window is not None and context_window > 0:
        window, window_is_default = context_window, False
    else:
        window, window_is_default = resolve_context_window(
            config.llm,
            config.context_window,
            probe=model is None,
            default_window=config.context.default_window,
            probe_timeout=config.context.probe_timeout,
        )

    mcp = mcp_manager
    if registry is None:
        if mcp is None:
            mcp = McpManager(
                mcp_config_path
                if mcp_config_path is not None
                else root / MCP_CONFIG_FILENAME,
                project_root=root,
                connect_timeout=config.mcp.connect_timeout,
                call_timeout=config.mcp.call_timeout,
                close_timeout=config.mcp.close_timeout,
            )
            mcp.prepare()
            for error in mcp.startup_errors:
                print(f"[MCP] {error}", file=sys.stderr)
        registry = build_default_registry(
            FileToolConfig(
                max_read_bytes=config.max_read_bytes,
                file_type_sample_bytes=config.tools.file_type_sample_bytes,
                cli_timeout=config.tools.cli_timeout,
                cli_max_output_chars=config.tools.cli_max_output_chars,
                web_timeout=config.tools.web_timeout,
                web_connect_timeout=config.tools.web_connect_timeout,
                web_error_max_chars=config.tools.web_error_max_chars,
                search_endpoint=config.search.endpoint,
                search_max_results=config.search.max_results,
            ),
            search_api_key=config.search.baidu_qianfan_api_key,
            skills=skill_manager,
            mcp_manager=mcp,
            context_archive=archive,
        )
    return AgentSession(
        model=model or OpenAIChatModel(config.llm),
        registry=registry,
        history=history
        if history is not None
        else HistoryStore(config.history_path),
        system_prompt=compose_system_prompt(config.system_prompt, skill_manager),
        context_archive=archive,
        context_window=window,
        context_window_is_default=window_is_default,
        context_warning_ratio=config.context.warning_ratio,
        compaction_target_tokens=config.context.compaction_target_tokens,
        agents_file=_rooted_path(root, config.session.agents_file),
        mcp_manager=mcp,
    )
