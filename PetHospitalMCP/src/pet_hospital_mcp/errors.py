from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "BACKEND_TIMEOUT",
    "BACKEND_UNAVAILABLE",
    "BACKEND_API_ERROR",
    "BACKEND_INVALID_RESPONSE",
    "INTERNAL_ERROR",
]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Unified structured error returned to MCP clients."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class AdapterError(Exception):
    """Domain error that maps to the unified MCP error envelope."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorBody(code=self.code, message=self.message, details=self.details)
        )


def validation_error(message: str, details: dict[str, Any] | None = None) -> AdapterError:
    return AdapterError("VALIDATION_ERROR", message, details=details)


def internal_error(message: str, details: dict[str, Any] | None = None) -> AdapterError:
    return AdapterError("INTERNAL_ERROR", message, details=details)
