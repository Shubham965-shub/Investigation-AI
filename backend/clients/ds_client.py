"""Thin async HTTP client for the InvestigationAi_DS service.

All LLM/search/critique work is delegated to InvestigationAi_DS over HTTP;
this module owns the shared httpx client and translates upstream failures
into FastAPI HTTPExceptions the routers can let propagate.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import HTTPException, status

from backend.config.settings import settings

_client: Optional[httpx.AsyncClient] = None


def create_client() -> httpx.AsyncClient:
    global _client
    _client = httpx.AsyncClient(
        base_url=settings.DS_SERVICE_BASE_URL,
        timeout=settings.DS_SERVICE_TIMEOUT_SECONDS,
    )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("DS client not initialised — app lifespan did not run")
    return _client


def _raise_for_upstream_error(exc: httpx.HTTPStatusError) -> None:
    """Forward the DS service's status code and error body to the caller."""
    try:
        detail: Any = exc.response.json().get("detail", exc.response.text)
    except ValueError:
        detail = exc.response.text
    raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc


async def ds_post(path: str, json: Optional[dict] = None, **kwargs: Any) -> Any:
    client = get_client()
    try:
        response = await client.post(path, json=json, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InvestigationAi_DS service unreachable: {exc}",
        ) from exc


async def ds_get(path: str, params: Optional[dict] = None, **kwargs: Any) -> Any:
    client = get_client()
    try:
        response = await client.get(path, params=params, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InvestigationAi_DS service unreachable: {exc}",
        ) from exc
