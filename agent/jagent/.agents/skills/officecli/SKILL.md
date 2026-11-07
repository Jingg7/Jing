---
description: 让Agent能够调用本地OfficeCLI工具，读取、创建和修改Word、Excel、PowerPoint文档。支持通过命令行参数执行Office操作任务。
---

# OfficeCLI技能

## 概述

本技能使Agent能够调用本地安装的`officecli-win-x64.exe`程序，实现对Microsoft Word、Excel和PowerPoint文档的自动化操作。该工具基于OpenXML格式处理，无需安装完整的Office软件即可进行文档编辑。

## 功能特性

- **文件读取**: 打开并读取Word (.docx)、Excel (.xlsx)、PowerPoint (.pptx)文档内容
- **文件创建**: 创建新的空白文档或从模板生成文档
- **内容修改**: 替换文本、插入表格、修改样式等
- **批量操作**: 支持对多个文档进行统一处理

## 使用方法

### 基本调用格式

```bash
D:\LLM\office\officecli-win-x64.exe [命令] [参数]
```

### 常用命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `open` | 打开文档 | `open "C:\test.docx"` |
| `create` | 创建新文档 | `create report.docx --template template.docx` |
| `read` | 读取内容 | `read "C:\report.xlsx" -o output.txt` |
| `write` | 写入内容 | `write "C:\data.pptx" --content "<xml>...</xml>"` |
| `modify` | 修改文档 | `modify "C:\doc.docx" --replace-text "旧文本" "新文本"` |

### 参数说明

- `-o`, `--output`: 输出文件路径
- `--template`: 模板文件路径（创建时使用）
- `--content`: XML内容（写入时使用）
- `--replace-text`: 要替换的文本
- `--with-text`: 替换后的新文本

## 参考文档

详细操作说明请参考：`D:\LLM\office\OfficeCli操作说明.md`

## 附件文件

- `officecli-win-x64.exe`: OfficeCLI Windows x64版本可执行文件
  - 路径: `D:\LLM\office\officecli-win-x64.exe`
  - 备用副本: `D:\LLM\agent\jagent\.agents\skills\officecli\officecli-win-x64.exe`
  - 用途: 执行Office文档操作命令

## 注意事项

1. 确保`officecli-win-x64.exe`已正确安装并配置环境变量
2. 处理大型文档时可能需要较长时间
3. 建议先测试小文件再处理重要文档
4. 修改前请备份原始文档

## 示例场景

### 读取Excel数据到文本文件

```bash
D:\LLM\office\officecli-win-x64.exe read "C:\data.xlsx" -o "C:\output.txt"
```

### 创建新Word文档

```bash
D:\LLM\office\officecli-win-x64.exe create "C:\new_report.docx" --template "C:\templates\report_template.docx"
```

### 修改PowerPoint内容

```bash
D:\LLM\office\officecli-win-x64.exe modify "C:\presentation.pptx" --replace-text "旧标题" "新标题"
```

## 错误处理

- 文件不存在: `File not found`
- 权限不足: `Access denied`
- XML格式错误: `Invalid XML format`
- 其他错误: 查看标准输出获取详细信息

---

*本技能基于OfficeCLI工具开发，适用于Windows平台文档自动化处理场景。*
