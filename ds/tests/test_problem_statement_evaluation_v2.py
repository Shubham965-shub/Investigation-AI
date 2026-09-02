"""
Tests for Problem Statement Evaluation V2 API (POST /ps/v2/generate).

This file previously failed 17/19 tests. Root causes (all test-fixture/test-
harness drift, not production bugs):

1. Trackwise field requirements had moved on since these fixtures were
   written — OOSTrackwiseFields gained several new required fields
   (laboratory_details, specification_number, stability_condition,
   stability_protocol_number, labelled_storage_conditions, product_type,
   stp_number, stability_time_point; see src/agents/shared/schemas.py) and
   DeviationTrackwiseFields has no `populate_by_name`, so it only accepts the
   real TrackWise alias keys (e.g. "Observed By"), not attribute names
   (e.g. "observed_by") — unlike OOS/Market Complaint, which both set
   `populate_by_name = True` and accept either.
2. `event_type` is a pydantic `Literal`, so an invalid value is now rejected
   at request-parsing time with FastAPI's own 422 (array-shaped `detail`),
   not the 400 these tests expected.
3. `ProblemStatementGenerationResponse` (v2/schemas.py) only ever had two
   fields, `event_type` and `problem_statement` — several tests asserted on
   `summary`/`severity_level`/`key_findings`, which have never existed on
   this response model. Confirmed directly against the route
   (v2/routes/ps_v2_route.py) and service (v2/services/problem_statement_generator.py).
4. The endpoint calls a real LLM via get_llm_client()/get_prompt_registry();
   neither was mocked here before (the shared `setup_deps` fixture in
   conftest.py never calls `deps.set_prompt_registry`, and mocks
   `llm.invoke`, while this service calls `llm.chat`) — every request fell
   through to `AssertionError: PromptRegistry not initialised` -> 500.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.utils import deps


@pytest.fixture(autouse=True)
def mock_generation_deps():
    """Mock the LLM + prompt registry this endpoint actually calls
    (get_llm_client().chat(...) and get_prompt_registry().get(...).format(...)),
    independently of the shared conftest fixtures (which target a different
    LLM method and never set a prompt registry at all)."""
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value="Generated problem statement based on the provided trackwise fields.")

    template = MagicMock()
    template.format.return_value = "formatted prompt"
    registry = MagicMock()
    registry.get.return_value = template

    deps.set_llm(llm)
    deps.set_prompt_registry(registry)
    yield llm
    deps._llm = None
    deps._prompt_registry = None


def _valid_deviation_fields(**overrides):
    fields = {
        "title": "Rough tablet surface",
        "Batch Number / AR Number": "BATCH001",
        "Product / Material Code": "PROD001",
        "Product Name / Material Name": "Ranitidine Tablets 150mg",
        "Deviation To": "SOP-123",
        "Equipment Name": "Tablet Press Unit 1",
        "description": "Rough surfaces observed on tablet coating during inspection.",
        "Instrument ID Number": "INS-01",
        "Name of the Instrument": "Caliper",
        "Observed By": "IPQA Personnel",
    }
    fields.update(overrides)
    return fields


def _valid_oos_fields(**overrides):
    fields = {
        "title": "OOS Result Reported",
        "description": "NDSRI result was reported OOS for the product.",
        "observation_date": "2024-02-10",
        "laboratory_details": "QC Lab 2",
        "specification_number": "SPC-001",
        "stability_condition": "25°C/60% RH",
        "stability_protocol_number": "SP-001",
        "labelled_storage_conditions": "Store below 25°C",
        "observation_time": "14:45:00",
        "product_type": "Tablet",
        "stp_number": "STP-001",
        "stability_time_point": "6 months",
        "failure_type": "NDSRI Result",
        "analyst_name": "John Smith",
        "product_material_name": "Tramadol Hydrochloride Tablets USP 50mg",
    }
    fields.update(overrides)
    return fields


def _valid_market_complaint_fields(**overrides):
    fields = {
        "title": "Tablet Description Variation",
        "description": "Variation in tablet description observed during dispensing.",
        "date_complaint_received": "2024-01-20",
        "complaint_reported_by": "Pharmacist",
        "reference_complaint_number": "RC-001",
        "products_information": "Amitriptyline Tablets 10mg",
        "dosage_form": "Tablet",
        "market": "South Asia",
        "product_manufacturing_info": "Batch 7263940",
        "customer": "Retail Pharmacy Chain",
        "complainant_name": "Mr. John",
    }
    fields.update(overrides)
    return fields


class TestGenerateProblemStatementEndpoint:
    """Tests for POST /ps/v2/generate endpoint."""

    @pytest.mark.asyncio
    async def test_generate_deviation_problem_statement(self, client):
        """Test generating problem statement for Deviation event."""
        request_data = {"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()}

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "Deviation"
        assert len(data["problem_statement"]) > 0

    @pytest.mark.asyncio
    async def test_generate_oos_problem_statement(self, client):
        """Test generating problem statement for OOS event."""
        request_data = {"event_type": "OOS", "trackwise_fields": _valid_oos_fields()}

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "OOS"
        assert len(data["problem_statement"]) > 0

    @pytest.mark.asyncio
    async def test_generate_oot_problem_statement(self, client):
        """Test generating problem statement for OOT event."""
        request_data = {
            "event_type": "OOT",
            "trackwise_fields": _valid_oos_fields(
                title="OOT Result - Stability Testing",
                description="Stability test result out of specification.",
                failure_type="Potency",
                product_material_name="Aspirin Tablets 500mg",
            ),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "OOT"

    @pytest.mark.asyncio
    async def test_generate_market_complaint_problem_statement(self, client):
        """Test generating problem statement for Market Complaint event."""
        request_data = {"event_type": "Market Complaint", "trackwise_fields": _valid_market_complaint_fields()}

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "Market Complaint"
        assert "problem_statement" in data

    @pytest.mark.asyncio
    async def test_missing_event_type(self, client):
        """Test request without event_type parameter."""
        request_data = {"trackwise_fields": {"title": "Test", "description": "Test description"}}

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_event_type(self, client):
        """event_type is a pydantic Literal, so an out-of-vocabulary value is
        rejected at request-parsing time with a 422, not a route-level 400."""
        request_data = {
            "event_type": "InvalidType",
            "trackwise_fields": {"title": "Test", "description": "Test description"},
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(e["loc"] == ["body", "event_type"] for e in errors)

    @pytest.mark.asyncio
    async def test_empty_trackwise_fields(self, client):
        """An empty trackwise_fields dict fails the pre-validator's own
        ValueError, which pydantic surfaces as a 422 (not the 400 this test
        previously expected)."""
        request_data = {"event_type": "Deviation", "trackwise_fields": {}}

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 422
        assert "missing required fields" in response.json()["detail"][0]["msg"]

    @pytest.mark.asyncio
    async def test_missing_trackwise_fields(self, client):
        """Test request without trackwise_fields."""
        request_data = {"event_type": "Deviation"}

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_minimal_deviation_fields(self, client):
        """Test with the exact required-field set for Deviation (no optionals)."""
        request_data = {"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()}

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["problem_statement"]

    @pytest.mark.asyncio
    async def test_microbial_deviation_generates_successfully(self, client):
        """Renamed from test_severity_critical_for_microbial_failure: the v2
        response has no severity_level field at all (confirmed against
        ProblemStatementGenerationResponse) — there is no severity computation
        in this endpoint to test. What IS real: the microbial-failure context
        must reach the LLM prompt via the formatted trackwise fields."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": _valid_deviation_fields(description="Microbial contamination detected in cleanroom."),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        assert response.json()["problem_statement"]

    @pytest.mark.asyncio
    async def test_market_complaint_with_customer_generates_successfully(self, client):
        """Renamed from test_severity_high_for_market_complaint: same
        rationale as above — no severity_level field exists on this response."""
        request_data = {
            "event_type": "Market Complaint",
            "trackwise_fields": _valid_market_complaint_fields(customer="Major Hospital"),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        assert response.json()["problem_statement"]

    @pytest.mark.asyncio
    async def test_deviation_fields_reach_the_llm_prompt(self, client):
        """Renamed from test_key_findings_extracted: there is no key_findings
        field on the v2 response (confirmed against the schema) — what's
        actually verifiable is that the distinguishing trackwise field values
        are formatted into the prompt sent to the LLM."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": _valid_deviation_fields(**{
                "Product Name / Material Name": "Amoxicillin Capsules 250mg",
                "Equipment Name": "Capsule Filler 3",
            }),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

        registry = deps.get_prompt_registry()
        formatted_kwargs = registry.get.return_value.format.call_args.kwargs
        assert "Amoxicillin Capsules 250mg" in formatted_kwargs["formatted_fields"]
        assert "Capsule Filler 3" in formatted_kwargs["formatted_fields"]

    @pytest.mark.asyncio
    async def test_long_description_reaches_llm_prompt_unmodified(self, client):
        """Renamed from test_summary_truncation: there is no summary field or
        truncation logic anywhere in the v2 response/service (confirmed via
        grep across problem_statement_generator.py and the response schema) —
        the service passes trackwise field values through to the prompt
        verbatim, with no length cap."""
        long_description = "A" * 500
        request_data = {
            "event_type": "Market Complaint",
            "trackwise_fields": _valid_market_complaint_fields(description=long_description),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

        registry = deps.get_prompt_registry()
        formatted_kwargs = registry.get.return_value.format.call_args.kwargs
        assert long_description in formatted_kwargs["formatted_fields"]

    @pytest.mark.asyncio
    async def test_special_characters_in_fields(self, client):
        """Test handling of special characters."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": _valid_deviation_fields(
                title="Test & Special @Characters",
                **{"Product Name / Material Name": "Product™ Name®"},
                **{"Observed By": "Dr. John O'Brien"},
                description="Issue with 50% failure rate (critical)",
            ),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unicode_characters(self, client):
        """Test handling of unicode characters."""
        request_data = {
            "event_type": "Market Complaint",
            "trackwise_fields": _valid_market_complaint_fields(
                title="Complaint from 中国 customer",
                description="Issue reported by café owner",
                complaint_reported_by="François",
                market="Zürich",
            ),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_all_event_types_response_structure(self, client):
        """Test that all event types return consistent response structure.

        expected_fields trimmed to what ProblemStatementGenerationResponse
        actually declares (event_type, problem_statement) — summary/
        severity_level/key_findings have never existed on this model."""
        event_types_data = {
            "Deviation": {"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()},
            "OOS": {"event_type": "OOS", "trackwise_fields": _valid_oos_fields()},
            "OOT": {
                "event_type": "OOT",
                "trackwise_fields": _valid_oos_fields(title="OOT", description="OOT detected"),
            },
            "Market Complaint": {
                "event_type": "Market Complaint",
                "trackwise_fields": _valid_market_complaint_fields(),
            },
        }

        expected_fields = ["event_type", "problem_statement"]

        for event_type, request_data in event_types_data.items():
            response = client.post("/ps/v2/generate", json=request_data)
            assert response.status_code == 200, f"{event_type} failed: {response.json()}"
            data = response.json()

            for field in expected_fields:
                assert field in data, f"Missing field {field} in {event_type} response"

    @pytest.mark.asyncio
    async def test_null_and_none_values(self, client):
        """Test handling of null/None values in optional fields."""
        request_data = {
            "event_type": "OOS",
            "trackwise_fields": _valid_oos_fields(analyst_name=None, product_material_name=None),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_extra_fields_ignored(self, client):
        """Test that extra fields in trackwise_fields are handled gracefully."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": _valid_deviation_fields(
                extra_field_1="should be ignored",
                extra_field_2=12345,
                extra_nested={"nested": "value"},
            ),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_different_date_formats(self, client):
        """Test handling of different date formats."""
        request_data = {
            "event_type": "OOS",
            "trackwise_fields": _valid_oos_fields(observation_date="15-01-2024"),
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
