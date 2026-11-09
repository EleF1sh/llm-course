"""MCP Client：读取项目根 `.mcp.json`，连接 Server，并把工具注册进 Function Calling。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# OpenAI function name：字母数字 / _ / -
_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_token(name: str) -> str:
    token = _SAFE_RE.sub("_", (name or "").strip()).strip("_")
    if not token:
        token = "mcp"
    if token[0].isdigit():
        token = f"mcp_{token}"
    return token


def _config_path(project_root: Path | None = None) -> Path:
    return (project_root or PROJECT_ROOT) / ".mcp.json"


def load_mcp_config(project_root: Path | None = None) -> dict[str, Any]:
    """读取 `{project_root}/.mcp.json`。不存在则返回空配置。"""
    path = _config_path(project_root)
    if not path.is_file():
        return {"mcpServers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法解析 MCP 配置 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"MCP 配置必须是 JSON 对象: {path}")
    servers = data.get("mcpServers") or data.get("servers") or {}
    if not isinstance(servers, dict):
        raise ValueError(f"mcpServers 必须是对象: {path}")
    return {"mcpServers": servers, "path": str(path)}


def _normalize_transport(entry: dict[str, Any]) -> str:
    raw = (
        entry.get("type")
        or entry.get("transport")
        or entry.get("serverType")
        or ""
    )
    raw = str(raw).strip().lower().replace("-", "_")
    if raw in {"streamable_http", "streamablehttp", "http", "sse"}:
        # sse 单独分支；无 type 时有 url 再判
        if raw == "sse":
            return "sse"
        return "streamable_http"
    if raw in {"stdio", "std_io", "standard_io"}:
        return "stdio"
    if entry.get("url"):
        return "streamable_http"
    if entry.get("command"):
        return "stdio"
    raise ValueError("无法识别传输类型（需要 type/transport，或 url/command）")


def _schema_to_parameters(input_schema: Any) -> dict[str, Any]:
    if isinstance(input_schema, dict):
        params = dict(input_schema)
    elif hasattr(input_schema, "model_dump"):
        params = input_schema.model_dump(by_alias=True, exclude_none=True)
    else:
        params = {"type": "object", "properties": {}}
    params.pop("$schema", None)
    if "type" not in params:
        params["type"] = "object"
    if "properties" not in params:
        params["properties"] = {}
    return params


def _format_exc(exc: BaseException) -> str:
    """展开 ExceptionGroup，便于日志阅读。"""
    if isinstance(exc, BaseExceptionGroup):
        parts = [_format_exc(e) for e in exc.exceptions]
        return f"{exc.__class__.__name__}: " + " | ".join(parts)
    return f"{exc.__class__.__name__}: {exc}"


def _format_call_result(result: Any) -> str:
    """把 MCP CallToolResult 转成 Agent 统一的 JSON 字符串。"""
    is_error = bool(getattr(result, "is_error", False))
    texts: list[str] = []
    structured = getattr(result, "structured_content", None)
    content = getattr(result, "content", None) or []
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "text" or hasattr(block, "text"):
            texts.append(str(getattr(block, "text", "")))
        else:
            if hasattr(block, "model_dump"):
                texts.append(json.dumps(block.model_dump(), ensure_ascii=False))
            else:
                texts.append(str(block))
    payload: dict[str, Any] = {
        "ok": not is_error,
        "source": "mcp",
        "text": "\n".join(t for t in texts if t),
        "content": texts,
    }
    if structured is not None:
        payload["structured"] = structured
    if is_error:
        payload["error"] = payload["text"] or "MCP tool returned isError=true"
    return json.dumps(payload, ensure_ascii=False)


class _LoopThread:
    """在后台线程跑常驻 asyncio 事件循环，供同步 Agent 调用。"""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run, name="xagent-mcp-loop", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise RuntimeError("MCP 事件循环启动超时")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self.loop = loop
        asyncio.set_event_loop(loop)
        self._ready.set()
        loop.run_forever()
        try:
            loop.close()
        except Exception:
            pass
        self.loop = None

    def run(self, coro: Any, timeout: float = 120.0) -> Any:
        if not self.loop:
            raise RuntimeError("MCP 事件循环未启动")
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result(timeout=timeout)

    def stop(self) -> None:
        loop = self.loop
        thread = self._thread
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            thread.join(timeout=8)
        self._thread = None
        self.loop = None


class McpManager:
    """管理多个 MCP Server 连接与工具映射。"""

    def __init__(self) -> None:
        self._loop = _LoopThread()
        self._exit_stack: contextlib.AsyncExitStack | None = None
        self._sessions: dict[str, Any] = {}
        # exposed_name -> (server_name, original_tool_name)
        self._tool_map: dict[str, tuple[str, str]] = {}
        self._openai_tools: list[dict[str, Any]] = []
        self._status: list[str] = []
        self._started = False
        self._lock = threading.Lock()

    @property
    def started(self) -> bool:
        return self._started

    @property
    def status_messages(self) -> list[str]:
        return list(self._status)

    @property
    def openai_tools(self) -> list[dict[str, Any]]:
        return list(self._openai_tools)

    def is_mcp_tool(self, name: str) -> bool:
        return name in self._tool_map

    def server_snapshot(self) -> list[dict[str, Any]]:
        """供侧栏展示：已连接 Server 及其暴露工具名。"""
        by_server: dict[str, list[dict[str, str]]] = {}
        for exposed, (server, original) in self._tool_map.items():
            by_server.setdefault(server, []).append(
                {"exposed": exposed, "original": original}
            )
        # 已连接但无工具的 server
        for name in self._sessions:
            by_server.setdefault(name, [])
        out: list[dict[str, Any]] = []
        for name, tools in by_server.items():
            out.append(
                {
                    "name": name,
                    "connected": name in self._sessions,
                    "tools": tools,
                }
            )
        out.sort(key=lambda x: str(x["name"]).lower())
        return out

    def start(self, project_root: Path | None = None) -> list[str]:
        """读取配置并连接；单 Server 失败不影响其他。可重复调用（已启动则跳过）。"""
        with self._lock:
            if self._started:
                return self.status_messages
            self._status = []
            try:
                cfg = load_mcp_config(project_root)
            except ValueError as exc:
                self._status.append(f"MCP 配置错误: {exc}")
                self._started = True
                return self.status_messages

            servers: dict[str, Any] = cfg.get("mcpServers") or {}
            path = cfg.get("path") or str(_config_path(project_root))
            if not servers:
                self._status.append(f"未找到 MCP Server（{path}）")
                self._started = True
                return self.status_messages

            self._loop.start()
            try:
                messages = self._loop.run(
                    self._async_start(servers), timeout=180.0
                )
            except Exception as exc:
                self._status.append(f"MCP 启动失败: {exc}")
                logger.exception("MCP start failed")
                self._started = True
                return self.status_messages

            self._status.extend(messages)
            self._started = True
            return self.status_messages

    async def _async_start(self, servers: dict[str, Any]) -> list[str]:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        messages: list[str] = []
        self._exit_stack = contextlib.AsyncExitStack()
        await self._exit_stack.__aenter__()

        discovered: dict[str, list[Any]] = {}

        for server_name, entry in servers.items():
            if not isinstance(entry, dict):
                messages.append(f"MCP [{server_name}] 配置无效（需要对象），已跳过")
                continue
            # 每个 Server 独立 ExitStack：失败时只关闭自己，不影响其它连接
            server_stack = contextlib.AsyncExitStack()
            try:
                await server_stack.__aenter__()
                transport = _normalize_transport(entry)
                session = await self._open_session(
                    entry,
                    transport,
                    exit_stack=server_stack,
                    ClientSession=ClientSession,
                    stdio_client=stdio_client,
                    StdioServerParameters=StdioServerParameters,
                    streamable_http_client=streamable_http_client,
                    create_mcp_http_client=create_mcp_http_client,
                )
                await session.initialize()
                listed = await session.list_tools()
                tools = list(listed.tools or [])
                # 成功后再挂到总栈，保证失败 Server 的资源已在下方 aclose
                await self._exit_stack.enter_async_context(server_stack)
                self._sessions[server_name] = session
                discovered[server_name] = tools
                messages.append(
                    f"MCP [{server_name}] 已连接（{transport}），工具 {len(tools)} 个"
                )
            except BaseException as exc:
                with contextlib.suppress(BaseException):
                    await server_stack.aclose()
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                err = _format_exc(exc)
                messages.append(f"MCP [{server_name}] 连接失败: {err}")
                logger.warning("MCP server %s failed: %s", server_name, err)

        self._register_tools(discovered)
        return messages

    async def _open_session(
        self,
        entry: dict[str, Any],
        transport: str,
        *,
        exit_stack: contextlib.AsyncExitStack,
        ClientSession: Any,
        stdio_client: Any,
        StdioServerParameters: Any,
        streamable_http_client: Any,
        create_mcp_http_client: Any,
    ) -> Any:
        if transport == "stdio":
            command = entry.get("command")
            if not command:
                raise ValueError("stdio 需要 command")
            args = entry.get("args") or []
            if not isinstance(args, list):
                raise ValueError("args 必须是数组")
            env_cfg = entry.get("env")
            env = None
            if isinstance(env_cfg, dict):
                env = {**os.environ, **{str(k): str(v) for k, v in env_cfg.items()}}
            cwd = entry.get("cwd")
            params = StdioServerParameters(
                command=str(command),
                args=[str(a) for a in args],
                env=env,
                cwd=str(cwd) if cwd else None,
            )
            read, write = await exit_stack.enter_async_context(stdio_client(params))
        elif transport == "streamable_http":
            url = entry.get("url")
            if not url:
                raise ValueError("streamable_http 需要 url")
            headers = entry.get("headers")
            timeout = float(entry.get("timeout", 30))
            sse_read_timeout = float(
                entry.get("sse_read_timeout", entry.get("read_timeout", 300))
            )
            http_client = None
            if headers or timeout:
                import httpx2

                http_client = create_mcp_http_client(
                    headers=headers if isinstance(headers, dict) else None,
                    timeout=httpx2.Timeout(timeout, read=sse_read_timeout),
                )
                await exit_stack.enter_async_context(http_client)
            streams = await exit_stack.enter_async_context(
                streamable_http_client(
                    str(url),
                    http_client=http_client,
                    terminate_on_close=bool(entry.get("terminate_on_close", True)),
                )
            )
            read, write = streams[0], streams[1]
        else:
            raise ValueError(f"暂不支持的传输类型: {transport}")

        session = await exit_stack.enter_async_context(ClientSession(read, write))
        return session

    def _register_tools(self, discovered: dict[str, list[Any]]) -> None:
        from core.schemas import LOCAL_TOOLS

        local_names = {t["function"]["name"] for t in LOCAL_TOOLS}
        # 原始名 -> 出现次数（跨 server）
        raw_counts: dict[str, int] = {}
        for tools in discovered.values():
            for tool in tools:
                raw_counts[tool.name] = raw_counts.get(tool.name, 0) + 1

        used: set[str] = set(local_names)
        self._tool_map.clear()
        self._openai_tools.clear()

        for server_name, tools in discovered.items():
            server_token = _safe_token(server_name)
            for tool in tools:
                original = tool.name
                need_prefix = (
                    original in local_names
                    or raw_counts.get(original, 0) > 1
                    or original in used
                )
                if need_prefix:
                    exposed = f"{server_token}__{original}"
                else:
                    exposed = original
                # 极端情况下仍冲突则再加序号
                base = exposed
                n = 2
                while exposed in used:
                    exposed = f"{base}_{n}"
                    n += 1
                used.add(exposed)
                self._tool_map[exposed] = (server_name, original)

                desc = (tool.description or "").strip() or f"MCP tool {original}"
                if need_prefix:
                    desc = f"[MCP:{server_name}] {desc}"
                params = _schema_to_parameters(
                    getattr(tool, "input_schema", None)
                    or getattr(tool, "inputSchema", None)
                )
                self._openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": exposed,
                            "description": desc,
                            "parameters": params,
                        },
                    }
                )

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        mapping = self._tool_map.get(name)
        if not mapping:
            return json.dumps(
                {"ok": False, "error": f"unknown MCP tool: {name}"},
                ensure_ascii=False,
            )
        server_name, original = mapping
        session = self._sessions.get(server_name)
        if session is None:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"MCP Server 未连接: {server_name}",
                    "tool": name,
                },
                ensure_ascii=False,
            )
        try:
            result = self._loop.run(
                session.call_tool(original, arguments or {}),
                timeout=180.0,
            )
            return _format_call_result(result)
        except Exception as exc:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"MCP 调用失败 [{server_name}/{original}]: {exc}",
                    "tool": name,
                },
                ensure_ascii=False,
            )

    def shutdown(self) -> None:
        with self._lock:
            if not self._started and self._exit_stack is None:
                self._loop.stop()
                return

            async def _close() -> None:
                if self._exit_stack is not None:
                    with contextlib.suppress(Exception):
                        await self._exit_stack.aclose()
                    self._exit_stack = None

            try:
                if self._loop.loop and self._loop.loop.is_running():
                    self._loop.run(_close(), timeout=30.0)
            except Exception as exc:
                logger.warning("MCP shutdown error: %s", exc)
            finally:
                self._sessions.clear()
                self._tool_map.clear()
                self._openai_tools.clear()
                self._started = False
                self._loop.stop()


_MANAGER: McpManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_mcp_manager() -> McpManager:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = McpManager()
        return _MANAGER


def start_mcp(project_root: Path | None = None) -> list[str]:
    return get_mcp_manager().start(project_root)


def start_mcp_async(
    project_root: Path | None = None,
    on_done: Any | None = None,
    *,
    force_reload: bool = False,
) -> None:
    """后台线程连接 MCP；完成后回调 on_done(messages, snapshot)。"""

    def _worker() -> None:
        msgs: list[str] = []
        try:
            if force_reload:
                shutdown_mcp()
            msgs = start_mcp(project_root)
        except Exception as exc:
            msgs = [f"MCP 启动失败: {exc}"]
        snap = []
        try:
            snap = get_mcp_manager().server_snapshot()
        except Exception:
            snap = []
        if on_done:
            try:
                on_done(msgs, snap)
            except Exception:
                logger.exception("MCP async on_done failed")

    threading.Thread(target=_worker, name="xagent-mcp-start", daemon=True).start()


def mcp_server_snapshot() -> list[dict[str, Any]]:
    return get_mcp_manager().server_snapshot()


def shutdown_mcp() -> None:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is not None:
            _MANAGER.shutdown()
            _MANAGER = None


def get_mcp_tools() -> list[dict[str, Any]]:
    mgr = get_mcp_manager()
    if not mgr.started:
        return []
    return mgr.openai_tools


def is_mcp_tool(name: str) -> bool:
    return get_mcp_manager().is_mcp_tool(name)


def call_mcp_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
    return get_mcp_manager().call_tool(name, arguments)


def reload_mcp(project_root: Path | None = None) -> list[str]:
    """关闭现有连接后按最新 `.mcp.json` 重新连接。"""
    root = (project_root or PROJECT_ROOT).resolve()
    shutdown_mcp()
    return start_mcp(root)


def _parse_config_payload(raw: Any) -> dict[str, Any]:
    """接受 JSON 字符串或对象，归一成 mcpServers 映射。"""
    data: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("configJson 为空")
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("配置必须是 JSON 对象")
    if "mcpServers" in data:
        servers = data["mcpServers"]
    elif "servers" in data:
        servers = data["servers"]
    else:
        # 整份就是 server 映射，或单个 server（需配合 serverName）
        servers = data
    if not isinstance(servers, dict):
        raise ValueError("mcpServers 必须是对象")
    return servers


def create_mcp_config(
    *,
    config_json: str | dict[str, Any] | None = None,
    server_name: str | None = None,
    server_type: str | None = None,
    url: str | None = None,
    command: str | None = None,
    args: list[Any] | None = None,
    merge: bool = True,
    reload: bool = True,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """把用户提供的 MCP 配置写入项目根 `.mcp.json`，可选立即重连。"""
    root = (project_root or PROJECT_ROOT).resolve()
    path = root / ".mcp.json"

    existing: dict[str, Any] = {"mcpServers": {}}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                servers = loaded.get("mcpServers") or loaded.get("servers") or {}
                if isinstance(servers, dict):
                    existing = {"mcpServers": dict(servers)}
        except (OSError, json.JSONDecodeError):
            existing = {"mcpServers": {}}

    incoming: dict[str, Any] = {}
    if config_json is not None:
        # 保留原始结构：若顶层已有 mcpServers，_parse 已取出映射
        raw_obj: Any = config_json
        if isinstance(config_json, str):
            raw_obj = json.loads(config_json.strip())
        parsed = _parse_config_payload(config_json)
        top_had_servers = isinstance(raw_obj, dict) and (
            "mcpServers" in raw_obj or "servers" in raw_obj
        )
        single_keys = {"url", "command", "type", "transport", "args", "env", "headers"}
        is_single_entry = (not top_had_servers) and any(
            k in parsed for k in ("url", "command")
        ) and not all(isinstance(v, dict) for v in parsed.values())
        # 例如 {"type":"streamable_http","url":"..."} → 单 Server
        # 例如 {"Bazi-MCP":{...},"pet":{...}} → 映射
        if is_single_entry or (
            not top_had_servers
            and any(k in parsed for k in single_keys)
            and not all(isinstance(v, dict) for v in parsed.values())
        ):
            if not server_name:
                raise ValueError("写入单个 Server 时需要 serverName")
            incoming = {server_name: dict(parsed)}
        else:
            incoming = dict(parsed)

    if not incoming and server_name:
        entry: dict[str, Any] = {}
        if server_type:
            entry["type"] = server_type
        if url:
            entry["url"] = url
            entry.setdefault("type", server_type or "streamable_http")
        if command:
            entry["command"] = command
            entry.setdefault("type", server_type or "stdio")
        if args is not None:
            entry["args"] = list(args)
        if not entry.get("url") and not entry.get("command"):
            raise ValueError("请提供 url（HTTP）或 command（stdio）")
        incoming = {server_name: entry}

    if not incoming:
        raise ValueError("请提供 configJson，或 serverName + url/command")

    # 校验每个 entry 至少能识别传输
    for name, entry in incoming.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Server [{name}] 配置必须是对象")
        _normalize_transport(entry)

    if merge:
        merged = dict(existing.get("mcpServers") or {})
        merged.update(incoming)
    else:
        merged = dict(incoming)

    payload = {"mcpServers": merged}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    reload_msgs: list[str] = []
    if reload:
        reload_msgs = reload_mcp(root)

    return {
        "ok": True,
        "path": str(path),
        "merged": merge,
        "reloaded": reload,
        "servers": list(merged.keys()),
        "wrote": list(incoming.keys()),
        "reload_status": reload_msgs,
    }
