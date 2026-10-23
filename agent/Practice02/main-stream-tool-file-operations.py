import configparser
import json
import mimetypes
import os
import platform
import shutil
import subprocess
from pathlib import Path

from openai import OpenAI

config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")

client = OpenAI(
    base_url=config["llm"]["base_url"],
    api_key=config["llm"]["api_key"],
)

history_file = "history-file-operations.json"
if os.path.exists(history_file):
    with open(history_file, encoding="utf-8") as f:
        messages = json.load(f)
else:
    messages = []

MAX_READ_BYTES = 1024 * 1024

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

tools = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断输入的年份是否为闰年",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，例如 2024",
                    }
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getCurrentDirectory",
            "description": "获取当前工作目录的绝对路径",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDirectory",
            "description": "列出指定目录下的所有文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，默认为当前工作目录",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定文件的文件类型，例如文本文件、图片、音频、视频、压缩包、文档、可执行文件等",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要检查的文件路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "读取指定纯文本文件的内容，仅支持纯文本格式文件，不支持二进制文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的纯文本文件路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "在指定目录下创建新的文件，可选择写入初始内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "新文件所在的目录路径",
                    },
                    "filename": {
                        "type": "string",
                        "description": "新文件的文件名，例如 demo.txt",
                    },
                    "content": {
                        "type": "string",
                        "description": "写入新文件的纯文本内容，默认为空",
                    },
                },
                "required": ["directory", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editFile",
            "description": "编辑指定纯文本文件的内容。提供 old_content 时替换文件中第一处匹配的内容，否则用 content 覆盖整个文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的纯文本文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "新的文本内容",
                    },
                    "old_content": {
                        "type": "string",
                        "description": "可选，要被替换的原文本内容；不提供时覆盖整个文件",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createDirectory",
            "description": "创建一个新目录，支持多级目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要创建的目录路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteDirectory",
            "description": "删除指定目录及其中的全部内容，支持删除非空目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的目录路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteFile",
            "description": "删除指定文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "renameFileOrDirectory",
            "description": "重命名文件或目录，也可用于移动文件或目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_path": {
                        "type": "string",
                        "description": "原文件或目录的路径",
                    },
                    "new_path": {
                        "type": "string",
                        "description": "新的文件或目录路径",
                    },
                },
                "required": ["old_path", "new_path"],
            },
        },
    },
]


def save_history():
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def get_date_by_command():
    if platform.system() == "Windows":
        date_out = subprocess.run(
            ["cmd", "/c", "date", "/t"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        ).stdout.strip()
        time_out = subprocess.run(
            ["cmd", "/c", "time", "/t"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        ).stdout.strip()
        return f"{date_out} {time_out}".strip()
    result = subprocess.run(["date"], capture_output=True, text=True)
    return (result.stdout or result.stderr).strip()


def check_leap_year(year):
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return f"{year}年是闰年"
    return f"{year}年不是闰年"


def resolve_path(path):
    return Path(path).expanduser().resolve()


def decode_text_bytes(data):
    if b"\x00" in data:
        return None
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None


def read_text_file(path):
    target = resolve_path(path)
    if not target.exists():
        raise ValueError(f"文件不存在: {target}")
    if not target.is_file():
        raise ValueError(f"不是文件: {target}")
    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        raise ValueError(f"文件过大（{size} 字节），超过读取上限 {MAX_READ_BYTES} 字节")
    decoded = decode_text_bytes(target.read_bytes())
    if decoded is None:
        raise ValueError("仅支持纯文本文件，该文件不是可识别的文本格式")
    return decoded[0]


def get_current_directory():
    return f"当前工作目录: {Path.cwd().resolve()}"


def list_directory(path="."):
    target = resolve_path(path or ".")
    if not target.exists():
        return f"目录不存在: {target}"
    if not target.is_dir():
        return f"不是目录: {target}"
    entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    directories = [item for item in entries if item.is_dir()]
    files = [item for item in entries if not item.is_dir()]
    lines = [
        f"目录: {target}",
        f"共 {len(entries)} 项（{len(directories)} 个目录，{len(files)} 个文件）:",
    ]
    for item in entries:
        if item.is_dir():
            lines.append(f"[D] {item.name}")
        else:
            try:
                size = item.stat().st_size
                lines.append(f"[F] {item.name} ({size} 字节)")
            except OSError:
                lines.append(f"[F] {item.name} (无法获取大小)")
    return "\n".join(lines)


def get_file_type(path):
    target = resolve_path(path)
    if not target.exists():
        return f"路径不存在: {target}"
    if target.is_dir():
        return f"路径: {target}\n类型: 目录"
    mime, _ = mimetypes.guess_type(target.name)
    ext = target.suffix.lower()
    if ext in TEXT_EXTENSIONS or (mime and mime.startswith("text/")):
        category = "文本文件"
    elif ext in IMAGE_EXTENSIONS or (mime and mime.startswith("image/")):
        category = "图片文件"
    elif ext in AUDIO_EXTENSIONS or (mime and mime.startswith("audio/")):
        category = "音频文件"
    elif ext in VIDEO_EXTENSIONS or (mime and mime.startswith("video/")):
        category = "视频文件"
    elif ext in ARCHIVE_EXTENSIONS:
        category = "压缩包"
    elif ext in DOCUMENT_EXTENSIONS or (mime and mime.startswith("application/pdf")):
        category = "文档文件"
    elif ext in EXECUTABLE_EXTENSIONS:
        category = "可执行文件"
    else:
        try:
            sample = target.read_bytes()[:4096]
        except OSError:
            sample = b""
        category = "文本文件" if decode_text_bytes(sample) else "二进制文件"
    lines = [
        f"路径: {target}",
        f"类型: {category}",
        f"MIME: {mime or '未知'}",
        f"扩展名: {ext or '无'}",
        f"大小: {target.stat().st_size} 字节",
    ]
    return "\n".join(lines)


def read_file(path):
    content = read_text_file(path)
    if content == "":
        return "(文件内容为空)"
    return content


def create_file(directory, filename, content=""):
    base = resolve_path(directory or ".")
    if not base.exists():
        return f"目录不存在: {base}"
    if not base.is_dir():
        return f"不是目录: {base}"
    target = (base / filename).resolve()
    if target.exists():
        return f"文件已存在: {target}"
    if not target.parent.exists():
        return f"目标目录不存在: {target.parent}"
    with open(target, "x", encoding="utf-8", newline="") as f:
        f.write(content)
    return f"已创建文件: {target}（{len(content.encode('utf-8'))} 字节）"


def edit_file(path, content, old_content=None):
    target = resolve_path(path)
    if not target.exists():
        return f"文件不存在: {target}"
    if not target.is_file():
        return f"不是文件: {target}"
    original = read_text_file(str(target))
    if old_content:
        if old_content not in original:
            return f"未在文件中找到要替换的内容: {old_content!r}"
        updated = original.replace(old_content, content, 1)
        action = "已替换文件中的匹配内容"
    else:
        updated = content
        action = "已覆盖写入文件内容"
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(updated)
    return f"{action}: {target}（{len(updated.encode('utf-8'))} 字节）"


def create_directory(path):
    target = resolve_path(path)
    if target.exists():
        if target.is_dir():
            return f"目录已存在: {target}"
        return f"同名文件已存在: {target}"
    target.mkdir(parents=True)
    return f"已创建目录: {target}"


def delete_directory(path):
    target = resolve_path(path)
    if not target.exists():
        return f"目录不存在: {target}"
    if not target.is_dir():
        return f"不是目录: {target}"
    if target == Path(target.anchor):
        return f"拒绝删除根目录: {target}"
    cwd = Path.cwd().resolve()
    if target == cwd or cwd.is_relative_to(target):
        return f"拒绝删除包含当前工作目录的目录: {target}"
    shutil.rmtree(target)
    return f"已删除目录: {target}"


def delete_file(path):
    target = resolve_path(path)
    if not target.exists():
        return f"文件不存在: {target}"
    if target.is_dir():
        return f"不是文件: {target}"
    target.unlink()
    return f"已删除文件: {target}"


def rename_file_or_directory(old_path, new_path):
    source = resolve_path(old_path)
    if not source.exists():
        return f"原路径不存在: {source}"
    cwd = Path.cwd().resolve()
    if source == cwd or cwd.is_relative_to(source):
        return f"拒绝重命名包含当前工作目录的目录: {source}"
    destination = Path(new_path).expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    destination = destination.resolve()
    if destination.exists():
        return f"目标路径已存在: {destination}"
    if not destination.parent.exists():
        return f"目标目录不存在: {destination.parent}"
    shutil.move(str(source), str(destination))
    return f"已重命名: {source} -> {destination}"


def run_tool(name, arguments):
    try:
        args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError as exc:
        return f"参数解析失败: {exc}"
    try:
        if name == "getDate":
            return get_date_by_command()
        if name == "isLeapYear":
            return check_leap_year(int(args["year"]))
        if name == "getCurrentDirectory":
            return get_current_directory()
        if name == "listDirectory":
            return list_directory(args.get("path", "."))
        if name == "getFileType":
            return get_file_type(args["path"])
        if name == "readFile":
            return read_file(args["path"])
        if name == "createFile":
            return create_file(
                args["directory"],
                args["filename"],
                args.get("content", ""),
            )
        if name == "editFile":
            return edit_file(args["path"], args["content"], args.get("old_content"))
        if name == "createDirectory":
            return create_directory(args["path"])
        if name == "deleteDirectory":
            return delete_directory(args["path"])
        if name == "deleteFile":
            return delete_file(args["path"])
        if name == "renameFileOrDirectory":
            return rename_file_or_directory(args["old_path"], args["new_path"])
        return f"未知的工具: {name}"
    except KeyError as exc:
        return f"缺少参数: {exc}"
    except Exception as exc:
        return f"执行失败: {exc}"


def stream_reply():
    reply = ""
    tool_calls = []
    stream = client.chat.completions.create(
        model=config["llm"]["model"],
        messages=messages,
        tools=tools,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            reply += delta.content
            print(delta.content, end="", flush=True)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                while len(tool_calls) <= tc.index:
                    tool_calls.append({"id": "", "name": "", "arguments": ""})
                if tc.id:
                    tool_calls[tc.index]["id"] = tc.id
                if tc.function and tc.function.name:
                    tool_calls[tc.index]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    tool_calls[tc.index]["arguments"] += tc.function.arguments
    print()
    return reply, tool_calls


try:
    while True:
        prompt = input("请输入提示词: ")
        messages.append({"role": "user", "content": prompt})
        while True:
            reply, tool_calls = stream_reply()
            for i, tc in enumerate(tool_calls):
                if not tc["id"]:
                    tc["id"] = f"call_{i}"
            assistant_msg = {"role": "assistant", "content": reply or None}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"] or "{}",
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            if not tool_calls:
                break
            for tc in tool_calls:
                output = run_tool(tc["name"], tc["arguments"])
                print(f"[工具 {tc['name']}] {output}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": output,
                    }
                )
        save_history()
except KeyboardInterrupt:
    save_history()
    print("\n已退出")
