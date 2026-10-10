from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.server import create_http_app, create_server
from helpers import list_payload

PROTOCOL = "2026-07-28"
PROTOCOL_META_KEY = "io.modelcontextprotocol/protocolVersion"
CAPS_META_KEY = "io.modelcontextprotocol/clientCapabilities"
INFO_META_KEY = "io.modelcontextprotocol/clientInfo"


def _modern_body(method: str, params: dict[str, Any] | None = None, req_id: int = 1) -> dict[str, Any]:
    body_params = dict(params or {})
    body_params["_meta"] = {
        PROTOCOL_META_KEY: PROTOCOL,
        CAPS_META_KEY: {},
        INFO_META_KEY: {"name": "pytest-client", "version": "0.0.1"},
    }
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": body_params,
    }


def _modern_headers(method: str, name: str | None = None) -> dict[str, str]:
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
        "mcp-protocol-version": PROTOCOL,
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    return headers


@pytest.fixture
def app_settings() -> Settings:
    return Settings(
        pet_hospital_base_url="http://pet-hospital.test",
        mcp_host="127.0.0.1",
        mcp_port=8100,
        request_timeout_s=1.0,
        max_retries=0,
        retry_backoff_s=0.01,
    )


@pytest.mark.asyncio
async def test_tool_registration_name_and_schema(app_settings: Settings) -> None:
    server = create_server(app_settings)
    tools = await server.list_tools()
    assert [t.name for t in tools] == ["list_pets"]
    tool = tools[0]
    schema = tool.input_schema
    assert schema["type"] == "object"
    props = schema.get("properties", {})
    for key in (
        "q",
        "name",
        "ownerName",
        "ownerPhone",
        "species",
        "doctor",
        "disease",
        "status",
        "min",
        "max",
        "sortBy",
        "order",
        "page",
        "pageSize",
    ):
        assert key in props
    assert "ctx" not in props


@pytest.mark.asyncio
async def test_health_and_stateless_mcp_flow(app_settings: Settings) -> None:
    app = create_http_app(app_settings)

    with respx.mock:
        respx.get("http://pet-hospital.test/api/v1/pets").mock(
            return_value=httpx.Response(200, json=list_payload())
        )

        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                health = await client.get("/health")
                assert health.status_code == 200
                body = health.json()
                assert body["status"] == "healthy"
                assert body["protocol"] == PROTOCOL
                assert body["server"] == "MCPServer"
                assert body["tools"] == ["list_pets"]

                # Stateless modern request: no initialize, no Mcp-Session-Id.
                list_headers = _modern_headers("tools/list")
                assert "mcp-session-id" not in {k.lower() for k in list_headers}
                listed = await client.post(
                    "/mcp",
                    headers=list_headers,
                    json=_modern_body("tools/list", {}),
                )
                assert listed.status_code == 200
                assert "mcp-session-id" not in {k.lower() for k in listed.headers}
                listed_json = listed.json()
                assert "error" not in listed_json
                tool_names = [t["name"] for t in listed_json["result"]["tools"]]
                assert tool_names == ["list_pets"]

                # Ensure clients are not required to send initialize.
                init = await client.post(
                    "/mcp",
                    headers=_modern_headers("initialize"),
                    json=_modern_body(
                        "initialize",
                        {
                            "protocolVersion": PROTOCOL,
                            "capabilities": {},
                            "clientInfo": {"name": "pytest", "version": "0"},
                        },
                    ),
                )
                # initialize is not part of the modern single-exchange workflow.
                assert init.status_code in (400, 404, 405) or "error" in init.json()

                called = await client.post(
                    "/mcp",
                    headers=_modern_headers("tools/call", name="list_pets"),
                    json=_modern_body(
                        "tools/call",
                        {
                            "name": "list_pets",
                            "arguments": {"page": 1, "pageSize": 5, "species": "犬"},
                        },
                    ),
                )
                assert called.status_code == 200
                assert "mcp-session-id" not in {k.lower() for k in called.headers}
                payload = called.json()
                assert "error" not in payload
                result = payload["result"]
                assert result.get("isError") is False
                structured = result.get("structuredContent") or json.loads(
                    result["content"][0]["text"]
                )
                assert structured["total"] == 1
                assert structured["items"][0]["name"] == "旺财"


@pytest.mark.asyncio
async def test_logging_redacts_sensitive_fields() -> None:
    from pet_hospital_mcp.logging_config import redact

    redacted = redact(
        {
            "ownerPhone": "13800001111",
            "owner_phone": "13900002222",
            "ownerAddr": "秘密地址",
            "chipNo": "CHIP-9",
            "nested": {"ownerPhone": "13700003333", "ok": "visible"},
            "note": "call 13600004444 please",
        }
    )
    assert redacted["ownerPhone"] == "***REDACTED***"
    assert redacted["owner_phone"] == "***REDACTED***"
    assert redacted["ownerAddr"] == "***REDACTED***"
    assert redacted["chipNo"] == "***REDACTED***"
    assert redacted["nested"]["ownerPhone"] == "***REDACTED***"
    assert redacted["nested"]["ok"] == "visible"
    assert "***REDACTED***" in redacted["note"]
