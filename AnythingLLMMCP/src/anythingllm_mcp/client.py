from __future__ import annotations

from typing import Any

import httpx

from anythingllm_mcp.config import Settings


class AnythingLLMError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class AnythingLLMClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._owns = client is None
        headers = {}
        if settings.anythingllm_api_key:
            headers["Authorization"] = f"Bearer {settings.anythingllm_api_key}"
        self._client = client or httpx.AsyncClient(
            base_url=f"{settings.anythingllm_base_url}/api",
            headers=headers,
            timeout=settings.request_timeout_s,
        )

    async def aclose(self) -> None:
        if self._owns:
            await self._client.aclose()

    async def _get(self, path: str) -> Any:
        if not self.settings.anythingllm_api_key:
            raise AnythingLLMError(
                "CONFIG_ERROR",
                "ANYTHINGLLM_API_KEY is not set. Create a key in AnythingLLM settings.",
            )
        try:
            resp = await self._client.get(path)
        except httpx.TimeoutException as exc:
            raise AnythingLLMError("BACKEND_TIMEOUT", "AnythingLLM request timed out") from exc
        except httpx.RequestError as exc:
            raise AnythingLLMError(
                "BACKEND_UNAVAILABLE",
                "AnythingLLM is unavailable. Is it running on the configured base URL?",
            ) from exc
        if resp.status_code in (401, 403):
            raise AnythingLLMError(
                "AUTH_ERROR",
                "AnythingLLM rejected the API key",
                {"status_code": resp.status_code},
            )
        if resp.status_code >= 400:
            raise AnythingLLMError(
                "BACKEND_API_ERROR",
                "AnythingLLM API error",
                {"status_code": resp.status_code, "body": resp.text[:500]},
            )
        return resp.json()

    async def list_workspaces(self) -> list[dict[str, Any]]:
        data = await self._get("/v1/workspaces")
        if isinstance(data, dict):
            workspaces = data.get("workspaces") or data.get("data") or []
        elif isinstance(data, list):
            workspaces = data
        else:
            workspaces = []
        if not isinstance(workspaces, list):
            raise AnythingLLMError("BACKEND_INVALID_RESPONSE", "Unexpected workspaces payload")
        return workspaces

    async def list_workspace_documents(self, slug: str) -> Any:
        return await self._get(f"/v1/workspace/{slug}/documents")

    async def first_workspace_files(self) -> dict[str, Any]:
        workspaces = await self.list_workspaces()
        if not workspaces:
            return {
                "workspace": None,
                "files": [],
                "message": "No workspace found. Create one in AnythingLLM first.",
            }
        ws = workspaces[0]
        slug = ws.get("slug") or ws.get("id") or ws.get("name")
        if not slug:
            raise AnythingLLMError("BACKEND_INVALID_RESPONSE", "First workspace missing slug")
        docs = await self.list_workspace_documents(str(slug))
        files = _normalize_documents(docs)
        return {
            "workspace": {
                "name": ws.get("name"),
                "slug": slug,
                "id": ws.get("id"),
            },
            "files": files,
            "count": len(files),
        }


def _normalize_documents(docs: Any) -> list[dict[str, Any]]:
    """Flatten common AnythingLLM document payload shapes into a file list."""
    items: list[Any]
    if isinstance(docs, dict):
        items = (
            docs.get("documents")
            or docs.get("localFiles")
            or docs.get("items")
            or docs.get("data")
            or []
        )
        # some versions nest under localFiles.items
        if isinstance(items, dict):
            items = items.get("items") or items.get("files") or []
    elif isinstance(docs, list):
        items = docs
    else:
        items = []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # folder nodes may contain nested items
        nested = item.get("items") or item.get("documents")
        if isinstance(nested, list):
            out.extend(_normalize_documents(nested))
            continue
        out.append(
            {
                "id": item.get("id") or item.get("docId") or item.get("uuid"),
                "name": item.get("name")
                or item.get("title")
                or item.get("filename")
                or item.get("docpath"),
                "type": item.get("type") or item.get("chunkSource") or item.get("mime"),
                "path": item.get("docpath") or item.get("path") or item.get("location"),
                "wordCount": item.get("wordCount") or item.get("token_count_estimate"),
                "cached": item.get("cached"),
                "raw": {
                    k: item.get(k)
                    for k in ("id", "name", "title", "filename", "docpath", "type", "url")
                    if k in item
                },
            }
        )
    return out
