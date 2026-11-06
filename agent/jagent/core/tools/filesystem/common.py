from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_READ_BYTES = 1024 * 1024

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv",
    ".json", ".jsonl", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".toml", ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".jsx", ".py", ".pyw", ".java", ".c", ".h", ".cpp", ".hpp", ".cc",
    ".cs", ".go", ".rs", ".rb", ".php", ".pl", ".lua", ".r", ".sql",
    ".sh", ".bat", ".cmd", ".ps1", ".vue", ".svelte", ".tex", ".gradle",
    ".properties", ".env", ".gitignore", ".gitattributes", ".dockerfile",
    ".makefile",
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico",
    ".tif", ".tiff", ".heic",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".m4v"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"}
DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods",
}
EXECUTABLE_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".msi", ".apk"}


@dataclass(frozen=True)
class FileToolConfig:
    max_read_bytes: int = DEFAULT_MAX_READ_BYTES
    file_type_sample_bytes: int = 4096
    cli_timeout: float = 30.0
    cli_max_output_chars: int = 6000
    web_timeout: float = 20.0
    web_connect_timeout: float = 10.0
    web_error_max_chars: int = 500
    search_endpoint: str = (
        "https://qianfan.baidubce.com/v2/ai_search/web_search"
    )
    search_max_results: int = 10


def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def decode_text_bytes(data: bytes) -> tuple[str, str] | None:
    if b"\x00" in data:
        return None
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None


def read_text_file(
    path: str | Path,
    max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
) -> str:
    target = resolve_path(path)
    if not target.exists():
        raise ValueError(f"文件不存在: {target}")
    if not target.is_file():
        raise ValueError(f"不是文件: {target}")
    size = target.stat().st_size
    if size > max_read_bytes:
        raise ValueError(
            f"文件过大（{size} 字节），超过读取上限 {max_read_bytes} 字节"
        )
    decoded = decode_text_bytes(target.read_bytes())
    if decoded is None:
        raise ValueError("仅支持纯文本文件，该文件不是可识别的文本格式")
    return decoded[0]


def format_size(size: int) -> str:
    return f"{size} 字节"


def ensure_safe_directory_operation(target: Path) -> None:
    if target == Path(target.anchor):
        raise ValueError(f"拒绝操作文件系统根目录: {target}")
    cwd = Path.cwd().resolve()
    if target == cwd or cwd.is_relative_to(target):
        raise ValueError(f"拒绝操作包含当前工作目录的路径: {target}")
