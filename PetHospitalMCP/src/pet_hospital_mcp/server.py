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

from pet_hospital_mcp import __version__
from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.errors import ErrorEnvelope
from pet_hospital_mcp.logging_config import setup_logging
from pet_hospital_mcp.rest_client import PetHospitalClient
from pet_hospital_mcp.tools.list_pets import (
    LIST_PETS_DESCRIPTION,
    ListPetsOutput,
    run_list_pets,
)

logger = setup_logging()


def _result_to_call_tool(result: ListPetsOutput | ErrorEnvelope) -> CallToolResult:
    payload = result.model_dump(mode="json")
    is_error = isinstance(result, ErrorEnvelope)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structured_content=payload,
        is_error=is_error,
    )


def _collect_raw_args(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def create_server(settings: Settings | None = None) -> MCPServer:
    """Build an MCPServer with the stage-1 list_pets tool and /health route."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
        client = PetHospitalClient(settings)
        try:
            yield {"settings": settings, "client": client}
        finally:
            await client.aclose()

    mcp = MCPServer(
        name="pet-hospital-mcp",
        title="Pet Hospital MCP",
        description=(
            "Stateless Streamable HTTP MCP adapter for the Pet Hospital Go REST API. "
            "Stage 1 exposes only list_pets."
        ),
        version=__version__,
        instructions=(
            "Call list_pets to query pets from the Go backend. "
            "Stage-2 tools are intentionally not implemented."
        ),
        lifespan=lifespan,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(_request: Request) -> Response:
        return JSONResponse(
            {
                "status": "healthy",
                "service": "pet-hospital-mcp",
                "version": __version__,
                "sdk": f"mcp=={settings.sdk_version}",
                "protocol": settings.protocol_version,
                "server": "MCPServer",
                "transport": "streamable-http",
                "dual_protocol": True, "stateless_http": False,
                "pet_hospital_base_url": settings.pet_hospital_base_url,
                "tools": ["list_pets"],
            }
        )

    @mcp.tool(
        name="list_pets",
        title="List pets",
        description=LIST_PETS_DESCRIPTION,
        structured_output=True,
    )
    async def list_pets(
        q: str | None = None,
        name: str | None = None,
        ownerName: str | None = None,
        ownerPhone: str | None = None,
        species: str | None = None,
        doctor: str | None = None,
        disease: str | None = None,
        status: str | None = None,
        min: float | None = None,
        max: float | None = None,
        sortBy: str | None = None,
        order: str | None = None,
        page: int | None = None,
        pageSize: int | None = None,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> CallToolResult:
        raw = _collect_raw_args(
            q=q,
            name=name,
            ownerName=ownerName,
            ownerPhone=ownerPhone,
            species=species,
            doctor=doctor,
            disease=disease,
            status=status,
            min=min,
            max=max,
            sortBy=sortBy,
            order=order,
            page=page,
            pageSize=pageSize,
        )

        client: PetHospitalClient | None = None
        if ctx is not None:
            lifespan_ctx = ctx.request_context.lifespan_context
            if isinstance(lifespan_ctx, dict):
                client = lifespan_ctx.get("client")

        owned = False
        if client is None:
            client = PetHospitalClient(settings)
            owned = True
        try:
            result = await run_list_pets(client, raw)
            return _result_to_call_tool(result)
        finally:
            if owned:
                await client.aclose()

    return mcp


def create_http_app(settings: Settings | None = None) -> Starlette:
    """Assemble the Starlette app for stateless Streamable HTTP + /health."""
    settings = settings or Settings.from_env()
    mcp = create_server(settings)
    app = mcp.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        json_response=True,
        stateless_http=False,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
        host=settings.mcp_host,
    )
    app.state.settings = settings  # type: ignore[attr-defined]
    app.state.mcp = mcp  # type: ignore[attr-defined]
    return app


async def serve(settings: Settings | None = None) -> None:
    """Run the MCP HTTP server (binds to MCP_HOST/MCP_PORT)."""
    import uvicorn

    settings = settings or Settings.from_env()
    app = create_http_app(settings)
    logger.info(
        "starting pet-hospital-mcp",
        extra={
            "tool_name": "-",
            "params": {
                "host": settings.mcp_host,
                "port": settings.mcp_port,
                "mcp_path": settings.mcp_path,
                "pet_hospital_base_url": settings.pet_hospital_base_url,
            },
            "status": "starting",
            "duration_ms": 0,
        },
    )
    config = uvicorn.Config(
        app,
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


