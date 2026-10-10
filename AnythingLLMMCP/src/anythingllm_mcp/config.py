from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    anythingllm_base_url: str = "http://127.0.0.1:3001"
    anythingllm_api_key: str = ""
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8200
    mcp_path: str = "/mcp"
    request_timeout_s: float = 30.0
    protocol_version: str = "2026-07-28"
    sdk_version: str = "2.0.0"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            anythingllm_base_url=os.getenv(
                "ANYTHINGLLM_BASE_URL", "http://127.0.0.1:3001"
            ).rstrip("/"),
            anythingllm_api_key=os.getenv("ANYTHINGLLM_API_KEY", "").strip(),
            mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
            mcp_port=int(os.getenv("MCP_PORT", "8200")),
            mcp_path=os.getenv("MCP_PATH", "/mcp"),
            request_timeout_s=float(os.getenv("ANYTHINGLLM_TIMEOUT_S", "30")),
        )
