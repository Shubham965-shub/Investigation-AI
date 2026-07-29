"""
Pytest configuration and shared fixtures for all agent tests.
"""

import pytest
import os
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# Set up environment variables before importing app
@pytest.fixture(scope="session", autouse=True)
def setup_env():
    """Set up test environment variables."""
    os.environ.setdefault("OPENAI_API_KEY", "test-key-12345")
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("DB_USER", "test_user")
    os.environ.setdefault("DB_PASSWORD", "test_password")
    os.environ.setdefault("DB_NAME", "test_db")


# Now import the app after env is set up
from src.agents.app import create_app
from src.utils import deps


@pytest.fixture
def app():
    """Create a FastAPI application for testing."""
    app_instance = create_app()
    return app_instance


@pytest.fixture
def client(app):
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    pool = AsyncMock()
    pool.acquire = AsyncMock()
    
    # Mock connection context manager
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock(return_value=None)
    
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    pool.acquire.return_value.__aexit__.return_value = None
    
    return pool


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    llm = AsyncMock()
    llm.invoke = AsyncMock(return_value="Mock LLM response")
    return llm


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings configuration."""
    mock_config = {
        'SEARCH_TABLE': 'test_search_table',
        'SUMMARY_TABLE': 'test_summary_table',
        'SUMMARY_ID_COLUMN': 'id',
        'COLUMN_ID': 'deviation_id',
        'COLUMN_CATEGORY': 'category',
        'COLUMN_LOCATION': 'location',
        'SUMMARY_COL_EVENT_DESCRIPTION': 'title',
        'SUMMARY_COL_ROOT_CAUSE': 'root_cause_summary',
        'SUMMARY_COL_CAPA': 'capa_details_summary',
        'SUMMARY_COL_CAPA_DATE': 'capa_date',
        'COLUMN_CAPA_IMPLEMENTATION_DATE': 'capa_date',
        'COLUMN_CAPA_NUMBER': 'capa_number',
        'COLUMN_IMMEDIATE_ACTIONS': 'immediate_actions',
        'COLUMN_CORRECTIVE_ACTIONS': 'corrective_actions',
        'COLUMN_PREVENTIVE_ACTIONS': 'preventive_actions',
        'PROMPTS_DIR': 'src/prompts',
    }
    
    with patch('src.config.settings.settings') as mock_settings:
        for key, value in mock_config.items():
            setattr(mock_settings, key, value)
        yield mock_settings


@pytest.fixture
def setup_deps(mock_db_pool, mock_llm_client, mock_settings):
    """Setup dependency injection for tests."""
    deps.set_pool(mock_db_pool)
    deps.set_llm(mock_llm_client)
    
    yield
    
    # Cleanup
    deps._pool = None
    deps._llm = None


@pytest.fixture
def sample_search_request():
    """Sample valid search request."""
    return {
        "query": "test deviation",
        "search_type": "Hybrid",
        "date_range": "last_30_days",
        "sites": ["all"],
        "instruments": ["all"],
        "materials": ["all"],
        "product_code": ["all"],
        "search_via": "Both",
        "top_k": 10,
    }


@pytest.fixture
def sample_critique_request():
    """Sample valid critique request."""
    return {
        "eventDescription": {
            "section": "1.0",
            "title": "Event Description",
            "data": {
                "rciNumber": "RCI-2024-001",
                "rciOwner": "John Doe",
                "rciInitiatedOn": "2024-01-15",
                "parentRecord": None,
                "problemStatement": "Test problem statement",
            },
        },
        "taskAssignments": {
            "section": "3.0",
            "title": "Task Assignments",
            "data": [
                {
                    "tick": "Task 1",
                    "task": "Pending",
                    "responsible_person": "Jane Doe",
                    "selected": True,
                    "critique": "",
                    "mandatory": True,
                }
            ],
        },
    }


@pytest.fixture
def sample_evaluation_request():
    """Sample valid problem statement evaluation request."""
    return {
        "event_type": "Manufacturing",
        "narrative": "The product batch showed unexpected color variation during production.",
    }


@pytest.fixture
def sample_cumulative_summary_request():
    """Sample cumulative summary request."""
    return {"deviation_id": ["DEV001", "DEV002"]}


@pytest.fixture
def sample_questionnaire_request():
    """Sample questionnaire request."""
    return {
        "event_type": "Manufacturing",
        "problem_statement": "Root cause analysis needed",
        "preliminary_findings": "Initial investigation shows control failure",
    }


# Helper functions for test assertions

def assert_valid_search_response(response_data):
    """Assert that response has valid search response structure."""
    assert isinstance(response_data, dict)
    assert "results" in response_data or "llm_data" in response_data or response_data == {}


def assert_valid_error_response(response_data, expected_status_code):
    """Assert that response has valid error structure."""
    assert isinstance(response_data, dict)
    assert "detail" in response_data or response_data.get("detail")
