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

# Short connect timeout so a genuinely down ds still fails fast; read/write/pool
# get much more room since real ds calls (critique, scoring, generation) can
# legitimately run long — see config/settings.py for where these are sourced.
HEAVY_DS_TIMEOUT = httpx.Timeout(
    connect=settings.DS_SERVICE_CONNECT_TIMEOUT_SECONDS,
    read=settings.DS_SERVICE_HEAVY_READ_TIMEOUT_SECONDS,
    write=settings.DS_SERVICE_HEAVY_READ_TIMEOUT_SECONDS,
    pool=settings.DS_SERVICE_HEAVY_READ_TIMEOUT_SECONDS,
)


def create_client() -> httpx.AsyncClient:
    global _client
    _client = httpx.AsyncClient(
        base_url=settings.DS_SERVICE_BASE_URL,
        timeout=httpx.Timeout(
            connect=settings.DS_SERVICE_CONNECT_TIMEOUT_SECONDS,
            read=settings.DS_SERVICE_READ_TIMEOUT_SECONDS,
            write=settings.DS_SERVICE_READ_TIMEOUT_SECONDS,
            pool=settings.DS_SERVICE_READ_TIMEOUT_SECONDS,
        ),
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


def raise_for_ds_request_error(exc: httpx.RequestError) -> None:
    """A connect failure and a read timeout are different situations, not the
    same "unreachable" error (2026-08-26, per the user) — a ReadTimeout means
    ds is still working (confirmed some ds calls fire ~20 concurrent LLM
    requests and can legitimately run long), while a ConnectError/ConnectTimeout
    means it genuinely can't be reached. Any other RequestError subtype
    (write/pool timeout, etc.) falls back to the original "unreachable"
    wording, matching prior behavior for untested edge cases."""
    if isinstance(exc, httpx.ReadTimeout):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="InvestigationAi_DS is taking longer than usual to respond — please try again shortly.",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"InvestigationAi_DS service unreachable: {exc}",
    ) from exc


async def ds_post(path: str, json: Optional[dict] = None, **kwargs: Any) -> Any:
    client = get_client()
    try:
        response = await client.post(path, json=json, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        raise_for_ds_request_error(exc)


async def ds_get(path: str, params: Optional[dict] = None, **kwargs: Any) -> Any:
    client = get_client()
    try:
        response = await client.get(path, params=params, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        raise_for_ds_request_error(exc)
