"""Authentication endpoints.

Real credential store as of 2026-07-31: schema.sql's athena_users/
athena_roles tables have been applied to the shared DB, and login verifies
the submitted password against the stored bcrypt hash (bcrypt was already a
declared dependency, previously unused). Tokens are signed, expiring JWTs
(HS256) — not an opaque placeholder.

JWT_SECRET is a platform-wide shared secret (see settings.py) — this app's
own regular session token IS the token other ARGUS Lighthouse services (e.g.
the feedback widget's service, AppFeedbackButton.tsx) accept too, no separate
per-service token needed. That service's own AuthFilter (confirmed
2026-08-03 by reading Strides-Pharma-Science-Ltd/feedback-platform directly)
does `UUID.fromString(claims.getSubject())` — `sub` MUST be a UUID string, a
generic RuntimeException there (e.g. from a non-UUID sub) is caught and
reported back as the exact opaque "Invalid bearer token" this app hit before
this was found. This app's athena_users has no real UUID column, so `sub`
here is `uuid_for_user_id()` — a deterministic UUID derived from the
integer id (stable per user, no schema change needed; the feedback service
never looks it up against anything, it's opaque to them). The ACTUAL
username now travels as a separate `username` claim instead — every internal
reader of this token (get_current_username(), the audit-trail middleware)
was updated to read that claim, not `sub`, accordingly. `roles`/`email` are
the other half of the interop contract, read by the feedback service to
attribute a submission without a DB lookup back to this app.

get_current_username() is the shared dependency both /auth/me and every
other (non-auth) router use to require a valid token — see app.py's
include_router(..., dependencies=[Depends(get_current_username)]) calls.
"""
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
    """A stable, deterministic UUID string for a given athena_users.id — see
    this module's docstring for why `sub` needs to be UUID-shaped at all."""
    return str(uuid.UUID(int=user_id))


def display_name_for_username(username: str) -> str:
    """Fallback only — used when athena_users.full_name is unset for an
    account. Derives a best-effort display name from the email-shaped
    username, e.g. "Saksham.Shankar@strides.com" -> "Saksham Shankar",
    "kaberi_nath@mckinsey.com" -> "Kaberi Nath". Known to get concatenated
    names wrong (e.g. "SatyanarayanSingh.Rajput" -> "SatyanarayanSingh
    Rajput", not the real "Satyanarayan Singh Rajput") — real full_name
    values take priority (see issue_token) precisely because of cases like
    that. A part already containing a capital letter is left as-is rather
    than forced to lowercase-then-capitalize, since it may already be an
    intentional concatenation."""
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
        # username IS an email address in this app's data (see the 7 seeded
        # accounts), so it doubles as the "email" identity claim the
        # reference platform's own tokens carry — no separate field needed.
        "email": username,
        "name": full_name or display_name_for_username(username),
        "roles": roles or [],
        # Investigator-role scoping hook (2026-09-09, per the user) — see
        # schema.sql's athena_users.investigator_name comment. Embedded in
        # the token so action_center.py's per-request scoping doesn't need
        # its own DB round trip; only meaningful when "Investigator" is in
        # roles above.
        "investigator_name": investigator_name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_token_payload(token: str) -> dict:
    try:
        # ExpiredSignatureError is a subclass of InvalidTokenError — must be
        # caught first, or "expired" would be misreported as "invalid".
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    # NOT "sub" — see module docstring (sub is now a UUID derived from uid,
    # not the username).
    if not payload.get("username"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


def _decode_token(token: str) -> str:
    return _decode_token_payload(token)["username"]


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


# Used where a route needs more than just the username — e.g.
# action_center.py's Investigator-role scoping needs `roles` and
# `investigator_name` too. Re-decodes the token independently rather than
# building on get_current_username, same pattern require_admin below already
# uses.
def get_current_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return _decode_token_payload(credentials.credentials)


# Gate for the User Management endpoints below (2026-09-08, per the user) —
# the first role-based authorization check in this codebase; every other
# router only ever required a valid token (see module docstring), never a
# specific role. Checks the JWT's own `roles` claim (already embedded at
# login, see issue_token) rather than re-querying the DB, so a role change
# only takes effect on that user's next login — same characteristic already
# true of the frontend's role-based UI (e.g. Action Center's "SIT Dashboard"
# title), not a new inconsistency introduced here.
def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = _decode_token_payload(credentials.credentials)
    if "Admin" not in (payload.get("roles") or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
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


# Event Explorer SSO handoff (2026-08-19, per the user) — mints a short-lived,
# single-purpose token InvestigationAI_BE exchanges for its own local session,
# so clicking "Explore Events" lands the user in InvestigationAI_FE's Event
# Explorer already authenticated as the same athena_users identity. Signed
# with EVENT_EXPLORER_HANDOFF_SECRET (NOT settings.JWT_SECRET — see that
# setting's docstring for why this is a deliberately separate secret).
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


# User Management (2026-09-08, per the user) — admin-only: list every
# athena_users row, create a new one, or change an existing one's role.
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