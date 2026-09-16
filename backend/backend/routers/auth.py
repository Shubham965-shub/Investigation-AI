"""Auth endpoints. JWT_SECRET is shared with other ARGUS Lighthouse services (e.g. the
feedback widget), whose AuthFilter requires `sub` to be a UUID string — so `sub` here is a
deterministic UUID derived from the user id, and the real username travels as a separate
`username` claim instead (read by get_current_username() and the audit-trail middleware)."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import asyncpg

from backend.config.settings import settings
from backend.db.auth_queries import (
    create_user,
    fetch_all_role_names,
    fetch_all_users,
    fetch_role_id_by_name,
    fetch_user_by_username,
    record_login,
    update_user_investigator_name,
    update_user_role,
)
from backend.schemas.auth import (
    AdminCreateUserRequest,
    AdminUpdateInvestigatorNameRequest,
    AdminUpdateUserRoleRequest,
    AdminUserListResponse,
    AdminUserRow,
    CurrentUser,
    EventExplorerHandoffResponse,
    LoginRequest,
    LoginResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])
_bearer_scheme = HTTPBearer(auto_error=False)

_INVALID_CREDENTIALS_DETAIL = "Invalid username or password"


def uuid_for_user_id(user_id: int) -> str:
    """Deterministic UUID for a user id — `sub` must be UUID-shaped for cross-service interop."""
    return str(uuid.UUID(int=user_id))


def display_name_for_username(username: str) -> str:
    """Fallback display name derived from an email-shaped username, used only when full_name is unset; can mis-split already-concatenated name parts."""
    local_part = username.split("@", 1)[0]
    parts = [p for p in re.split(r"[._]+", local_part) if p]
    if not parts:
        return username
    return " ".join(p.capitalize() if p.islower() else p for p in parts)


def issue_token(
    username: str,
    user_id: int,
    roles: Optional[list[str]] = None,
    full_name: Optional[str] = None,
    investigator_name: Optional[str] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": uuid_for_user_id(user_id),
        "username": username,
        "uid": user_id,
        "email": username,  # username is already an email address in this app's data
        "name": full_name or display_name_for_username(username),
        "roles": roles or [],
        # Embedded so action_center.py's Investigator-role scoping avoids a DB round trip.
        "investigator_name": investigator_name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_token_payload(token: str) -> dict:
    try:
        # ExpiredSignatureError subclasses InvalidTokenError — must be caught first.
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if not payload.get("username"):  # NOT "sub" — sub is a UUID derived from uid
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


def _decode_token(token: str) -> str:
    return _decode_token_payload(token)["username"]


def try_decode_payload(token: str) -> Optional[dict]:
    """Never-raising decode for audit logging and sliding-expiry refresh; an expired token returns None (same as invalid), so refresh can extend a live session but never resurrect a dead one."""
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


# For routes needing more than the username, e.g. action_center.py's roles/investigator_name scoping.
def get_current_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return _decode_token_payload(credentials.credentials)


# Checks the JWT's roles claim rather than the DB, so a role change takes effect only on next login.
def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = _decode_token_payload(credentials.credentials)
    if "Admin" not in (payload.get("roles") or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return payload["username"]


# Gate for the SIT Dashboard's "Remark" field — deliberately SIT-only, not SIT-or-Admin.
def require_sit(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = _decode_token_payload(credentials.credentials)
    if "SIT" not in (payload.get("roles") or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SIT role required")
    return payload["username"]


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    user = await fetch_user_by_username(request.username)
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS_DETAIL)
    if not bcrypt.checkpw(request.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS_DETAIL)
    roles = [user["role"]] if user["role"] else []
    token = issue_token(user["username"], user["id"], roles, user["full_name"], user["investigator_name"])
    await record_login(user["id"])
    return LoginResponse(access_token=token, username=user["username"])


@router.get("/me", response_model=CurrentUser)
async def me(username: str = Depends(get_current_username)) -> CurrentUser:
    return CurrentUser(username=username)


# Short-lived SSO handoff token InvestigationAI_BE exchanges for its own session; signed with a
# separate secret (EVENT_EXPLORER_HANDOFF_SECRET), not settings.JWT_SECRET.
_HANDOFF_TOKEN_TTL_SECONDS = 60


@router.get("/event-explorer-handoff", response_model=EventExplorerHandoffResponse)
async def event_explorer_handoff(username: str = Depends(get_current_username)) -> EventExplorerHandoffResponse:
    now = datetime.now(timezone.utc)
    payload = {
        "username": username,
        "iat": now,
        "exp": now + timedelta(seconds=_HANDOFF_TOKEN_TTL_SECONDS),
    }
    token = jwt.encode(payload, settings.EVENT_EXPLORER_HANDOFF_SECRET, algorithm=settings.JWT_ALGORITHM)
    url = f"{settings.EVENT_EXPLORER_URL}/event-explorer?handoff={token}"
    return EventExplorerHandoffResponse(url=url)


# User Management: admin-only list/create/role-change endpoints.
_USERNAME_TAKEN_DETAIL = "That username/email is already in use"
_UNKNOWN_ROLE_DETAIL = "Unknown role"


@router.get("/admin/users", response_model=AdminUserListResponse)
async def list_users(_: str = Depends(require_admin)) -> AdminUserListResponse:
    rows = await fetch_all_users()
    roles = await fetch_all_role_names()
    return AdminUserListResponse(users=[AdminUserRow(**dict(r)) for r in rows], roles=roles)


@router.post("/admin/users", response_model=AdminUserRow, status_code=status.HTTP_201_CREATED)
async def create_admin_user(request: AdminCreateUserRequest, _: str = Depends(require_admin)) -> AdminUserRow:
    role_id = await fetch_role_id_by_name(request.role)
    if role_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_UNKNOWN_ROLE_DETAIL)
    password_hash = bcrypt.hashpw(request.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        user_id = await create_user(
            request.username, request.full_name, password_hash, role_id, request.investigator_name
        )
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_USERNAME_TAKEN_DETAIL)
    return AdminUserRow(
        id=user_id,
        username=request.username,
        full_name=request.full_name,
        role=request.role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_login=None,
        investigator_name=request.investigator_name,
    )


@router.put("/admin/users/{user_id}/role", response_model=AdminUserRow)
async def update_admin_user_role(
    user_id: int, request: AdminUpdateUserRoleRequest, _: str = Depends(require_admin)
) -> AdminUserRow:
    role_id = await fetch_role_id_by_name(request.role)
    if role_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_UNKNOWN_ROLE_DETAIL)
    updated = await update_user_role(user_id, role_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    rows = await fetch_all_users()
    row = next((r for r in rows if r["id"] == user_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserRow(**dict(row))


@router.put("/admin/users/{user_id}/investigator-name", response_model=AdminUserRow)
async def update_admin_user_investigator_name(
    user_id: int, request: AdminUpdateInvestigatorNameRequest, _: str = Depends(require_admin)
) -> AdminUserRow:
    updated = await update_user_investigator_name(user_id, request.investigator_name or None)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    rows = await fetch_all_users()
    row = next((r for r in rows if r["id"] == user_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserRow(**dict(row))