# AnythingLLM MCP

本地 AnythingLLM 的 MCP 适配器（Python / `MCPServer` / Streamable HTTP，兼容新旧协议）。

## 工具

- `list_first_workspace_files`：读取**第一个工作区**的文件/文档信息

## 准备

1. 启动 AnythingLLM Desktop  
2. 打开设置 → API Keys，创建一把 Key  
3. 复制 `.env.example` 为 `.env` 并填写：

```env
ANYTHINGLLM_BASE_URL=http://127.0.0.1:3001
ANYTHINGLLM_API_KEY=你的key
MCP_HOST=127.0.0.1
MCP_PORT=8200
```

## 安装与启动

```powershell
cd D:\LLM-Course\AnythingLLMMCP
python -m pip install -e .
python -m anythingllm_mcp
```

- Health: http://127.0.0.1:8200/health  
- MCP: http://127.0.0.1:8200/mcp  

API 文档参考：http://localhost:3001/api/docs/
