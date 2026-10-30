# JAgent

JAgent 是一个基于 OpenAI 兼容接口的本地文件操作 Agent。项目由 `core` 与 `tui` 两个主要目录组成：`core` 负责配置、模型交互、会话编排、历史持久化和工具执行；`tui` 是使用 Textual 实现的终端界面适配层。

## 设计目标

- 核心业务与界面代码完全隔离，`core` 不依赖 Textual 或任何 UI 框架
- 核心通过事件流向界面输出文本增量、工具调用状态和轮次完成事件
- 工具按业务拆分并注册到统一注册表，便于扩展和测试
- 配置、模型客户端、历史存储和工具均可通过依赖注入替换
- 为未来新增 Web、Desktop 等界面保留统一的接入方式

## 目录结构

```text
agent/jagent/
├── main.py                      # TUI 启动入口
├── config.example.ini           # 模型与 Agent 配置示例
├── config.ini                   # 本地配置（已忽略，不提交）
├── requirements.txt
├── README.md
├── core/
│   ├── __init__.py              # 核心公共 API
│   ├── bootstrap.py             # 组合根：装配模型、工具、历史与会话
│   ├── config.py                # 配置读取与数据类
│   ├── events.py                # UI 无关的事件契约
│   ├── history.py               # 会话历史持久化
│   ├── llm.py                   # ChatModel 协议与 OpenAI 实现
│   ├── session.py               # Agent 会话编排、流式聚合与工具循环
│   ├── skills.py                # Skill 发现、加载与 System Prompt 注入
│   └── tools/
│       ├── __init__.py          # 默认工具注册表
│       ├── base.py              # 工具抽象基类
│       ├── registry.py          # 工具注册与统一错误处理
│       ├── datetime_tools.py    # 时间工具
│       ├── skill_tools.py       # loadSkill 工具
│       ├── web_tools.py         # 网页正文抓取与网络搜索工具
│       └── filesystem/
│           ├── common.py        # 路径、编码、文本检测与安全校验
│           ├── read_tools.py    # 查询类文件工具
│           └── write_tools.py   # 创建、编辑、删除与重命名工具
├── tui/
│   ├── __init__.py
│   ├── app.py                   # Textual App
│   ├── styles.tcss              # Textual 样式
│   └── widgets/
│       ├── __init__.py
│       └── messages.py          # 用户、助手、工具与错误消息组件
└── tests/
    ├── test_session.py
    ├── test_tools.py
    └── test_web_tools.py
```

## 分层说明

| 层级 | 目录 | 职责 |
| --- | --- | --- |
| 配置层 | `core/config.py` | 读取 `config.ini`，生成不可变配置对象 |
| 模型接入层 | `core/llm.py` | 定义 `ChatModel` 协议，封装 OpenAI 异步流式调用 |
| 会话编排层 | `core/session.py` | 维护消息上下文、聚合流式工具调用、执行工具循环、发送事件 |
| 工具领域层 | `core/tools/` | 工具定义、注册、参数分发及具体业务实现 |
| 持久化层 | `core/history.py` | JSON 历史的加载与原子写入 |
| 组合根 | `core/bootstrap.py` | 为 UI 装配可用的 `AgentSession` |
| 界面适配层 | `tui/` | 将核心事件渲染为 Textual 界面，不包含业务逻辑 |

`core` 对外主要暴露 `AgentConfig`、`AgentSession`、`AgentEvent` 和 `create_session`。界面层只需要消费会话事件，不应直接操作工具或消息协议。

## 内置工具

| 工具 | 说明 |
| --- | --- |
| `getDate` | 获取系统日期和时间 |
| `isLeapYear` | 判断闰年 |
| `getCurrentDirectory` | 获取当前工作目录 |
| `listDirectory` | 列出目录中的文件和子目录 |
| `getFileType` | 判断文件类型 |
| `readFile` | 读取纯文本文件，默认最大 1 MB |
| `createFile` | 在指定目录创建新文件，不覆盖已有文件 |
| `editFile` | 覆盖文件内容或替换第一处匹配文本 |
| `createDirectory` | 创建目录，支持多级目录 |
| `deleteDirectory` | 递归删除目录，支持非空目录 |
| `deleteFile` | 删除文件 |
| `renameFileOrDirectory` | 重命名或移动文件、目录 |
| `fetchWeb` | 使用本地 `curl` 获取网页，并通过 trafilatura 提取 Markdown 正文 |
| `searchWeb` | 调用百度千帆搜索 API，返回搜索摘要、标题、URL 和日期 |
| `RunCli` | 调用本地已安装的命令行程序，返回 stdout、stderr 和退出码 |
| `loadSkill` | 按名称加载 Skill 的完整 `SKILL.md`，或加载 Skill 目录内的附件文件 |

删除目录和重命名操作会拒绝文件系统根目录，以及包含当前工作目录的路径。

