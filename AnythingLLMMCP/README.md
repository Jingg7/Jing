# AnythingLLM MCP Server

把本机 [AnythingLLM](https://anythingllm.com/) 的 REST API 包装成 **Streamable HTTP MCP Server**，让 JAgent 等 MCP 客户端可以用自然语言查询工作区、上传文档、更新向量化并向工作区提问。

本目录只有一个入口文件 [`server.py`](server.py)，基于官方 `mcp` SDK 2.x 的 `MCPServer`，不依赖 `requests`、FastAPI 或其他 Web 框架。

## 工具一览

| 类别 | 工具 | 上游 API | 说明 |
| --- | --- | --- | --- |
| 工作区 | `first_workspace_files` | `GET /v1/workspaces`、`GET /v1/workspace/{slug}` | 列出第一个工作区及其文档 |
| 对话 | `chat_workspace` | `POST /v1/workspace/{slug}/chat` | 提问并返回 `textResponse` 与引用来源 |
| 文档 | `upload_document` | `POST /v1/document/upload` | 上传本地文件，可通过 `addToWorkspaces` 直接加入工作区 |
| 文档 | `update_workspace_embeddings` | `POST /v1/workspace/{slug}/update-embeddings` | 用 upload 返回的 `location` 加入或移除向量化文档 |

`slug` 参数留空时默认使用 AnythingLLM 中的第一个工作区。

## 环境依赖与版本约束

| 项目 | 要求 |
| --- | --- |
| Python | **3.11+**（本仓库在 Python 3.14.4 上实测） |
| MCP SDK | `mcp>=2.0.0`（本仓库在 `mcp==2.2.0` 上实测） |
| AnythingLLM | 桌面版或 Docker 单用户版，REST API 默认监听 `http://localhost:3001` |
| 第三方包 | 仅 `mcp`；HTTP 请求使用 Python 标准库 `urllib` |

AnythingLLM 必须先启动，并在其中完成模型配置、创建至少一个工作区。

## 安装与启动

```powershell
cd D:\LLM\AnythingLLMMCP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 复制配置模板并填入真实 API Key
Copy-Item .env.example .env
notepad .env

python server.py
```

`server.py` 会自动读取同目录下的 `.env`，且不会覆盖外部已经设置的环境变量。

也可以不创建 `.env`，直接设置环境变量：

```powershell
$env:ANYTHINGLLM_API_KEY = "your-anythingllm-api-key"
$env:ANYTHINGLLM_BASE_URL = "http://localhost:3001/api"
$env:MCP_PORT = "8001"
python server.py
```

启动成功后 MCP 端点为 `http://127.0.0.1:8001/mcp`。日志会打印在终端；按 `Ctrl+C` 退出。

### 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ANYTHINGLLM_BASE_URL` | `http://localhost:3001/api` | AnythingLLM REST API 根地址，末尾 `/` 会自动去掉 |
| `ANYTHINGLLM_API_KEY` | 无，**必填** | AnythingLLM Developer API Key |
| `ANYTHINGLLM_TIMEOUT` | `30` | 单次上游请求超时（秒） |
| `MCP_HOST` | `127.0.0.1` | MCP 监听地址 |
| `MCP_PORT` | `8001` | MCP 监听端口；与 PetHospitalMCP 同时运行时要错开 |

> 真实密钥不要写进代码，也不要提交到仓库。本目录的 `.env` 已被 `.gitignore` 忽略，配置模板见 [`.env.example`](.env.example)。

## 如何获取 AnythingLLM API Key

1. 打开并登录本机 AnythingLLM。
2. 进入 **Settings（设置）→ Tools（工具）→ Developer API**。
3. 点击 **Generate API Key / Create API Key**，复制生成的密钥。
4. 把密钥写入 `.env` 的 `ANYTHINGLLM_API_KEY`，或按上面的方式设置为环境变量。
5. 打开 `http://localhost:3001/api/docs` 可以查看当前实例的 Swagger 接口文档。

API Key 拥有该 AnythingLLM 实例的完整控制权限，请勿截图、分享或提交到 Git。

## 验证方式

### 1. 先验证 AnythingLLM 本身

```powershell
curl.exe -H "Authorization: Bearer $env:ANYTHINGLLM_API_KEY" http://localhost:3001/api/v1/auth
```

预期返回：

```json
{"authenticated":true}
```

列出工作区，记下返回的 `slug`：

```powershell
curl.exe -H "Authorization: Bearer $env:ANYTHINGLLM_API_KEY" http://localhost:3001/api/v1/workspaces
```

### 2. 直接向 AnythingLLM 提问

```powershell
curl.exe -X POST http://localhost:3001/api/v1/workspace/<slug>/chat `
  -H "Authorization: Bearer $env:ANYTHINGLLM_API_KEY" `
  -H "Content-Type: application/json" `
  -d "{\"message\":\"这个工作区里有哪些文档？\",\"mode\":\"query\"}"
```

回答在 `textResponse` 字段，引用在 `sources` 字段。

### 3. 验证 MCP Server

推荐使用 MCP Inspector：

```powershell
npx @modelcontextprotocol/inspector
```

在 Inspector 中选择 **Streamable HTTP**，URL 填 `http://127.0.0.1:8001/mcp`，连接后应能看到 4 个工具。也可以直接用 JSON-RPC 请求：

```bash
curl -s http://127.0.0.1:8001/mcp \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/list" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```

调用对话工具：

```bash
curl -s http://127.0.0.1:8001/mcp \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/call" \
  -H "Mcp-Name: chat_workspace" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"chat_workspace","arguments":{"message":"总结第一个工作区的文档","mode":"query"},"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```

### 4. 接入 JAgent

在 JAgent 的 `.mcp.json` 中加入：

```json
{
  "mcpServers": {
    "AnythingLLMMCP": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

启动 JAgent 后，侧边栏出现 `AnythingLLMMCP` 和上述 4 个工具即表示连接成功。

## 失败场景

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 启动时打印 `配置错误：缺少环境变量 ANYTHINGLLM_API_KEY` 并退出码 2 | 没有设置 API Key | 按上文设置 `ANYTHINGLLM_API_KEY`，或创建 `.env` |
| `HTTP 401` / `{"error":"Invalid API Key"}` | Key 错误、被删除或实例重启后失效 | 到 Settings → Tools → Developer API 重新生成 |
| `无法连接 AnythingLLM (...) [WinError 10061]` | AnythingLLM 未启动，或 `ANYTHINGLLM_BASE_URL`/端口不对 | 先启动 AnythingLLM；默认端口是 `3001` |
| `HTTP 404` 且提示工作区不存在 | `slug` 写错 | 用 `GET /v1/workspaces` 查看真实 `slug`，或留空使用第一个工作区 |
| 对话返回 `HTTP 500` | AnythingLLM 没有配置聊天模型，或模型服务不可用 | 在 AnythingLLM 设置中完成模型配置并测试聊天 |
| 上传成功但工作区文档列表为空 | 只上传到了文档库，没有 `addToWorkspaces` | 调用 `upload_document` 时传 `slug`，或用 `update_workspace_embeddings` 的 `adds` |
| MCP 端口被占用 | 与 PetHospitalMCP 默认端口冲突 | 设置 `MCP_PORT=8001` 或其他空闲端口 |
| JAgent 看不到工具 | URL 写错、服务未启动、`.mcp.json` 不是合法 JSON | 先用 Inspector 验证 MCP 端点，再检查 `.mcp.json` |

## 相关文件

- [`server.py`](server.py)：MCP Server 与全部工具实现
- [`.env.example`](.env.example)：环境变量模板
- [`requirements.txt`](requirements.txt)：MCP SDK 依赖
- [`../AnythingLLMWebPage/`](../AnythingLLMWebPage/)：浏览器版文档上传工具（直接调用 AnythingLLM REST，不经过 MCP）
