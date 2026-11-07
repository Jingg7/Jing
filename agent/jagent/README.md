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
├── .mcp.json                    # MCP Server 连接配置
├── requirements.txt
├── README.md
├── core/
│   ├── __init__.py              # 核心公共 API
│   ├── archive.py               # 原始上下文归档与全文关键词检索
│   ├── bootstrap.py             # 组合根：装配模型、工具、历史与会话
│   ├── compaction.py            # 上下文压缩 Prompt 与历史转录
│   ├── config.py                # 配置读取与数据类
│   ├── context.py               # Token 估算、上下文使用量与窗口探测
│   ├── events.py                # UI 无关的事件契约
│   ├── history.py               # 会话历史持久化
│   ├── llm.py                   # ChatModel 协议与 OpenAI 实现
│   ├── local_server.py          # 启动时自动拉起本地 LM Studio / Ollama
│   ├── mcp.py                   # MCP Client、连接管理与工具适配
│   ├── session.py               # Agent 会话编排、流式聚合与工具循环
│   ├── sessions.py              # 多会话保存、恢复与索引
│   ├── skills.py                # Skill 发现、加载与 System Prompt 注入
│   └── tools/
│       ├── __init__.py          # 默认工具注册表
│       ├── base.py              # 工具抽象基类
│       ├── context_tools.py     # recallContext 工具
│       ├── registry.py          # 工具注册与统一错误处理
│       ├── datetime_tools.py    # 时间工具
│       ├── skill_tools.py       # loadSkill / createSkill 工具
│       ├── web_tools.py         # 网页正文抓取与网络搜索工具
│       └── filesystem/
│           ├── common.py        # 路径、编码、文本检测与安全校验
│           ├── read_tools.py    # 查询类文件工具
│           └── write_tools.py   # 创建、编辑、删除与重命名工具
├── tui/
│   ├── __init__.py
│   ├── app.py                   # Textual App
│   ├── first_run.py             # 首次运行配置提示窗口
│   ├── styles.tcss              # Textual 样式
│   └── widgets/
│       ├── __init__.py
│       ├── compact.py           # 压缩前后对比浮动面板
│       ├── palette.py           # Slash 命令与会话选择面板
│       └── messages.py          # 用户、助手、工具与错误消息组件
└── tests/
    ├── test_context.py          # 上下文压缩、归档与检索测试
    ├── test_mcp.py
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
| `createSkill` | 根据名称和完整内容创建符合规范的 Skill，已存在时不覆盖 |
| `recallContext` | 在上下文归档中全文检索历史消息，支持按归档编号过滤 |

MCP Server 通过 `list_tools()` 暴露的工具会在启动时动态注册到同一工具注册表中，调用方式与上述本地工具完全一致。

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

模型也可以调用 `createSkill` 根据自然语言要求创建新的 Skill。工具接收 `name` 和 `skillContext` 两个参数，将名称规范化为小写字母、数字和连字符组成的格式，并在 `.agents/skills/<name>/SKILL.md` 中写入包含 `name`、`description` 和正文的完整内容。`skillContext` 可以自带 YAML Frontmatter，其中的 `description` 会被保留；未提供时会从正文首段自动生成。如果同名 Skill 已存在，工具只返回提示，不会覆盖原内容。需要补充 `references/`、`scripts/` 等目录或文件时，模型应继续调用 `createDirectory`、`createFile` 等文件工具。

## MCP Client

JAgent 读取当前工作目录下的 `.mcp.json`，使用 MCP Python SDK 连接配置中的 Server，并调用 `list_tools()` 把远端工具动态注册到现有工具注册表。支持 `stdio` 和 `streamable_http` 两种传输方式。TUI 启动后会在后台异步加载 MCP；连接进度、已连接 Server 和可用工具会在侧边栏动态刷新：

```json
{
  "mcpServers": {
    "Bazi-MCP": {
      "type": "streamable_http",
      "url": "https://mcp.api-inference.modelscope.net/<your-token>/mcp"
    },
    "local-tools": {
      "type": "stdio",
      "command": "python",
      "args": ["path/to/server.py"],
      "env": {"API_KEY": "..."}
    }
  }
}
```

- `stdio` 配置支持 `command`、`args`、`env` 和可选 `cwd`；`cwd` 相对于 `.mcp.json` 所在目录解析。
- `streamable_http` 配置支持 `url` 和可选 `headers`。
- 工具名称默认保持 MCP Server 返回的原名。当与本地工具或其他 MCP Server 的工具重名时，会自动增加服务器名称前缀，例如 `ServerA__search`，内部维护暴露名称到 `Server + 原始工具名` 的映射。
- 调用 MCP 工具时，JAgent 通过现有的 Function Calling 工具循环转发工具名和参数，并拼接返回的文本内容、结构化数据；`isError` 结果会以明确的错误文本返回。
- 单个 MCP Server 连接失败只会记录错误并跳过该 Server，不影响本地工具和其他 MCP Server。配置错误会输出到标准错误流；连接错误会显示在侧边栏。
- MCP 连接在后台事件循环线程中保持，退出时自动关闭。TUI 首屏先渲染，再异步加载 MCP；加载完成后刷新工具注册表和侧边栏。测试或嵌入场景也可通过 `McpManager` 和 `create_session(..., mcp_manager=...)` 注入自定义配置。

## 上下文压缩与历史检索

当会话变长时，可以在输入框中执行 `/compact` 手动压缩上下文。压缩流程如下：

