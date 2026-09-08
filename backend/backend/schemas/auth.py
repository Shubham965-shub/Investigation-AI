"""Placeholder auth schemas — no real credential store yet.

Any non-empty username/password succeeds and returns an opaque bearer
token. Replace with real identity provider integration later.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class CurrentUser(BaseModel):
    username: str


class EventExplorerHandoffResponse(BaseModel):
    url: str


# ── User Management (admin-only) ───────────────────────────────────────────
# Added 2026-09-08, per the user — a small button beside AppFeedbackButton,
# visible only to Admin-role users, opens a page listing every athena_users
# row with role/created/last-login, plus create-user and edit-role actions.


class AdminUserRow(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class AdminUserListResponse(BaseModel):
    users: List[AdminUserRow]
    # Every role name that exists (athena_roles.name) — populates the
    # role dropdown in the create-user/edit-role UI without a second call.
    roles: List[str]


class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1)
    full_name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)
    role: str = Field(..., min_length=1)


class AdminUpdateUserRoleRequest(BaseModel):
    role: str = Field(..., min_length=1)
