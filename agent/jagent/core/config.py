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

CONFIG_FILENAME = "config.ini"
DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_WARNING_RATIO = 0.6
DEFAULT_ARCHIVE_MAX_RESULTS = 20
DEFAULT_ARCHIVE_MAX_CHARS = 8_000
DEFAULT_ARCHIVE_SNIPPET_CHARS = 600
DEFAULT_COMPACTION_TARGET_TOKENS = 5_000
DEFAULT_SEARCH_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"
DEFAULT_SEARCH_MAX_RESULTS = 10


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    start_timeout: float = 60.0
    load_timeout: float = 180.0
    probe_timeout: float = 0.5
    poll_interval: float = 0.25


@dataclass(frozen=True)
class SearchConfig:
    baidu_qianfan_api_key: str = ""
    endpoint: str = DEFAULT_SEARCH_ENDPOINT
    max_results: int = DEFAULT_SEARCH_MAX_RESULTS


@dataclass(frozen=True)
class ToolConfig:
    max_read_bytes: int = 1024 * 1024
    file_type_sample_bytes: int = 4096
    cli_timeout: float = 30.0
    cli_max_output_chars: int = 6000
    web_timeout: float = 20.0
    web_connect_timeout: float = 10.0
    web_error_max_chars: int = 500


@dataclass(frozen=True)
class McpConfig:
    connect_timeout: float = 15.0
    call_timeout: float = 60.0
    close_timeout: float = 10.0


@dataclass(frozen=True)
class ContextConfig:
    default_window: int = DEFAULT_CONTEXT_WINDOW
    warning_ratio: float = DEFAULT_WARNING_RATIO
    archive_directory: Path = field(
        default_factory=lambda: Path(".agents") / "context"
    )
    archive_max_results: int = DEFAULT_ARCHIVE_MAX_RESULTS
    archive_max_chars: int = DEFAULT_ARCHIVE_MAX_CHARS
    archive_snippet_chars: int = DEFAULT_ARCHIVE_SNIPPET_CHARS
    compaction_target_tokens: int = DEFAULT_COMPACTION_TARGET_TOKENS
    probe_timeout: float = 1.5


@dataclass(frozen=True)
class SkillConfig:
    directory: Path = field(
        default_factory=lambda: Path(".agents") / "skills"
    )
    max_frontmatter_lines: int = 512


@dataclass(frozen=True)
class SessionConfig:
    directory: Path = field(
        default_factory=lambda: Path(".agents") / "sessions"
    )
    agents_file: Path = field(default_factory=lambda: Path("AGENTS.md"))


@dataclass(frozen=True)
class UiConfig:
    sidebar_width: int = 22
    sidebar_min_width: int = 16
    sidebar_max_width: int = 40
    display_max_chars: int = 4000


