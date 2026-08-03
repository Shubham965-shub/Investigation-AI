"""Authentication endpoints.

Real credential store as of 2026-07-31: schema.sql's athena_users/
athena_roles tables have been applied to the shared DB, and login verifies
the submitted password against the stored bcrypt hash (bcrypt was already a
declared dependency, previously unused). Tokens are signed, expiring JWTs
(HS256) — not an opaque placeholder — carrying the user's id ("uid") alongside
their username ("sub") so the audit-trail middleware (see app.py) can resolve
who made a request without an extra DB round-trip per request.

get_current_username() is the shared dependency both /auth/me and every
other (non-auth) router use to require a valid token — see app.py's
include_router(..., dependencies=[Depends(get_current_username)]) calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config.settings import settings
from backend.db.auth_queries import fetch_user_by_username
from backend.schemas.auth import CurrentUser, LoginRequest, LoginResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])
_bearer_scheme = HTTPBearer(auto_error=False)

_INVALID_CREDENTIALS_DETAIL = "Invalid username or password"


def issue_token(username: str, user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "uid": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_token(token: str) -> str:
    try:
        # ExpiredSignatureError is a subclass of InvalidTokenError — must be
        # caught first, or "expired" would be misreported as "invalid".
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return username


def try_decode_payload(token: str) -> Optional[dict]:
    """Best-effort, never-raising decode used only by app.py's request
    middleware — for the audit trail (a request with a missing/invalid/
    expired token still gets logged as an anonymous call, user_id=None) and
    for sliding-expiry token refresh (only a STILL-VALID token's payload is
    returned — an already-expired token returns None here too, same as an
    invalid one, so refresh can only extend a live session, never resurrect
    a dead one; the user must fully re-login once actually expired)."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None


def get_current_username(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return _decode_token(credentials.credentials)


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    user = await fetch_user_by_username(request.username)
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS_DETAIL)
    if not bcrypt.checkpw(request.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS_DETAIL)
    return LoginResponse(access_token=issue_token(user["username"], user["id"]), username=user["username"])


@router.get("/me", response_model=CurrentUser)
async def me(username: str = Depends(get_current_username)) -> CurrentUser:
    return CurrentUser(username=username)