`fetchWeb` 采用参数列表调用本地 `curl`（不使用 `shell=True`），默认超时 20 秒。它会去除导航栏、广告和页脚，保留标题、段落、列表、表格及链接，并将原始 URL 与 Markdown 正文一起返回。使用前请确保系统已安装 `curl`。

`searchWeb` 需要 `config.ini` 中的 `[search]` 配置，API Key 只从配置文件读取，不会写入代码或工具结果。搜索失败、超时、鉴权错误或缺少配置时，会通过工具结果向模型返回明确的错误信息。

`RunCli` 接受程序名称 `command` 和参数列表 `args`，将二者拼装为参数列表后通过 `subprocess.run(..., shell=False)` 执行，默认超时 30 秒。工具会返回标准输出、标准错误和退出码；单段输出超过 6000 个字符时会截断并标注截断情况。命令以运行 JAgent 的当前用户权限执行，当前阶段未实现命令白名单、黑名单或审批机制，仅用于受控教学实验环境。

## Skill 动态加载

JAgent 以启动时的工作目录作为项目根目录，扫描 `.agents/skills/` 下的 Skill 子目录。每个子目录必须包含 `SKILL.md`，并在文件开头的 YAML Frontmatter 中声明 `name` 和 `description`：

```markdown
---
name: pdf-tools
description: Extract text and metadata from PDF files.
---

# PDF Tools

这里是完整的使用说明，只有在模型调用 `loadSkill` 时才会进入上下文。
```

初始化阶段只解析 Frontmatter，将 `name` 与 `description` 注入 System Prompt，不会读取完整正文。模型需要时调用 `loadSkill`：

- 仅传 `name`：返回该 Skill 的 `SKILL.md` 全文。
- 传 `name` 和 `filename`：读取 Skill 目录内的附件文件。`filename` 支持相对于 Skill 目录、相对于项目根目录以及绝对路径；只传文件名时会递归查找，重名时返回候选路径。
- 所有文件读取都限制在对应 Skill 目录内。

## 运行

```powershell
cd D:\LLM\agent\jagent
pip install -r requirements.txt
python main.py
```

界面操作：

- 在输入框中输入消息，按 `Enter` 发送
- 支持 `Ctrl+V` 粘贴系统剪贴板内容，多行文本会合并为一行
- 也可以点击“发送”按钮
- `Ctrl+Q` 退出

## 配置

将 `config.example.ini` 复制为 `config.ini` 后填写本地配置：

```ini
[llm]
base_url = http://127.0.0.1:1234/v1
model = qwen3.5-4b
api_key = DUMMY

[agent]
history_file = history.json
max_read_bytes = 1048576
system_prompt = 你是一个本地文件与网络信息助手，可以查询时间、搜索互联网、抓取网页正文、读取和编辑纯文本文件、管理目录。

[search]
baidu_qianfan_api_key = your_baidu_qianfan_api_key
```

`history_file` 相对于配置文件所在目录解析。历史记录默认写入 `history.json`，`config.ini` 与 `history.json` 均已在 `.gitignore` 中忽略，不会提交到仓库。

## 核心事件流

`AgentSession.send()` 是异步生成器，UI 层通过类型判断消费事件：

```python
from core.events import (
    AssistantStarted,
    TextDelta,
    AssistantCompleted,
    ToolCallStarted,
    ToolCallFinished,
    TurnCompleted,
)

async for event in session.send("列出当前目录"):
    if isinstance(event, AssistantStarted):
        print("[助手] ", end="")
    elif isinstance(event, TextDelta):
        print(event.text, end="")
    elif isinstance(event, AssistantCompleted):
        print()
    elif isinstance(event, ToolCallStarted):
        print(f"[调用工具] {event.name}")
    elif isinstance(event, ToolCallFinished):
        print(f"[工具结果] {event.output}")
    elif isinstance(event, TurnCompleted):
        print("[完成]")
```

每次模型响应都会产生一组 `AssistantStarted`、若干 `TextDelta` 和 `AssistantCompleted` 事件。工具调用发生在两次响应之间，因此界面可以将工具结果放在正确的时间顺序位置。

## 扩展新的界面

新增 Web 或 Desktop 界面时，建议创建与 `tui` 平级的目录，例如：

```text
agent/jagent/
├── core/
├── tui/
└── web/
```

新界面只需要：

1. 读取 `AgentConfig`
2. 调用 `create_session(config)` 获取 `AgentSession`
3. 调用 `await session.send(prompt)` 并消费 `AgentEvent`
4. 将 `AssistantStarted`、`TextDelta`、`AssistantCompleted`、`ToolCallStarted`、`ToolCallFinished`、`TurnCompleted` 映射到目标 UI

这样可以复用全部业务逻辑、工具能力和历史记录，无需修改 `core`。测试时也可以通过 `create_session(config, model=..., registry=..., history=...)` 注入替身实现。

## 测试

```powershell
cd D:\LLM\agent\jagent
python -m unittest discover -s tests -v
```

测试覆盖工具注册、文件生命周期、二进制文件拒绝、安全校验、流式工具调用聚合和历史持久化。