1. jagent 先把当前完整消息（包含 System Prompt、用户消息、助手回复、工具调用参数和工具结果）保存到项目本地的 `.agents/context/<归档编号>.jsonl`。归档编号使用本地时间生成，例如 `20261022-153000`。
2. 归档保存成功后，使用专门的压缩 Prompt 调用 LLM 生成约 5,000 Tokens 的 Markdown 工作摘要。压缩期间不注册任何工具，也不会继续执行原有任务。
3. 摘要末尾会追加归档编号和 `recallContext` 使用提示，然后用摘要替换当前会话历史，同时保留原 System Prompt 和全部工具定义。
4. 成功后弹出左右两栏的浮动面板，左侧显示压缩前原文，右侧显示压缩结果，支持滚动，可通过关闭按钮或 `Esc` 关闭。
5. 如果压缩失败，原上下文保持不变，可以重新执行 `/compact`。

TUI 顶部会显示当前会话的上下文使用量，例如 `上下文 12.3k / 128.0k · 9.6%`。优先使用模型 API 返回的 Token 使用量，无法获得时按字符数估算。上下文窗口会尝试从本地 LM Studio / Ollama 接口自动探测；无法探测时默认按 128k 处理，并在指示器中标记“默认”。也可以在 `config.ini` 中通过 `[agent] context_window` 显式指定。

当上下文使用量达到配置的警告阈值时，界面会显示警告，并暂停接受普通提示词，直到 `/compact` 成功完成。默认阈值为 60%，可在 `[context] warning_ratio` 中修改。压缩后如果仍超过阈值，可以再次执行 `/compact`。

`recallContext` 是普通的 Function Calling 工具，接收可选参数 `id` 和必需参数 `text`：

- 提供 `id` 时只检索指定归档；省略时检索 `.agents/context/` 下所有归档。
- 使用 Python 本地全文关键词匹配，返回匹配片段、归档编号和消息位置。
- 结果按相关度排序并限制长度，避免检索结果再次占满上下文。

## AGENTS.md 项目指令

如果当前项目根目录存在 `AGENTS.md`，JAgent 会在首次加载会话时读取文件并追加到聊天历史（作为 System Prompt 之后的一条 System 消息）。该消息会写入会话历史，后续轮次直接复用，不会重复注入。路径可通过 `[session] agents_file` 修改。

## 运行

```powershell
cd D:\LLM\agent\jagent
pip install -r requirements.txt
python main.py
```

启动时会先检查 `[llm].base_url`：如果指向本机且端口未监听，会自动使用 `lms`（LM Studio）或 `ollama` 拉起服务，并让 LM Studio 加载 `model` 指定的模型；远程接口不会触发任何本地进程。模型名需与本地已安装模型一致。

界面操作：

- 在输入框中输入消息，按 `Enter` 发送
- 输入 `/` 会弹出命令选择面板，可使用方向键选择并按 `Enter` 执行
- `/new` 新建会话，`/save [名称]` 保存当前会话，`/resume [编号或名称]` 恢复已保存会话
- `/compact` 手动压缩上下文并归档原始记录
- `/clear` 清空当前会话，`/help` 查看命令，`/quit` 退出
- 保存后的会话写入 `[session] directory`（默认 `.agents/sessions/`）；保存前的临时历史写入 `history.json`，该目录已被 `.gitignore` 忽略
- 支持 `Ctrl+V` 粘贴系统剪贴板内容，多行文本会合并为一行
- 也可以点击“发送”按钮
- `Ctrl+Q` 退出

## 配置

JAgent 从**当前工作目录**读取 `config.ini`。如果不存在，首次运行会自动生成一份完整的 Mock 配置（本地 LM Studio 地址、`qwen3.5-4b` 模型），然后弹出提示窗口并退出；请修改后重新启动。

可以参考 `config.example.ini`。主要配置段包括：

- `[llm]`：模型接口地址、模型名、API Key，以及本地服务启动/加载超时
- `[agent]`：临时历史文件、System Prompt、可选的 `context_window`
- `[tools]` / `[search]`：文件读取上限、命令输出上限、网页请求超时、搜索接口和结果数
- `[context]`：默认上下文窗口、压缩阈值、归档目录、归档/摘要限制
- `[mcp]`：MCP 连接、调用和关闭超时
- `[skills]`：Skill 目录和 Frontmatter 读取上限
- `[session]`：已保存会话目录和 `AGENTS.md` 路径
- `[ui]`：侧边栏宽度和工具输出显示长度

```ini
[llm]
base_url = http://127.0.0.1:1234/v1
model = qwen3.5-4b
api_key = DUMMY
start_timeout = 60
load_timeout = 180

[agent]
history_file = history.json
# 可选。留空时自动探测；探测失败按 [context] default_window 处理。
# context_window = 128000
system_prompt = 你是一个本地文件与网络信息助手，可以查询时间、搜索互联网、抓取网页正文、读取和编辑纯文本文件、管理目录。

[search]
baidu_qianfan_api_key = your_baidu_qianfan_api_key

[context]
warning_ratio = 0.6
```

`history_file` 相对于配置文件所在目录解析。未命名会话默认使用 `history.json`；`/save` 后的会话写入 `[session] directory`（默认 `.agents/sessions/`）。`config.ini`、`history.json` 和 `.agents/sessions/` 均已在 `.gitignore` 中忽略，不会提交到仓库。

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

测试覆盖工具注册、文件生命周期、二进制文件拒绝、安全校验、流式工具调用聚合、历史持久化、上下文 Token 估算、归档检索和压缩替换流程。还覆盖配置文件生成与解析、会话保存/恢复、`AGENTS.md` 注入以及 MCP 工具刷新。
