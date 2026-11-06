from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..archive import CONTEXT_DIRECTORY, ContextArchive
from ..skills import SkillManager
from .base import BaseTool
from .cli_tools import RunCliTool
from .context_tools import RecallContextTool
from .datetime_tools import GetDateTool, IsLeapYearTool
from .filesystem import (
    CreateDirectoryTool,
    CreateFileTool,
    DeleteDirectoryTool,
    DeleteFileTool,
    EditFileTool,
    FileToolConfig,
    GetCurrentDirectoryTool,
    GetFileTypeTool,
    ListDirectoryTool,
    ReadFileTool,
    RenameFileOrDirectoryTool,
)
from .registry import ToolRegistry
from .skill_tools import CreateSkillTool, LoadSkillTool
from .web_tools import FetchWebTool, SearchWebTool

if TYPE_CHECKING:
    from ..mcp import McpManager


def build_default_registry(
    file_config: FileToolConfig | None = None,
    *,
    search_api_key: str = "",
    skills: SkillManager | None = None,
    mcp_manager: "McpManager | None" = None,
    context_archive: ContextArchive | None = None,
) -> ToolRegistry:
    config = file_config or FileToolConfig()
    skill_manager = skills or SkillManager.discover(
        max_read_bytes=config.max_read_bytes
    )
    archive = context_archive or ContextArchive(
        Path.cwd() / CONTEXT_DIRECTORY
    )
    tools: list[BaseTool] = [
        GetDateTool(),
        IsLeapYearTool(),
        GetCurrentDirectoryTool(),
        ListDirectoryTool(),
        GetFileTypeTool(config),
        ReadFileTool(config),
        CreateFileTool(),
        EditFileTool(config),
        CreateDirectoryTool(),
        DeleteDirectoryTool(),
        DeleteFileTool(),
        RenameFileOrDirectoryTool(),
        FetchWebTool(
            timeout=config.web_timeout,
            connect_timeout=config.web_connect_timeout,
            max_error_chars=config.web_error_max_chars,
        ),
        SearchWebTool(
            search_api_key,
            timeout=config.web_timeout,
            endpoint=config.search_endpoint,
            max_results=config.search_max_results,
        ),
        RunCliTool(
            timeout=config.cli_timeout,
            max_output_chars=config.cli_max_output_chars,
        ),
        LoadSkillTool(skill_manager),
        CreateSkillTool(skill_manager),
        RecallContextTool(archive),
    ]
    if mcp_manager is not None:
        tools.extend(mcp_manager.build_tools(tool.name for tool in tools))
    return ToolRegistry(tools)


__all__ = [
    "BaseTool",
    "ToolRegistry",
    "FileToolConfig",
    "FetchWebTool",
    "SearchWebTool",
    "RunCliTool",
    "LoadSkillTool",
    "CreateSkillTool",
    "RecallContextTool",
    "build_default_registry",
]
