import io

import pytest
from fastapi.testclient import TestClient

from src.agents.app import create_app
from src.prompt_registry.service import PromptRegistry
from src.utils import deps
from agents.rot_cause_advisor.api.services.root_cause_advisor_service import (
    ROOT_CAUSE_CATEGORIES,
)

# The service now loads its prompts from PromptRegistry at request time
# (migrated off static .txt files, 2026-09-02) — client is built directly
# rather than as a lifespan-entering context manager, so the registry that
# lifespan would normally set up is registered explicitly here instead.
# Must be a per-test fixture, not bare module-level code: deps._prompt_registry
# is a process-global, and other test files' fixtures (e.g.
# test_problem_statement_evaluation_v2.py) reset it to None in their own
# teardown — a one-time module-level set gets wiped out by the time this
# file's tests actually run later in a full-suite session.
@pytest.fixture(autouse=True)
def _prompt_registry():
    deps.set_prompt_registry(PromptRegistry())
    yield
    deps._prompt_registry = None


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


# A test here used to call validate_root_cause_advice(), checking that an LLM response missing
# a category raised HTTPException. That function no longer exists anywhere in the codebase (and
# the response schema itself has since changed shape — rootCauseAdvisoryResponse now wraps a
# root_cause_categories list, and RootCauseCategory's fields were restructured, e.g. hypothesis/
# tasks merged into items: List[HypothesisTask]), confirmed 2026-10-01: this validation was
# dropped in a refactor and never replaced, not a test bug — removed rather than reinventing
# unspecified validation behavior.


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
