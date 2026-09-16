from __future__ import annotations

from fastapi import APIRouter

from backend.db.action_center_queries import fetch_open_investigations_count

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Unauthenticated (included without the shared auth dependency, unlike action_center's own
# summary endpoint) — the login page's "N investigations · live" stat needs this before a
# token exists. Only ever exposes a bare count, no investigation-level data.
@router.get("/public-stats")
async def public_stats() -> dict:
    return {"open_investigations": await fetch_open_investigations_count()}
