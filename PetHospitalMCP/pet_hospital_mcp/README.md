# pet-hospital-mcp

将现有 Go 宠物医院 REST API（`GET /api/v1/pets`）以 MCP 工具形式暴露给 AI Agent 的 **无状态 Streamable HTTP** MCP 服务。

- 运行时：Python 3.11+（本仓库实测 3.14）
- MCP SDK：官方 `mcp==2.0.0`
- 协议版本：`2026-07-28`
- 服务端实现：SDK 2.x 的 `mcp.server.MCPServer`（**不使用** `FastMCP`，不实现 1.x 会话模型）
- 唯一工具：`list_pets`
- 上游后端：Go 宠物医院服务（唯一业务后端，本服务只通过 HTTP 调用它）

## 一、目录结构

```text
pet_hospital_mcp/
├── pyproject.toml
├── README.md
├── UPGRADE_PROMPT.md
├── src/
│   └── pet_hospital_mcp/
│       ├── __init__.py          # 版本、SDK_VERSION、PROTOCOL_VERSION
│       ├── __main__.py          # python -m pet_hospital_mcp 入口
│       ├── config.py            # 环境变量配置（MCP_HOST/PORT、PET_HOSPITAL_BASE_URL…）
│       ├── server.py            # build_server / create_app / /health
│       ├── rest_client.py       # httpx REST 客户端 + 超时 + 有限重试
│       ├── errors.py            # 统一错误码与 {"error":{...}} 结构
│       ├── logging_config.py    # JSON 行日志 + 敏感字段递归脱敏
│       ├── models.py            # 成功/错误 Pydantic 输出模型
│       └── tools/
│           ├── __init__.py
│           └── list_pets.py     # 输入模型、Schema、工具实现与注册
└── tests/                       # 全部离线（httpx.MockTransport / 本地 mock 后端）
```

## 二、先启动 Go REST API

**Go 服务必须先启动**，MCP 服务不会自己启动它，也不提供兜底数据：

```bash
# Windows（与本仓库同级的 windows 目录）
pethospital.exe -addr 127.0.0.1:8080 -db data/pet.db
```

验证后端可用：

```bash
curl http://127.0.0.1:8080/api/v1/meta
```

## 三、安装与启动 MCP 服务

```bash
cd pet_hospital_mcp
python -m venv .venv                # 已有可跳过
.venv\Scripts\activate              # Windows；macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m pet_hospital_mcp
```

安装后也可直接使用控制台脚本：

```bash
pet-hospital-mcp
```

启动成功会输出 JSON 日志，包含 `mcp_endpoint`、`health_endpoint`、`backend`、`protocolVersion`、`sdk`。

### 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MCP_HOST` | `127.0.0.1` | MCP 监听地址，默认仅本机 |
| `MCP_PORT` | `8000` | MCP 监听端口 |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | Go REST API 地址（末尾 `/` 自动去掉） |
| `PET_HOSPITAL_TIMEOUT` | `10` | 单次上游请求超时（秒） |
| `PET_HOSPITAL_MAX_RETRIES` | `2` | 上游重试次数（0–5，仅连接错误/超时/5xx） |
| `MCP_LOG_LEVEL` | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` |
| `MCP_JSON_RESPONSE` | `true` | Streamable HTTP 返回 JSON（否则 SSE 流） |

示例：换端口并指向另一个后端

```bash
$env:MCP_PORT = "9000"
$env:PET_HOSPITAL_BASE_URL = "http://127.0.0.1:8081"
python -m pet_hospital_mcp
```

## 四、MCP 端点与版本

| 项 | 值 |
| --- | --- |
| MCP 端点 | `http://127.0.0.1:8000/mcp` |
| 健康检查 | `http://127.0.0.1:8000/health` |
| SDK 版本 | `mcp==2.0.0` |
| 协议版本 | `2026-07-28` |
| 传输 | Streamable HTTP，`stateless_http=True`，JSON 响应 |
| 会话 | 无：不实现 `initialize` 握手、不签发/要求 `Mcp-Session-Id`、无会话存储 |

服务发现方式为 2026-07-28 规定的 `server/discover`、`tools/list`、`tools/call`（现代请求需在 `params._meta` 带上
`io.modelcontextprotocol/protocolVersion` 与 `io.modelcontextprotocol/clientCapabilities`，HTTP 头带
`MCP-Protocol-Version`、`Mcp-Method`、`Mcp-Name`，`Accept: application/json, text/event-stream`）。

## 五、验证步骤

### 5.1 健康检查 `/health`

```bash
curl http://127.0.0.1:8000/health
```

```json
{
  "status": "ok",
  "service": "pet-hospital-mcp",
  "version": "0.1.0",
  "protocolVersion": "2026-07-28",
  "sdk": { "name": "mcp", "version": "2.0.0" },
  "transport": "streamable-http",
  "stateless": true,
  "endpoint": "/mcp",
  "backend": "http://127.0.0.1:8080"
}
```

### 5.2 用 MCP Inspector 验证

```bash
npx @modelcontextprotocol/inspector
```

在 Inspector 中选择 **Streamable HTTP**，URL 填 `http://127.0.0.1:8000/mcp`，连接后：

1. `Tools` 列表中出现唯一工具 `list_pets`；
2. 展开工具，可见 14 个参数及枚举/取值约束；
3. 输入 `{"page": 1, "pageSize": 5}` 执行，返回上游 `data`（`items/total/page/pageSize/totalPages/totalCost`）；
4. 输入 `{"page": 0}` 执行，`isError` 为真，内容为统一错误结构。

### 5.3 用 SDK 2.x 客户端验证

