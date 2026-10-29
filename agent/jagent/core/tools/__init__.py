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
from .web_tools import FetchWebTool, SearchWebTool


def build_default_registry(
    file_config: FileToolConfig | None = None,
    *,
    search_api_key: str = "",
) -> ToolRegistry:
    config = file_config or FileToolConfig()
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
        ]
    )


__all__ = [
    "BaseTool",
    "ToolRegistry",
    "FileToolConfig",
    "FetchWebTool",
    "SearchWebTool",
    "RunCliTool",
    "build_default_registry",
]
