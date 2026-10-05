"""Router-level tests for backend/backend/routers/auth.py — no live DB, no live network.
Builds a minimal FastAPI app around just this router and monkeypatches the DB query functions
it imports (patched where they're looked up: backend.routers.auth.<name>, not their definition
module). Permission checks use real JWTs via issue_token()/require_admin rather than overriding
the dependency, so the actual role-check logic is exercised, not bypassed."""

import datetime

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from backend.routers import auth as auth_router_module

app = FastAPI()
app.include_router(auth_router_module.router)
client = TestClient(app)


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _user_row(**overrides):
    row = {
        "id": 1,
        "username": "jane@example.com",
        "password_hash": _hash("correct-password"),
        "is_active": True,
        "role": "Investigator",
        "full_name": "Jane Doe",
        "investigator_name": "Jane Doe",
        "created_at": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        "last_login": None,
    }
    row.update(overrides)
    return row


def _admin_token():
    return auth_router_module.issue_token("admin@example.com", 1, roles=["Admin"])


def _non_admin_token():
    return auth_router_module.issue_token("user@example.com", 2, roles=["Investigator"])


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


def test_login_succeeds_with_correct_credentials(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_username", AsyncMock(return_value=_user_row()))
    monkeypatch.setattr(auth_router_module, "record_login", AsyncMock())
    response = client.post("/auth/login", json={"username": "jane@example.com", "password": "correct-password"})
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "jane@example.com"
    assert body["access_token"]


def test_login_rejects_wrong_password(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_username", AsyncMock(return_value=_user_row()))
    monkeypatch.setattr(auth_router_module, "record_login", AsyncMock())
    response = client.post("/auth/login", json={"username": "jane@example.com", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_login_rejects_unknown_username(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_username", AsyncMock(return_value=None))
    monkeypatch.setattr(auth_router_module, "record_login", AsyncMock())
    response = client.post("/auth/login", json={"username": "nobody@example.com", "password": "anything"})
    assert response.status_code == 401


def test_login_rejects_inactive_user_even_with_correct_password(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_username", AsyncMock(return_value=_user_row(is_active=False)))
    monkeypatch.setattr(auth_router_module, "record_login", AsyncMock())
    response = client.post("/auth/login", json={"username": "jane@example.com", "password": "correct-password"})
    assert response.status_code == 401


def test_login_rejects_empty_password_with_422():
    response = client.post("/auth/login", json={"username": "jane@example.com", "password": ""})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


def test_me_requires_a_token():
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_username_from_token():
    token = auth_router_module.issue_token("jane@example.com", 1)
    response = client.get("/auth/me", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["username"] == "jane@example.com"


def test_me_rejects_garbage_token():
    response = client.get("/auth/me", headers=_auth_headers("not-a-real-jwt"))
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PUT /auth/change-password
# ---------------------------------------------------------------------------


def test_change_password_succeeds_with_correct_current_password(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_id", AsyncMock(return_value=_user_row()))
    monkeypatch.setattr(auth_router_module, "update_user_password", AsyncMock())
    token = auth_router_module.issue_token("jane@example.com", 1)
    response = client.put(
        "/auth/change-password",
        json={"current_password": "correct-password", "new_password": "new-password-123"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_change_password_rejects_wrong_current_password(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_id", AsyncMock(return_value=_user_row()))
    monkeypatch.setattr(auth_router_module, "update_user_password", AsyncMock())
    token = auth_router_module.issue_token("jane@example.com", 1)
    response = client.put(
        "/auth/change-password",
        json={"current_password": "totally-wrong", "new_password": "new-password-123"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Current password is incorrect"


def test_change_password_rejects_too_short_new_password():
    token = auth_router_module.issue_token("jane@example.com", 1)
    response = client.put(
        "/auth/change-password",
        json={"current_password": "correct-password", "new_password": "short"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /auth/event-explorer-handoff
# ---------------------------------------------------------------------------


def test_event_explorer_handoff_returns_a_url_containing_a_token():
    token = auth_router_module.issue_token("jane@example.com", 1)
    response = client.get("/auth/event-explorer-handoff", headers=_auth_headers(token))
    assert response.status_code == 200
    url = response.json()["url"]
    assert "handoff=" in url


# ---------------------------------------------------------------------------
# Admin endpoints — permission gate
# ---------------------------------------------------------------------------


def test_admin_endpoints_reject_non_admin_role():
    response = client.get("/auth/admin/users", headers=_auth_headers(_non_admin_token()))
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_endpoints_reject_missing_token():
    response = client.get("/auth/admin/users")
    assert response.status_code == 401


def test_list_users_returns_users_and_roles(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_all_users", AsyncMock(return_value=[_user_row()]))
    monkeypatch.setattr(auth_router_module, "fetch_all_role_names", AsyncMock(return_value=["Admin", "Investigator", "SIT"]))
    response = client.get("/auth/admin/users", headers=_auth_headers(_admin_token()))
    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["Admin", "Investigator", "SIT"]
    assert body["users"][0]["username"] == "jane@example.com"


def test_create_admin_user_succeeds(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_role_id_by_name", AsyncMock(return_value=5))
    monkeypatch.setattr(auth_router_module, "create_user", AsyncMock(return_value=42))
    response = client.post(
        "/auth/admin/users",
        json={"username": "new@example.com", "full_name": "New User", "password": "password123", "role": "Investigator"},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 42
    assert body["is_active"] is True


def test_create_admin_user_rejects_unknown_role(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_role_id_by_name", AsyncMock(return_value=None))
    response = client.post(
        "/auth/admin/users",
        json={"username": "new@example.com", "full_name": "New User", "password": "password123", "role": "NotARole"},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown role"


def test_create_admin_user_rejects_duplicate_username(monkeypatch):
    import asyncpg

    monkeypatch.setattr(auth_router_module, "fetch_role_id_by_name", AsyncMock(return_value=5))
    monkeypatch.setattr(
        auth_router_module, "create_user", AsyncMock(side_effect=asyncpg.exceptions.UniqueViolationError())
    )
    response = client.post(
        "/auth/admin/users",
        json={"username": "dup@example.com", "full_name": "Dup User", "password": "password123", "role": "Investigator"},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 409


def test_update_admin_user_role_succeeds(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_role_id_by_name", AsyncMock(return_value=5))
    monkeypatch.setattr(auth_router_module, "update_user_role", AsyncMock(return_value=True))
    monkeypatch.setattr(auth_router_module, "fetch_all_users", AsyncMock(return_value=[_user_row(id=7, role="SIT")]))
    response = client.put(
        "/auth/admin/users/7/role",
        json={"role": "SIT"},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 200
    assert response.json()["role"] == "SIT"


def test_update_admin_user_role_404_when_update_reports_no_row_updated(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_role_id_by_name", AsyncMock(return_value=5))
    monkeypatch.setattr(auth_router_module, "update_user_role", AsyncMock(return_value=False))
    response = client.put(
        "/auth/admin/users/999/role",
        json={"role": "SIT"},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 404


def test_admin_set_user_password_404_for_unknown_user(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_id", AsyncMock(return_value=None))
    response = client.put(
        "/auth/admin/users/999/password",
        json={"new_password": "new-password-123"},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 404


def test_admin_set_user_password_succeeds(monkeypatch):
    monkeypatch.setattr(auth_router_module, "fetch_user_by_id", AsyncMock(return_value=_user_row()))
    monkeypatch.setattr(auth_router_module, "update_user_password", AsyncMock())
    response = client.put(
        "/auth/admin/users/1/password",
        json={"new_password": "new-password-123"},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 200


def test_get_audit_trail_returns_entries(monkeypatch):
    monkeypatch.setattr(
        auth_router_module,
        "fetch_audit_trail",
        AsyncMock(
            return_value=[
                {
                    "created_at": "2026-01-01T00:00:00Z",
                    "method": "GET",
                    "path": "/api/records/1/none/rci-plan",
                    "status_code": 200,
                    "duration_ms": 12,
                    "username": "jane@example.com",
                    "full_name": "Jane Doe",
                    "role": "Investigator",
                }
            ]
        ),
    )
    response = client.get("/auth/admin/audit-trail/1/none", headers=_auth_headers(_admin_token()))
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 1


def test_update_admin_user_active_status_succeeds(monkeypatch):
    monkeypatch.setattr(auth_router_module, "update_user_active_status", AsyncMock(return_value=True))
    monkeypatch.setattr(auth_router_module, "fetch_all_users", AsyncMock(return_value=[_user_row(id=7, is_active=False)]))
    response = client.put(
        "/auth/admin/users/7/status",
        json={"is_active": False},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_update_admin_user_active_status_404_when_not_found(monkeypatch):
    monkeypatch.setattr(auth_router_module, "update_user_active_status", AsyncMock(return_value=False))
    response = client.put(
        "/auth/admin/users/999/status",
        json={"is_active": False},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 404


def test_update_admin_user_investigator_name_clears_to_none_on_empty_string(monkeypatch):
    update_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_router_module, "update_user_investigator_name", update_mock)
    monkeypatch.setattr(auth_router_module, "fetch_all_users", AsyncMock(return_value=[_user_row(id=7, investigator_name=None)]))
    response = client.put(
        "/auth/admin/users/7/investigator-name",
        json={"investigator_name": ""},
        headers=_auth_headers(_admin_token()),
    )
    assert response.status_code == 200
    update_mock.assert_awaited_once_with(7, None)
