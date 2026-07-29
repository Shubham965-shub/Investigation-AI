import io

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from src.agents.app import create_app
from agents.rot_cause_advisor.api.services.root_cause_advisor_service import (
    ROOT_CAUSE_CATEGORIES,
    validate_root_cause_advice,
)

client = TestClient(create_app())


def test_root_cause_advisor_rejects_unsupported_file_type():
    response = client.post(
        "/rca/root_cause_advisor",
        data={"event_type": "deviation"},
        files={"file": ("test.txt", b"invalid content", "text/plain")},
    )

    assert response.status_code == 415
    assert "supported" in response.json()["detail"].lower()


def test_root_cause_advisor_requires_non_empty_event_type():
    response = client.post(
        "/rca/root_cause_advisor",
        data={"event_type": ""},
        files={"file": ("document.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "event_type is required and must be non-empty."


def test_validate_root_cause_advice_rejects_missing_category():
    incomplete_response = [
        {
            "category": "man",
            "gaps": [],
            "hypothesis": [],
            "tasks": [],
            "assumptions": [],
        }
    ]

    with pytest.raises(HTTPException):
        validate_root_cause_advice(incomplete_response)


def test_root_cause_advisor_route_returns_valid_list(monkeypatch):
    async def fake_generate(event_type, file, llm):
        return [
            {
                "category": category,
                "gaps": [],
                "hypothesis": [],
                "tasks": [],
                "assumptions": [],
            }
            for category in ROOT_CAUSE_CATEGORIES
        ]

    monkeypatch.setattr(
        "src.agents.rot_cause_advisor.api.routes.root_cause_advisor_route.generate_root_cause_advice",
        fake_generate,
    )

    response = client.post(
        "/rca/root_cause_advisor",
        data={"event_type": "deviation"},
        files={"file": ("document.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == len(ROOT_CAUSE_CATEGORIES)
    assert response.json()[0]["category"] == ROOT_CAUSE_CATEGORIES[0]
