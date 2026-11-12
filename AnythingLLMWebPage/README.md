# AnythingLLM WebPage

一个单页工具，用于把本地文件上传到 AnythingLLM 并加入工作区向量化。它**直接调用 AnythingLLM 的 Developer REST API**，不经过 MCP Server，适合在浏览器里手工验证 AnythingLLM 的文档上传流程。

页面只有一个入口文件 [`index.html`](index.html)，无需构建、无需 Node.js。

## 功能

- 自动读取 AnythingLLM 中的第一个工作区
- 多选本地文件并上传到 `POST /api/v1/document/upload`
- 通过 `addToWorkspaces` 把文档直接加入工作区并触发向量化
- 在页面上逐条显示成功/失败结果

## 环境依赖与版本约束

| 项目 | 要求 |
| --- | --- |
| 浏览器 | 支持 `fetch`、`FormData` 的现代浏览器（Chrome / Edge / Firefox） |
| AnythingLLM | 桌面版或 Docker 单用户版，REST API 默认 `http://localhost:3001` |
| 网络 | 页面需要能访问 AnythingLLM；建议通过本机 HTTP 服务打开，避免 `file://` 的跨域限制 |

AnythingLLM 必须先启动，并至少创建一个工作区、完成聊天模型配置。

## 配置与启动

### 1. 获取 AnythingLLM API Key

1. 打开并登录本机 AnythingLLM。
2. 进入 **Settings（设置）→ Tools（工具）→ Developer API**。
3. 点击 **Generate API Key / Create API Key**，复制密钥。
4. 可在 `http://localhost:3001/api/docs` 查看当前实例的完整接口文档。

### 2. 写入配置

```powershell
cd D:\LLM\AnythingLLMWebPage
Copy-Item config.example.js config.js
notepad config.js
```

把 `apiKey` 改成真实密钥：

```js
window.ANYTHINGLLM_CONFIG = {
  apiBase: 'http://localhost:3001',
  apiKey: 'your-anythingllm-api-key'
};
```

> 真实密钥不要写进 `index.html`，也不要提交到仓库。`config.js` 已被 [`.gitignore`](.gitignore) 忽略；模板见 [`config.example.js`](config.example.js)。

### 3. 启动页面

推荐用本机静态服务器打开，避免浏览器对 `file://` 页面的跨域限制：

```powershell
cd D:\LLM\AnythingLLMWebPage
python -m http.server 5500
```

然后浏览器访问 <http://localhost:5500/>。

也可以直接双击 `index.html`；如果浏览器拦截了对 `http://localhost:3001` 的请求，请改用上面的 HTTP 服务方式。

## 验证方式

### 1. 用 curl 验证 AnythingLLM

```powershell
curl.exe -H "Authorization: Bearer <your-api-key>" http://localhost:3001/api/v1/auth
```

预期：

```json
{"authenticated":true}
```

列出工作区：

```powershell
curl.exe -H "Authorization: Bearer <your-api-key>" http://localhost:3001/api/v1/workspaces
```

### 2. 用 curl 验证文档上传

```powershell
curl.exe -X POST http://localhost:3001/api/v1/document/upload `
  -H "Authorization: Bearer <your-api-key>" `
  -F "file=@D:\path\to\file.md" `
  -F "addToWorkspaces=<slug>"
```

成功时返回 `{"success":true,"documents":[...]}`，其中 `documents[].location` 可用于后续的 `update-embeddings`。

### 3. 浏览器操作

1. 打开 <http://localhost:5500/>。
2. 页面顶部应显示第一个工作区的名称和 `slug`。
3. 选择文件，点击“上传并嵌入”。
4. 日志出现 `完成: <文件名> -> <location>` 即表示上传并加入工作区成功。
5. 回到 AnythingLLM 工作区，确认文档列表和向量计数已更新。

## 失败场景

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 页面显示 `未配置 API Key` | 没有创建 `config.js` 或 `apiKey` 为空 | 复制 `config.example.js` 为 `config.js` 并填入真实 Key |
| 顶部显示 `获取失败: HTTP 401 ...` | Key 错误、被撤销或复制时带了空格 | 重新生成 Key，确认 `config.js` 中没有多余引号或空格 |
| `获取失败: Failed to fetch` / `NetworkError` | AnythingLLM 未启动、端口不对，或 `file://` 跨域被拦截 | 启动 AnythingLLM；用 `python -m http.server 5500` 打开页面 |
| `获取失败: 没有工作区` | AnythingLLM 中还没有工作区 | 在 AnythingLLM 界面创建一个工作区 |
| 上传返回 `success:false` | 文件类型不支持、文件过大或上游错误 | 查看页面日志中的 `error` 字段；换用受支持的文本/PDF/DOCX 文件 |
| 上传成功但工作区看不到文档 | 未传 `addToWorkspaces` 或工作区 `slug` 为空 | 确认页面顶部已加载工作区；必要时改用 MCP 的 `upload_document`/`update_workspace_embeddings` |
| 日志一直停在“上传中” | AnythingLLM 正在解析/嵌入大文件，或模型服务超时 | 等待完成；检查 AnythingLLM 日志和嵌入模型配置 |
| 浏览器控制台报 CORS | 页面与 API 不同源，且实例未允许跨域 | 用 `http.server` 打开页面仍失败时，改用 AnythingLLMMCP 或直接 curl |

## 相关文件

- [`index.html`](index.html)：页面与上传逻辑
- [`config.example.js`](config.example.js)：配置模板
- [`../AnythingLLMMCP/`](../AnythingLLMMCP/)：把同一套 AnythingLLM 能力暴露为 MCP 工具
- [`.gitignore`](.gitignore)：忽略本地 `config.js`
