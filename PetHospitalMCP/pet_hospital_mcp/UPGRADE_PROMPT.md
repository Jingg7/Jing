# UPGRADE_PROMPT.md —— 阶段二新增工具时给 AI 的提示词

> 本次交付**只实现 `list_pets`**，未实现阶段二工具。后续在此基础上新增工具时，把本文件整体交给 AI，
> 并同时提供新工具对应的 Go REST API 文档（README 中的路径、参数、成功/错误响应示例）。

---

## 背景（勿删，AI 必须遵守）

本仓库 `pet_hospital_mcp/` 是一个**已完工、已通过测试**的 MCP 服务，硬约束如下：

1. 技术栈固定：Python 3.11+、官方 SDK `mcp==2.0.0`、协议 `2026-07-28`、`mcp.server.MCPServer`、
   无状态 Streamable HTTP（`stateless_http=True`）。**禁止**使用/导入 `mcp.server.fastmcp.FastMCP`，
   **禁止**实现 `initialize` 握手、`Mcp-Session-Id`、会话存储、会话过期、有状态 SSE 恢复。
2. 服务是独立进程，唯一业务后端是 Go 宠物医院 REST API，只能通过 `PET_HOSPITAL_BASE_URL` 走 HTTP 调用；
   不得修改 Go 服务，不得在 Python 侧造业务数据。
3. 现有约定必须复用，不要另起一套：
   - `rest_client.py`：`PetHospitalClient` 负责超时、有限重试（仅 connect/timeout/5xx，退避 `_RETRY_BACKOFF_SECONDS`）、
     Go 成功信封 `{"code":200,...,"data":...}` 与 Go 错误体 `{"code":4xx/5xx,"message":...}` 的解析；
   - `errors.py`：所有失败都抛 `MCPToolError`，最终渲染为
     `{"error":{"code","message","details"}}`，错误码只能取 `ERROR_CODES` 中的值
     （`VALIDATION_ERROR`/`BACKEND_TIMEOUT`/`BACKEND_UNAVAILABLE`/`BACKEND_API_ERROR`/`BACKEND_INVALID_RESPONSE`/`INTERNAL_ERROR`）；
   - `logging_config.py`：JSON 行日志，字段 `timestamp/tool_name/params/status/duration_ms`，
     `ownerPhone/ownerAddr/chipNo`（含 snake_case）写入前递归脱敏，禁止堆栈外泄；
   - `models.py`：成功/错误输出的 Pydantic 模型。
4. 工具注册必须沿用 `tools/list_pets.py` 的三件套模式：
   - `ListPetsInput`：Pydantic 严格模型（`extra="forbid"`、`strict=True`、`allow_inf_nan=False`）做全部校验；
   - `input_schema()`：导出给 MCP 的 JSON Schema（SDK 层不做业务校验，只靠它做提示）；
   - `register(server)`：`server.add_tool(fn, name=..., description=..., structured_output=False)`，
     工具函数直接返回 `CallToolResult`（成功：`content` JSON + `structured_content`；
     失败：`is_error=True` + 统一错误 JSON）。**必须**保持 `structured_output=False`，
     否则 SDK 会用输出模型校验 `structured_content` 并抛错。
   - 参数注解用 `Annotated[Any, WithJsonSchema(_PROPERTIES[name])]`，避免 SDK 层 Pydantic 校验文本泄漏到客户端。
5. 未知字段检测依赖 `ctx.request_context.params["arguments"]`（`Context.request_context` 缺省会抛 `ValueError`，
   已有 try/except 保护）。
6. 测试必须离线：`httpx.MockTransport` 或本地线程内 uvicorn + mock 后端，**禁止**访问真实 Go 服务；
   运行命令固定为 `cd pet_hospital_mcp && pytest -q`，当前为 **53 passed**，新增工具后必须仍然全绿。

## 你要做的任务

在**不破坏上述任何约定**的前提下，新增阶段二工具：

1. 新建 `src/pet_hospital_mcp/tools/<tool_name>.py`，按 `list_pets.py` 的结构写：
   输入模型（严格校验、枚举用真实后端允许值）→ `input_schema()` → 工具函数（调 `PetHospitalClient`
   的新方法，成功/失败都返回 `CallToolResult`）→ `register(server)`。
2. 在 `src/pet_hospital_mcp/rest_client.py` 中新增对应的 HTTP 方法（复用现有超时、重试、信封解析、
   错误映射；若新接口是写操作，说明清楚幂等性与重试边界）。
3. 在 `src/pet_hospital_mcp/server.py` 的 `build_server()` 中调用新工具的 `register(server)`；
   工具描述必须说明用途、参数、适用场景和返回值。
4. `README.md`：更新工具列表、参数表、调用示例、错误示例、测试预期结果；`__init__.py` 保持
   `SDK_VERSION`/`PROTOCOL_VERSION` 不变。
5. `tests/`：为新工具补三类用例 —— 成功（参数转发 + 输出模型）、输入校验失败、上游 4xx/5xx/超时/
   非法响应；再补一条 HTTP 无状态流程用例（`server/discover` → `tools/list` → `tools/call`，
   断言无 `Mcp-Session-Id`）。
6. 运行 `cd pet_hospital_mcp && pytest -q`，全绿才算完成；最后按「最终交付」格式输出
   目录结构、修改文件列表、测试结果、启动与验证方式。

## 明确禁止

- 不得引入新依赖（除非后端确实需要，并在 `pyproject.toml` 固定版本并说明理由）；
- 不得修改 `errors.py` 的错误结构与错误码语义；
- 不得在日志/错误信息中输出堆栈、HTTPX/Pydantic/SDK 内部文本；
- 不得实现认证、权限、CORS（教学场景不需要）；
- 不得一次交付多个未验证的改动，逐工具提交并跑测试。