@dataclass(frozen=True)
class AgentConfig:
    llm: LLMConfig
    history_path: Path
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_read_bytes: int = 1024 * 1024
    context_window: int | None = None
    search: SearchConfig = field(default_factory=SearchConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    skills: SkillConfig = field(default_factory=SkillConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    ui: UiConfig = field(default_factory=UiConfig)

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

        start_timeout = _positive_float(
            _value(parser, "llm", "start_timeout", "60"),
            "llm.start_timeout",
        )
        load_timeout = _positive_float(
            _value(parser, "llm", "load_timeout", "180"),
            "llm.load_timeout",
        )
        probe_timeout = _positive_float(
            _value(parser, "llm", "probe_timeout", "0.5"),
            "llm.probe_timeout",
        )
        poll_interval = _positive_float(
            _value(parser, "llm", "poll_interval", "0.25"),
            "llm.poll_interval",
        )

        history_value = history_path or _value(
            parser, "agent", "history_file", "history.json"
        )
        resolved_history = _resolve_path(history_value, config_path.parent)

        resolved_prompt = (
            system_prompt
            if system_prompt is not None
            else _value(
                parser, "agent", "system_prompt", DEFAULT_SYSTEM_PROMPT
            )
        )

        max_read_value = _value(
            parser,
            "tools",
            "max_read_bytes",
            _value(parser, "agent", "max_read_bytes", "1048576"),
        )
        max_read_bytes = _positive_int(max_read_value, "max_read_bytes")

        tools = ToolConfig(
            max_read_bytes=max_read_bytes,
            file_type_sample_bytes=_positive_int(
                _value(parser, "tools", "file_type_sample_bytes", "4096"),
                "tools.file_type_sample_bytes",
            ),
            cli_timeout=_positive_float(
                _value(parser, "tools", "cli_timeout", "30"),
                "tools.cli_timeout",
            ),
            cli_max_output_chars=_positive_int(
                _value(parser, "tools", "cli_max_output_chars", "6000"),
                "tools.cli_max_output_chars",
            ),
            web_timeout=_positive_float(
                _value(parser, "tools", "web_timeout", "20"),
                "tools.web_timeout",
            ),
            web_connect_timeout=_positive_float(
                _value(parser, "tools", "web_connect_timeout", "10"),
                "tools.web_connect_timeout",
            ),
            web_error_max_chars=_positive_int(
                _value(parser, "tools", "web_error_max_chars", "500"),
                "tools.web_error_max_chars",
            ),
        )

        search = SearchConfig(
            baidu_qianfan_api_key=_value(
                parser, "search", "baidu_qianfan_api_key", ""
            ),
            endpoint=_value(
                parser, "search", "endpoint", DEFAULT_SEARCH_ENDPOINT
            )
            or DEFAULT_SEARCH_ENDPOINT,
            max_results=_positive_int(
                _value(
                    parser,
                    "search",
                    "max_results",
                    str(DEFAULT_SEARCH_MAX_RESULTS),
                ),
                "search.max_results",
            ),
        )

        context_window_value = _value(parser, "agent", "context_window", "")
        context_window = (
            _positive_int(context_window_value, "context_window")
            if context_window_value
            else None
        )

        context = ContextConfig(
            default_window=_positive_int(
                _value(
                    parser,
                    "context",
                    "default_window",
                    str(DEFAULT_CONTEXT_WINDOW),
                ),
                "context.default_window",
            ),
            archive_directory=_path(
                _value(parser, "context", "archive_directory", ".agents/context")
            ),
            warning_ratio=_ratio(
                _value(
                    parser,
                    "context",
                    "warning_ratio",
                    str(DEFAULT_WARNING_RATIO),
                ),
                "context.warning_ratio",
            ),
            archive_max_results=_positive_int(
                _value(
                    parser,
                    "context",
                    "archive_max_results",
                    str(DEFAULT_ARCHIVE_MAX_RESULTS),
                ),
                "context.archive_max_results",
            ),
            archive_max_chars=_positive_int(
                _value(
                    parser,
                    "context",
                    "archive_max_chars",
                    str(DEFAULT_ARCHIVE_MAX_CHARS),
                ),
                "context.archive_max_chars",
            ),
            archive_snippet_chars=_positive_int(
                _value(
                    parser,
                    "context",
                    "archive_snippet_chars",
                    str(DEFAULT_ARCHIVE_SNIPPET_CHARS),
                ),
                "context.archive_snippet_chars",
            ),
            compaction_target_tokens=_positive_int(
                _value(
                    parser,
                    "context",
                    "compaction_target_tokens",
                    str(DEFAULT_COMPACTION_TARGET_TOKENS),
                ),
                "context.compaction_target_tokens",
            ),
            probe_timeout=_positive_float(
                _value(parser, "context", "probe_timeout", "1.5"),
                "context.probe_timeout",
            ),
        )

        mcp = McpConfig(
            connect_timeout=_positive_float(
                _value(parser, "mcp", "connect_timeout", "15"),
                "mcp.connect_timeout",
            ),
            call_timeout=_positive_float(
                _value(parser, "mcp", "call_timeout", "60"),
                "mcp.call_timeout",
            ),
            close_timeout=_positive_float(
                _value(parser, "mcp", "close_timeout", "10"),
                "mcp.close_timeout",
            ),
        )

        skills = SkillConfig(
            directory=_path(
                _value(parser, "skills", "directory", ".agents/skills")
            ),
            max_frontmatter_lines=_positive_int(
                _value(parser, "skills", "max_frontmatter_lines", "512"),
                "skills.max_frontmatter_lines",
            ),
        )

        session = SessionConfig(
            directory=_path(
                _value(parser, "session", "directory", ".agents/sessions")
            ),
            agents_file=_path(
                _value(parser, "session", "agents_file", "AGENTS.md")
            ),
        )

        sidebar_min_width = _positive_int(
            _value(parser, "ui", "sidebar_min_width", "16"),
            "ui.sidebar_min_width",
        )
        sidebar_max_width = _positive_int(
            _value(parser, "ui", "sidebar_max_width", "40"),
            "ui.sidebar_max_width",
        )
        if sidebar_max_width < sidebar_min_width:
            raise ValueError("ui.sidebar_max_width 不能小于 ui.sidebar_min_width")
        sidebar_width = _positive_int(
            _value(parser, "ui", "sidebar_width", "22"),
            "ui.sidebar_width",
        )
        sidebar_width = max(sidebar_min_width, min(sidebar_max_width, sidebar_width))
        ui = UiConfig(
            sidebar_width=sidebar_width,
            sidebar_min_width=sidebar_min_width,
            sidebar_max_width=sidebar_max_width,
            display_max_chars=_positive_int(
                _value(parser, "ui", "display_max_chars", "4000"),
                "ui.display_max_chars",
            ),
        )

        return cls(
            llm=LLMConfig(
                base_url=base_url,
                model=model,
                api_key=api_key,
                start_timeout=start_timeout,
                load_timeout=load_timeout,
                probe_timeout=probe_timeout,
                poll_interval=poll_interval,
            ),
            history_path=resolved_history,
            system_prompt=resolved_prompt,
            max_read_bytes=max_read_bytes,
            context_window=context_window,
            search=search,
            tools=tools,
            mcp=mcp,
            context=context,
            skills=skills,
            session=session,
            ui=ui,
        )


def _value(
    parser: configparser.ConfigParser,
    section: str,
    option: str,
    fallback: str,
) -> str:
    if section in parser and parser.has_option(section, option):
        return parser.get(section, option).strip()
    return fallback


def _path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    resolved = Path(value).expanduser()
    if not resolved.is_absolute():
        resolved = base_dir / resolved
    return resolved.resolve()


def _positive_int(value: str | int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是正整数") from exc
    if number <= 0:
        raise ValueError(f"{name} 必须是正整数")
    return number


def _positive_float(value: str | float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是正数") from exc
    if number <= 0:
        raise ValueError(f"{name} 必须是正数")
    return number


def _ratio(value: str | float, name: str) -> float:
    number = _positive_float(value, name)
    if number > 1:
        raise ValueError(f"{name} 必须在 0 到 1 之间")
    return number


DEFAULT_CONFIG_TEMPLATE = """\
# JAgent 配置文件
# 首次运行会在当前工作目录生成此文件。请按实际情况修改后重新启动 jagent。

[llm]
# 本地 OpenAI 兼容接口。以下为 LM Studio 的默认 Mock 配置。
base_url = http://127.0.0.1:1234/v1
model = qwen3.5-4b
api_key = DUMMY
# 本地模型服务启动与模型加载超时（秒）
start_timeout = 60
load_timeout = 180
probe_timeout = 0.5
poll_interval = 0.25

[agent]
# 未执行 /save 时的自动历史文件
history_file = history.json
# 可选。模型上下文窗口大小；留空时尝试自动探测。
# context_window = 128000
system_prompt = 你是一个本地文件与网络信息助手，可以查询时间、搜索互联网、抓取网页正文、读取和编辑纯文本文件、管理目录。调用工具时请使用准确的路径和 URL。搜索或抓取失败时请说明原因。只读取纯文本文件，不要操作二进制文件。执行删除或重命名前请确认用户意图。

[tools]
max_read_bytes = 1048576
file_type_sample_bytes = 4096
cli_timeout = 30
cli_max_output_chars = 6000
web_timeout = 20
web_connect_timeout = 10
web_error_max_chars = 500

[search]
baidu_qianfan_api_key = your_baidu_qianfan_api_key
endpoint = https://qianfan.baidubce.com/v2/ai_search/web_search
max_results = 10

[context]
default_window = 128000
warning_ratio = 0.6
archive_directory = .agents/context
archive_max_results = 20
archive_max_chars = 8000
archive_snippet_chars = 600
compaction_target_tokens = 5000
probe_timeout = 1.5

[skills]
directory = .agents/skills
max_frontmatter_lines = 512

[mcp]
connect_timeout = 15
call_timeout = 60
close_timeout = 10

[session]
directory = .agents/sessions
agents_file = AGENTS.md

[ui]
sidebar_width = 22
sidebar_min_width = 16
sidebar_max_width = 40
display_max_chars = 4000
"""


def write_default_config(path: str | Path) -> Path:
    config_path = Path(path).expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return config_path


def ensure_config_file(path: str | Path) -> tuple[Path, bool]:
    config_path = Path(path).expanduser().resolve()
    if config_path.exists():
        return config_path, False
    write_default_config(config_path)
    return config_path, True