```python
import asyncio, json
from mcp.client import Client

async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        print(client.protocol_version)                  # 2026-07-28
        tools = await client.list_tools()               # -> [list_pets]
        ok = await client.call_tool("list_pets", {"page": 1, "pageSize": 3})
        print(ok.is_error, json.loads(ok.content[0].text))
        bad = await client.call_tool("list_pets", {"page": 0})
        print(bad.is_error, bad.content[0].text)

asyncio.run(main())
```

### 5.4 直接发 JSON-RPC（无 initialize、无会话）

```bash
curl -s http://127.0.0.1:8000/mcp \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/call" \
  -H "Mcp-Name: list_pets" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_pets","arguments":{"species":"犬","order":"asc","page":1},"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```

响应中**没有** `Mcp-Session-Id` 头，`result.isError=false` 时 `content[0].text` 与 `structuredContent` 一致。

## 六、`list_pets` 工具说明

上游：`GET {PET_HOSPITAL_BASE_URL}/api/v1/pets`，仅转发以下 14 个查询参数（不新增私有参数）：

`q`、`name`、`ownerName`、`ownerPhone`、`species`、`doctor`、`disease`、`status`、
`min`、`max`、`sortBy`、`order`、`page`、`pageSize`

校验规则（Pydantic 严格模式，`extra="forbid"`，拒绝 NaN/Infinity）：

- `species` ∈ `犬/猫/兔/鸟/仓鼠/爬宠/其他`
- `status` ∈ `待就诊/就诊中/住院中/已康复/慢性病随访`
- `sortBy` ∈ `id,name,ownerName,species,doctor,disease,status,totalCost,visitCount,createdAt,updatedAt`
- `order` ∈ `asc/desc`
- `page >= 1`；`1 <= pageSize <= 500`
- `min >= 0`、`max >= 0`、`min <= max`
- 类型必须精确（`"1"` 不是 `1`），未知字段直接拒绝

### 调用示例

```json
{
  "name": "list_pets",
  "arguments": {
    "species": "犬",
    "status": "待就诊",
    "min": 0,
    "max": 5000,
    "sortBy": "totalCost",
    "order": "desc",
    "page": 1,
    "pageSize": 20
  }
}
```

成功返回（即 Go API 成功响应的 `data`）：

```json
{
  "items": [
    {
      "id": "PET-000180",
      "name": "团团",
      "species": "猫",
      "breed": "狸花",
      "gender": "母",
      "ageMonths": 78,
      "ownerName": "张三",
      "ownerPhone": "13800001111",
      "status": "待就诊",
      "doctor": "李医生",
      "disease": "急性肠胃炎",
      "totalCost": 1055.46,
      "visitCount": 3,
      "records": null,
      "charges": null
    }
  ],
  "total": 47,
  "page": 1,
  "pageSize": 20,
  "totalPages": 3,
  "totalCost": 2110.93
}
```

> `records`、`charges` 可能为 `null` 或数组；`note`、`allergy`、`chipNo` 等字段后端可能省略 —— 本服务按后端原样透传，不凭空补 `null`。

### 失败返回（统一结构）

工具失败时 `isError=true`，`content[0].text` 为：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "查询参数校验失败",
    "details": {
      "issues": [{ "field": "species", "message": "Input should be ...", "type": "literal_error" }]
    }
  }
}
```

错误码：`VALIDATION_ERROR`、`BACKEND_TIMEOUT`、`BACKEND_UNAVAILABLE`、`BACKEND_API_ERROR`（`details.http_status`、`details.upstream_message`）、`BACKEND_INVALID_RESPONSE`、`INTERNAL_ERROR`。HTTPX / Pydantic / SDK 的异常文本与堆栈一律不外泄。

## 七、日志

JSON 行格式，至少包含 `timestamp`、`tool_name`、`params`、`status`、`duration_ms`：

```json
{"timestamp":"2026-10-07T13:26:47.125764+00:00","level":"INFO","logger":"pet_hospital_mcp","tool_name":"list_pets","params":{"sortBy":"totalCost","order":"desc","page":1,"pageSize":3},"status":"success","duration_ms":696.137,"total":1008,"returned_items":3}
```

`ownerPhone`、`ownerAddr`、`chipNo` 及 `owner_phone`、`owner_addr`、`chip_no` 会在写日志前递归脱敏，不记录完整敏感值，不打印堆栈。

## 八、单元测试

```bash
cd pet_hospital_mcp
pytest -q
```

预期结果：**53 passed**（全部离线，不访问真实 Go 服务；HTTP 用例在本地线程内启动 uvicorn + mock 后端）。

覆盖范围：

1. 参数转发（路径与全部 14 个查询参数）与成功输出模型（含 `records/charges = null`、字段省略）；
2. 输入校验失败（枚举、边界、类型、未知字段、`min > max`、NaN/Infinity）；
3. 上游 4xx/5xx → `BACKEND_API_ERROR`；
4. 超时 / 连接异常 → `BACKEND_TIMEOUT` / `BACKEND_UNAVAILABLE`；
5. 非法 JSON、不符合数据模型 → `BACKEND_INVALID_RESPONSE`；
6. 工具注册、工具名、描述与 JSON Schema；
7. 无状态连接流程：`/health`、`server/discover`、`tools/list`、`tools/call` 不发旧 `initialize`、不要求/返回 `Mcp-Session-Id`、协议 `2026-07-28`；
8. 日志脱敏与错误结构不含内部实现细节。

## 九、阶段说明

本次**仅实现阶段一工具 `list_pets`，未实现阶段二工具**；新增工具的约定见 `UPGRADE_PROMPT.md`。
