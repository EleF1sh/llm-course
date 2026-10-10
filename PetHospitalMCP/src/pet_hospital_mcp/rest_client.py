from __future__ import annotations

import asyncio
from typing import Any

import httpx

from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.errors import AdapterError


class PetHospitalClient:
    """Thin HTTP client for the Go Pet Hospital REST API."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.pet_hospital_base_url,
            timeout=settings.request_timeout_s,
            transport=transport,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def list_pets(self, params: dict[str, Any]) -> dict[str, Any]:
        """Call GET /api/v1/pets and return the response `data` object."""
        query = {k: v for k, v in params.items() if v is not None}
        last_error: Exception | None = None
        attempts = self._settings.max_retries + 1

        for attempt in range(attempts):
            try:
                response = await self._client.get("/api/v1/pets", params=query)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise AdapterError(
                        "BACKEND_TIMEOUT",
                        "Timed out while calling the Pet Hospital API",
                        details={"path": "/api/v1/pets", "attempts": attempts},
                    ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise AdapterError(
                        "BACKEND_UNAVAILABLE",
                        "Pet Hospital API is unavailable",
                        details={"path": "/api/v1/pets", "attempts": attempts},
                    ) from exc
            else:
                if response.status_code >= 500:
                    if attempt + 1 < attempts:
                        await asyncio.sleep(self._settings.retry_backoff_s * (attempt + 1))
                        continue
                    raise AdapterError(
                        "BACKEND_API_ERROR",
                        "Pet Hospital API returned a server error",
                        details={
                            "status_code": response.status_code,
                            "body": _safe_text(response),
                        },
                    )
                if response.status_code >= 400:
                    raise AdapterError(
                        "BACKEND_API_ERROR",
                        "Pet Hospital API returned an error response",
                        details={
                            "status_code": response.status_code,
                            "body": _safe_text(response),
                        },
                    )
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise AdapterError(
                        "BACKEND_INVALID_RESPONSE",
                        "Pet Hospital API returned non-JSON content",
                        details={"status_code": response.status_code},
                    ) from exc

                if not isinstance(payload, dict) or "data" not in payload:
                    raise AdapterError(
                        "BACKEND_INVALID_RESPONSE",
                        "Pet Hospital API response is missing the data field",
                        details={"payload_type": type(payload).__name__},
                    )
                data = payload["data"]
                if not isinstance(data, dict):
                    raise AdapterError(
                        "BACKEND_INVALID_RESPONSE",
                        "Pet Hospital API data field must be an object",
                        details={"data_type": type(data).__name__},
                    )
                return data

            await asyncio.sleep(self._settings.retry_backoff_s * (attempt + 1))

        raise AdapterError(
            "BACKEND_UNAVAILABLE",
            "Pet Hospital API is unavailable",
            details={"path": "/api/v1/pets", "reason": str(last_error)},
        )


def _safe_text(response: httpx.Response, limit: int = 500) -> str:
    text = response.text
    if len(text) > limit:
        return text[:limit] + "…"
    return text
