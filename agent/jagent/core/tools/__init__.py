from ..skills import SkillManager
from .base import BaseTool
from .cli_tools import RunCliTool
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


def build_default_registry(
    file_config: FileToolConfig | None = None,
    *,
    search_api_key: str = "",
    skills: SkillManager | None = None,
) -> ToolRegistry:
    config = file_config or FileToolConfig()
    skill_manager = skills or SkillManager.discover(
        max_read_bytes=config.max_read_bytes
    )
    return ToolRegistry(
        [
            GetDateTool(),
            IsLeapYearTool(),
            GetCurrentDirectoryTool(),
            ListDirectoryTool(),
            GetFileTypeTool(),
            ReadFileTool(config),
            CreateFileTool(),
            EditFileTool(config),
            CreateDirectoryTool(),
            DeleteDirectoryTool(),
            DeleteFileTool(),
            RenameFileOrDirectoryTool(),
            FetchWebTool(),
            SearchWebTool(search_api_key),
            RunCliTool(),
            LoadSkillTool(skill_manager),
            CreateSkillTool(skill_manager),
        ]
    )


__all__ = [
    "BaseTool",
    "ToolRegistry",
    "FileToolConfig",
    "FetchWebTool",
    "SearchWebTool",
    "RunCliTool",
    "LoadSkillTool",
    "CreateSkillTool",
    "build_default_registry",
]
