"""Placeholder auth schemas — no real credential store yet.

Any non-empty username/password succeeds and returns an opaque bearer
token. Replace with real identity provider integration later.
"""
from __future__ import annotations

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
