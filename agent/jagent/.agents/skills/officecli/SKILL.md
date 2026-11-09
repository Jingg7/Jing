---
name: officecli
description: 调用本地 officecli 可执行文件创建、读取和修改 Word(.docx)、Excel(.xlsx)、PowerPoint(.pptx) 文档，无需安装 Office。
---

# OfficeCLI 技能

用本技能通过 `RunCli` 工具调用本地 `officecli-win-x64.exe` 生成/编辑 Office 文档。

## 可执行文件

- 推荐（已验证可用）：`D:\LLM\agent\jagent\.agents\skills\officecli\officecli-win-x64.exe`
- 备用：`D:\LLM\office\officecli-win-x64.exe`（较新构建，当前可能在启动时因缺少 `System.IO.Pipelines` 崩溃，优先用上面的副本）

`RunCli` 的 `command` 传 exe 路径，`args` 传参数数组。例如：

```
command: D:\LLM\agent\jagent\.agents\skills\officecli\officecli-win-x64.exe
args: ["create", "D:\\LLM\\agent\\jagent\\presentations\\demo.pptx"]
```

## 帮助优先（重要）

不确定属性名、取值格式或命令语法时，先查帮助，不要猜：

- `officecli help` — 全部命令
- `officecli help docx` / `officecli help pptx` / `officecli help xlsx`
- `officecli help docx paragraph` — 某元素的完整 schema
- `officecli help pptx shape`
- `officecli help docx set paragraph` — 只列 `set` 可用的属性

格式别名：`word`→`docx`，`excel`→`xlsx`，`ppt`/`powerpoint`→`pptx`。

## 策略层次

**L1 读取 → L2 DOM 编辑 → L3 原始 XML**，总是先用更高层。加 `--json` 得到结构化输出。

## 快速开始

### 创建 PowerPoint

```
officecli create slides.pptx
officecli add slides.pptx / --type slide --prop title="Q4 Report" --prop background=1A1A2E
officecli add slides.pptx '/slide[1]' --type shape --prop text="Revenue grew 25%" --prop x=2cm --prop y=5cm --prop font=Arial --prop size=24 --prop color=FFFFFF
```

### 创建 Word

```
officecli create report.docx
officecli add report.docx /body --type paragraph --prop text="Executive Summary" --prop style=Heading1
officecli add report.docx /body --type paragraph --prop text="Revenue increased by 25% year-over-year."
```

### 创建 Excel

```
officecli create data.xlsx
officecli set data.xlsx /Sheet1/A1 --prop value="Name" --prop bold=true
officecli set data.xlsx /Sheet1/A2 --prop value="Alice"
```

## 读取与检查（L1）

```
officecli view <file> <mode>        # outline | stats | issues | text | annotated | html | screenshot | svg | pdf
officecli get <file> <path> --depth N [--json]
officecli query <file> <selector>   # CSS-like，如 paragraph[style=Normal]、shape[fill=FF0000]
officecli validate <file>
```

`view outline` 看结构，`view text` 提取纯文本，`view issues` 查格式/内容问题。

## DOM 编辑（L2）

```
officecli set <file> <path> --prop key=value [--prop ...]
officecli add <file> <parent> --type <type> [--after|--before <path>] [--prop ...]
officecli add <file> <parent> --from <path>     # 克隆现有元素
officecli move <file> <path> [--to <parent>] [--index N|--after|--before <path>]
officecli swap <file> <path1> <path2>
officecli remove <file> <path>
```

- 任意 XML 属性都可通过元素路径用 `set` 修改。
- 值格式：颜色 `FF0000`/`#FF0000`/`red`/`rgb(255,0,0)`/`accent1`；间距 `12pt`/`0.5cm`/`1.5x`/`150%`；尺寸 `2.54cm`/`1in`/`72pt`/`96px`。
- 点号别名：`--prop font.color=red --prop font.bold=true --prop font.size=14pt`。

### 查找替换文本

```
officecli set doc.docx / --find draft --replace final
officecli set doc.docx '/body/p[1]' --find weather --prop bold=true --prop color=red
```

路径 `/` = 全文；`/body/p[1]`、`/slide[N]/shape[M]` = 指定元素。默认区分大小写，忽略大小写加 `--prop 'find=(?i)error' --prop regex=true`。

### batch 批量（一次保存周期）

```
officecli batch data.xlsx --commands '[{"op":"set","path":"/Sheet1/A1","props":{"value":"Done"}}]' --json
```

默认原子：任一失败整批回滚。想保留成功项加 `--best-effort`。

## 原始 XML（L3）

L2 无法表达时使用：

```
officecli raw <file> <part>
officecli raw-set <file> <part> --xpath "..." --action replace --xml '<w:p>...</w:p>'
```

## 路径约定

- 路径 **1-based**：`'/body/p[3]'` = 第 3 段。
- `--index` **0-based**（Excel 的 `add --type row|col` 例外，为 1-based）。
- PowerShell 中带 `[N]` 的路径必须加引号：`'/slide[1]'`。
- 优先使用稳定 ID 路径，如 `/slide[1]/shape[@id=550950021]`、`/body/p[@paraId=1A2B3C4D]`。

## 修改后验证

```
officecli validate <file>
officecli view <file> issues
```

## 常见错误

| 错误写法 | 正确做法 |
|---------|---------|
| `--name "foo"` | 用 `--prop name="foo"` |
| 未加引号的 `[N]` 路径 | `'/slide[1]'` 加引号 |
| 用 `read`/`write`/`modify` | 真实命令是 `create`/`add`/`set`/`view`/`query`/`get` |
| 猜属性名 | 先 `officecli help <format> <element>` |
| PPT 用 `shape[1]` 当正文 | `shape[1]` 通常是标题占位符，内容用 `shape[2]+` |

## 专用子技能

`officecli load_skill <name>` 会输出 SKILL.md，按其中规则执行（每个文档只加载一个）：

- Word：`word`（报告/信函/通用）、`academic-paper`（论文）
- PowerPoint：`pptx`（通用）、`pitch-deck`（融资）、`morph-ppt`（Morph 动画）、`morph-ppt-3d`
- Excel：`excel`（通用）、`financial-model`（财务模型）、`data-dashboard`（数据看板）

## 输出目录

生成的文件建议放在工作目录下，如 `D:\LLM\agent\jagent\presentations\`（PPT）或与其他文档同级位置。
