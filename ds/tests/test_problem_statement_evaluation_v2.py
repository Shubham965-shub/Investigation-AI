"""
Comprehensive tests for Problem Statement Evaluation V2 API.
Tests for structured problem statement generation from trackwise fields.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestGenerateProblemStatementEndpoint:
    """Tests for POST /ps/v2/generate endpoint."""

    @pytest.mark.asyncio
    async def test_generate_deviation_problem_statement(self, client, setup_deps):
        """Test generating problem statement for Deviation event."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Rough tablet surface",
                "observation_date": "2024-01-15",
                "failure_duration": "2 hours",
                "batch_number": "BATCH001",
                "product_material_code": "PROD001",
                "product_material_name": "Ranitidine Tablets 150mg",
                "related_market": "North America",
                "related_customer": "Hospital A",
                "equipment_name": "Tablet Press Unit 1",
                "description": "Rough surfaces observed on tablet coating during inspection.",
                "observed_by": "IPQA Personnel",
                "observation_time": "10:30:00",
                "is_microbial_em_failure": False,
                "responsible_department": "QA",
            },
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "problem_statement" in data
        assert "summary" in data
        assert "severity_level" in data
        assert "key_findings" in data
        assert data["event_type"] == "Deviation"
        assert len(data["problem_statement"]) > 0

    @pytest.mark.asyncio
    async def test_generate_oos_problem_statement(self, client, setup_deps):
        """Test generating problem statement for OOS event."""
        request_data = {
            "event_type": "OOS",
            "trackwise_fields": {
                "title": "OOS Result Reported",
                "description": "NDSRI result was reported OOS for the product.",
                "observation_date": "2024-02-10",
                "failure_type": "NDSRI Result",
                "product_type": "Tablet",
                "specification_number": "SPC-001",
                "stability_condition": "25°C/60% RH",
                "analyst_name": "John Smith",
                "sample_number": "SAMPLE-2024-001",
                "product_material_name": "Tramadol Hydrochloride Tablets USP 50mg",
                "observation_time": "14:45:00",
            },
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "OOS"
        assert "problem_statement" in data
        assert len(data["key_findings"]) > 0

    @pytest.mark.asyncio
    async def test_generate_oot_problem_statement(self, client, setup_deps):
        """Test generating problem statement for OOT event."""
        request_data = {
            "event_type": "OOT",
            "trackwise_fields": {
                "title": "OOT Result - Stability Testing",
                "description": "Stability test result out of specification.",
                "observation_date": "2024-03-05",
                "failure_type": "Potency",
                "specification_number": "SPC-STAB-001",
                "stability_protocol_number": "SP-001",
                "analyst_name": "Jane Doe",
                "product_material_name": "Aspirin Tablets 500mg",
                "observation_time": "09:15:00",
            },
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "OOT"

    @pytest.mark.asyncio
    async def test_generate_market_complaint_problem_statement(self, client, setup_deps):
        """Test generating problem statement for Market Complaint event."""
        request_data = {
            "event_type": "Market Complaint",
            "trackwise_fields": {
                "title": "Tablet Description Variation",
                "description": "Variation in tablet description observed during dispensing.",
                "date_complaint_received": "2024-01-20",
                "complaint_reported_by": "Pharmacist",
                "products_information": "Amitriptyline Tablets 10mg",
                "dosage_form": "Tablet",
                "market": "South Asia",
                "customer": "Retail Pharmacy Chain",
                "complainant_name": "Mr. John",
                "observation_time": "15:30:00",
            },
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "Market Complaint"
        assert "problem_statement" in data

    @pytest.mark.asyncio
    async def test_missing_event_type(self, client, setup_deps):
        """Test request without event_type parameter."""
        request_data = {
            "trackwise_fields": {
                "title": "Test",
                "description": "Test description",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_event_type(self, client, setup_deps):
        """Test request with invalid event type."""
        request_data = {
            "event_type": "InvalidType",
            "trackwise_fields": {
                "title": "Test",
                "description": "Test description",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_trackwise_fields(self, client, setup_deps):
        """Test request with empty trackwise_fields."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {}
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_trackwise_fields(self, client, setup_deps):
        """Test request without trackwise_fields."""
        request_data = {
            "event_type": "Deviation"
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_minimal_deviation_fields(self, client, setup_deps):
        """Test with minimal required fields for Deviation."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Test Deviation",
                "observation_date": "2024-01-15",
                "product_material_name": "Test Product",
                "description": "Test issue detected",
                "observed_by": "QA Person",
                "observation_time": "10:00:00",
                "is_microbial_em_failure": False,
                "responsible_department": "QA",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["problem_statement"]

    @pytest.mark.asyncio
    async def test_severity_critical_for_microbial_failure(self, client, setup_deps):
        """Test that microbial failure is marked as Critical severity."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Microbial Contamination",
                "observation_date": "2024-01-15",
                "product_material_name": "Test Product",
                "description": "Microbial contamination detected",
                "observed_by": "QA",
                "observation_time": "10:00:00",
                "is_microbial_em_failure": True,
                "responsible_department": "QA",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["severity_level"] == "Critical"

    @pytest.mark.asyncio
    async def test_severity_high_for_market_complaint(self, client, setup_deps):
        """Test that market complaint with customer is marked as High/Critical."""
        request_data = {
            "event_type": "Market Complaint",
            "trackwise_fields": {
                "title": "Product Quality Issue",
                "description": "Quality issue reported",
                "date_complaint_received": "2024-01-20",
                "complaint_reported_by": "Customer",
                "products_information": "Product A",
                "market": "International",
                "customer": "Major Hospital",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["severity_level"] in ["High", "Critical"]

    @pytest.mark.asyncio
    async def test_key_findings_extracted(self, client, setup_deps):
        """Test that key findings are properly extracted."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Test",
                "observation_date": "2024-01-15",
                "product_material_name": "Test Product",
                "description": "Test description",
                "equipment_name": "Test Equipment",
                "failure_duration": "2 hours",
                "observed_by": "QA",
                "observation_time": "10:00:00",
                "is_microbial_em_failure": False,
                "responsible_department": "QA",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert len(data["key_findings"]) > 0
        assert any("Product" in finding for finding in data["key_findings"])

    @pytest.mark.asyncio
    async def test_summary_truncation(self, client, setup_deps):
        """Test that summary is properly truncated."""
        long_description = "A" * 500
        request_data = {
            "event_type": "Market Complaint",
            "trackwise_fields": {
                "title": "Very long complaint",
                "description": long_description,
                "date_complaint_received": "2024-01-20",
                "complaint_reported_by": "Customer",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert len(data["summary"]) <= 203  # 200 chars + "..."

    @pytest.mark.asyncio
    async def test_special_characters_in_fields(self, client, setup_deps):
        """Test handling of special characters."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Test & Special @Characters",
                "observation_date": "2024-01-15",
                "product_material_name": "Product™ Name®",
                "description": "Issue with 50% failure rate (critical)",
                "observed_by": "Dr. John O'Brien",
                "observation_time": "10:00:00",
                "is_microbial_em_failure": False,
                "responsible_department": "QA/Dept",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unicode_characters(self, client, setup_deps):
        """Test handling of unicode characters."""
        request_data = {
            "event_type": "Market Complaint",
            "trackwise_fields": {
                "title": "Complaint from 中国 customer",
                "description": "Issue reported by café owner",
                "date_complaint_received": "2024-01-20",
                "complaint_reported_by": "François",
                "market": "Zürich",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_all_event_types_response_structure(self, client, setup_deps):
        """Test that all event types return consistent response structure."""
        event_types_data = {
            "Deviation": {
                "event_type": "Deviation",
                "trackwise_fields": {
                    "title": "Test",
                    "observation_date": "2024-01-15",
                    "product_material_name": "Test",
                    "description": "Test",
                    "observed_by": "QA",
                    "observation_time": "10:00:00",
                    "is_microbial_em_failure": False,
                    "responsible_department": "QA",
                }
            },
            "OOS": {
                "event_type": "OOS",
                "trackwise_fields": {
                    "title": "OOS",
                    "description": "OOS detected",
                    "observation_date": "2024-01-15",
                    "failure_type": "Test",
                    "analyst_name": "John",
                    "product_material_name": "Product",
                }
            },
            "OOT": {
                "event_type": "OOT",
                "trackwise_fields": {
                    "title": "OOT",
                    "description": "OOT detected",
                    "observation_date": "2024-01-15",
                    "failure_type": "Test",
                    "analyst_name": "John",
                    "product_material_name": "Product",
                }
            },
            "Market Complaint": {
                "event_type": "Market Complaint",
                "trackwise_fields": {
                    "title": "Complaint",
                    "description": "Complaint received",
                    "date_complaint_received": "2024-01-20",
                    "complaint_reported_by": "Customer",
                }
            }
        }

        expected_fields = ["event_type", "problem_statement", "summary", "severity_level", "key_findings"]

        for event_type, request_data in event_types_data.items():
            response = client.post("/ps/v2/generate", json=request_data)
            assert response.status_code == 200
            data = response.json()
            
            for field in expected_fields:
                assert field in data, f"Missing field {field} in {event_type} response"

    @pytest.mark.asyncio
    async def test_null_and_none_values(self, client, setup_deps):
        """Test handling of null/None values in fields."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Test",
                "observation_date": "2024-01-15",
                "product_material_name": "Test Product",
                "description": "Test",
                "observed_by": "QA",
                "observation_time": "10:00:00",
                "is_microbial_em_failure": False,
                "responsible_department": "QA",
                "batch_number": None,
                "related_customer": None,
                "equipment_name": None,
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_extra_fields_ignored(self, client, setup_deps):
        """Test that extra fields in trackwise_fields are handled gracefully."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Test",
                "observation_date": "2024-01-15",
                "product_material_name": "Test",
                "description": "Test",
                "observed_by": "QA",
                "observation_time": "10:00:00",
                "is_microbial_em_failure": False,
                "responsible_department": "QA",
                "extra_field_1": "should be ignored",
                "extra_field_2": 12345,
                "extra_nested": {"nested": "value"},
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_different_date_formats(self, client, setup_deps):
        """Test handling of different date formats."""
        request_data = {
            "event_type": "Deviation",
            "trackwise_fields": {
                "title": "Test",
                "observation_date": "15-01-2024",  # Different format
                "product_material_name": "Test",
                "description": "Test",
                "observed_by": "QA",
                "observation_time": "10:00:00",
                "is_microbial_em_failure": False,
                "responsible_department": "QA",
            }
        }

        response = client.post("/ps/v2/generate", json=request_data)
        assert response.status_code == 200
