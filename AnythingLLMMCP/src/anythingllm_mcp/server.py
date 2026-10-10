from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from anythingllm_mcp import __version__
from anythingllm_mcp.client import AnythingLLMClient, AnythingLLMError
from anythingllm_mcp.config import Settings


def _err(code: str, message: str, details: dict[str, Any] | None = None) -> CallToolResult:
    payload = {"error": {"code": code, "message": message, "details": details or {}}}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structured_content=payload,
        is_error=True,
    )


def _ok(data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
        structured_content=data,
        is_error=False,
    )


def create_server(settings: Settings | None = None) -> MCPServer:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
        client = AnythingLLMClient(settings)
        try:
            yield {"client": client, "settings": settings}
        finally:
            await client.aclose()

    mcp = MCPServer(
        name="anythingllm-mcp",
        title="AnythingLLM MCP",
        description="MCP adapter for local AnythingLLM. Stage tool: list_first_workspace_files.",
        version=__version__,
        lifespan=lifespan,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> Response:
        return JSONResponse(
            {
                "status": "healthy",
                "service": "anythingllm-mcp",
                "version": __version__,
                "sdk": f"mcp=={settings.sdk_version}",
                "protocol": settings.protocol_version,
                "server": "MCPServer",
                "transport": "streamable-http",
                "dual_protocol": True,
                "anythingllm_base_url": settings.anythingllm_base_url,
                "api_key_configured": bool(settings.anythingllm_api_key),
                "tools": ["list_first_workspace_files"],
            }
        )

    @mcp.tool(
        name="list_first_workspace_files",
        title="List first workspace files",
        description=(
            "List file/document information from the first AnythingLLM workspace. "
            "Requires ANYTHINGLLM_API_KEY and a running local AnythingLLM instance."
        ),
        structured_output=True,
    )
    async def list_first_workspace_files(ctx: Context = None) -> CallToolResult:  # type: ignore[assignment]
        client: AnythingLLMClient | None = None
        owned = False
        if ctx is not None:
            try:
                life = ctx.request_context.lifespan_context
                if isinstance(life, dict):
                    client = life.get("client")
            except Exception:
                client = None
        if client is None:
            client = AnythingLLMClient(settings)
            owned = True
        try:
            data = await client.first_workspace_files()
            return _ok(data)
        except AnythingLLMError as exc:
            return _err(exc.code, exc.message, exc.details)
        except Exception as exc:
            return _err("INTERNAL_ERROR", "Unexpected error", {"reason": type(exc).__name__})
        finally:
            if owned and client is not None:
                await client.aclose()

    return mcp


def create_http_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()
    mcp = create_server(settings)
    # Dual protocol: handshake versions use stateful path; 2026-07-28 uses modern path.
    return mcp.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        json_response=True,
        stateless_http=False,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
        host=settings.mcp_host,
    )


async def serve(settings: Settings | None = None) -> None:
    import uvicorn

    settings = settings or Settings.from_env()
    app = create_http_app(settings)
    config = uvicorn.Config(app, host=settings.mcp_host, port=settings.mcp_port, log_level="info")
    await uvicorn.Server(config).serve()
