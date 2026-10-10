from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration for the MCP adapter."""

    pet_hospital_base_url: str = "http://127.0.0.1:8080"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8100
    request_timeout_s: float = 10.0
    max_retries: int = 2
    retry_backoff_s: float = 0.2
    mcp_path: str = "/mcp"
    protocol_version: str = "2026-07-28"
    sdk_version: str = "2.0.0"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            pet_hospital_base_url=os.getenv(
                "PET_HOSPITAL_BASE_URL", "http://127.0.0.1:8080"
            ).rstrip("/"),
            mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
            mcp_port=_env_int("MCP_PORT", 8100),
            request_timeout_s=_env_float("PET_HOSPITAL_TIMEOUT_S", 10.0),
            max_retries=_env_int("PET_HOSPITAL_MAX_RETRIES", 2),
            retry_backoff_s=_env_float("PET_HOSPITAL_RETRY_BACKOFF_S", 0.2),
            mcp_path=os.getenv("MCP_PATH", "/mcp"),
        )
