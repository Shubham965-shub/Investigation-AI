"""Placeholder authentication endpoints.

No real identity provider yet: any non-empty username/password is accepted
and exchanged for an opaque bearer token so the frontend has a login flow
and protected-route shell to build against. Swap for real auth later.
"""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config.settings import settings
from src.schemas.auth import CurrentUser, LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Auth"])
_bearer_scheme = HTTPBearer(auto_error=False)


def _issue_token(username: str) -> str:
    payload = f"{username}:{settings.AUTH_PLACEHOLDER_SECRET}"
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_token(token: str) -> str:
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        username, secret = payload.split(":", 1)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
    if secret != settings.AUTH_PLACEHOLDER_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return username


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    return LoginResponse(access_token=_issue_token(request.username), username=request.username)


@router.get("/me", response_model=CurrentUser)
async def me(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return CurrentUser(username=_decode_token(credentials.credentials))
