"""Auth schemas. No real credential store yet — any non-empty username/password succeeds."""
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


# ── User Management (admin-only) ──


class AdminUserRow(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    # Links this account to its dim_investigator identity for Action Center scoping; NULL falls back to matching full_name.
    investigator_name: Optional[str] = None


class AdminUserListResponse(BaseModel):
    users: List[AdminUserRow]
    # Every athena_roles.name — populates the role dropdown without a second call.
    roles: List[str]


class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1)
    full_name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)
    role: str = Field(..., min_length=1)
    investigator_name: Optional[str] = None


class AdminUpdateUserRoleRequest(BaseModel):
    role: str = Field(..., min_length=1)


class AdminUpdateInvestigatorNameRequest(BaseModel):
    # "" clears it to NULL; kept non-Optional so an omitted field isn't ambiguous with "clear it".
    investigator_name: str = Field(default="")
