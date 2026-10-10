# Pet Hospital MCP（阶段一）

将现有 **Go 宠物医院 REST API** 的查询能力，通过 **MCP SDK 2.x (`MCPServer`)** 以无状态 Streamable HTTP 暴露给 AI Agent。

| 项 | 值 |
| --- | --- |
| SDK | `mcp==2.0.0` |
| 协议 | `2026-07-28` |
| 服务器类 | `MCPServer` |
| 传输 | Streamable HTTP（`stateless_http=True`） |
| 本次工具 | 仅 `list_pets`（**未实现阶段二**） |

## 前置条件

1. 先启动 Go 宠物医院服务（默认 `http://127.0.0.1:8080`）  
   可用仓库旁的 Windows 发布包：

   ```powershell
   cd D:\LLM-Course\pet-hospital\windows
   .\pethospital.exe
   ```

2. Python 3.11+

## 安装

```powershell
cd D:\LLM-Course\pet-hospital\pet-hospital-mcp
python -m pip install -e ".[dev]"
```

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | Go REST API 地址 |
| `MCP_HOST` | `127.0.0.1` | MCP 监听地址（教学场景仅本机） |
| `MCP_PORT` | `8100` | MCP 端口 |
| `MCP_PATH` | `/mcp` | Streamable HTTP 端点路径 |

## 启动 MCP

```powershell
cd D:\LLM-Course\pet-hospital\pet-hospital-mcp
python -m pet_hospital_mcp
```

或：

```powershell
$env:MCP_HOST="127.0.0.1"
$env:MCP_PORT="8100"
$env:PET_HOSPITAL_BASE_URL="http://127.0.0.1:8080"
python -m pet_hospital_mcp
```

## 端点

- 健康检查：`GET http://127.0.0.1:8100/health`
- MCP：`POST http://127.0.0.1:8100/mcp`（无状态；不使用旧 `initialize` / `Mcp-Session-Id`）

### `/health` 示例

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health
```

预期包含：`status=healthy`、`sdk=mcp==2.0.0`、`protocol=2026-07-28`、`server=MCPServer`、`tools=["list_pets"]`。

### `list_pets` 调用示例（MCP Inspector / HTTP）

在 MCP Inspector 中：

1. Transport 选择 Streamable HTTP
2. URL：`http://127.0.0.1:8100/mcp`
3. 协议版本：`2026-07-28`
4. 发现工具应看到 `list_pets`
5. 调用参数示例：

```json
{
  "species": "犬",
  "page": 1,
  "pageSize": 5,
  "sortBy": "totalCost",
  "order": "desc"
}
```

成功时 `structuredContent` 对应 Go API 的 `data`：

```json
{
  "items": [ ... ],
  "total": 1,
  "page": 1,
  "pageSize": 5,
  "totalPages": 1,
  "totalCost": 380.0
}
```

## 单元测试

测试使用 mock，**不会访问真实 Go 服务**。

```bash
cd pet-hospital-mcp
pytest -q
```

在本仓库路径下：

```powershell
cd D:\LLM-Course\pet-hospital\pet-hospital-mcp
pytest -q
```

预期：全部通过。

## 设计说明

- 不修改 Go 后端；MCP 仅通过 HTTP 调用 `GET /api/v1/pets`
- 使用 Pydantic 严格校验输入；`species` / `status` / `sortBy` / `order` 与后端允许值对齐
- 统一错误结构：`VALIDATION_ERROR` / `BACKEND_*` / `INTERNAL_ERROR`
- 日志对 `ownerPhone` / `ownerAddr` / `chipNo` 递归脱敏
- **明确声明：未实现阶段二工具（创建/更新/删除等）**

## Э��
�����¾�Э�飺Streamable HTTP�����ְ� + 2026-07-28 �ִ���״̬·������

