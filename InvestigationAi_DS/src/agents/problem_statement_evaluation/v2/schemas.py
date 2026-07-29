"""
V2 Schemas for structured problem statement generation.
Input based on trackwise field requirements and event types.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any


class DeviationTrackwiseFields(BaseModel):
    """Trackwise fields for Deviation events (Excel-aligned)."""
    title: str = Field(..., description="Title of the deviation")
    batch_number_ar_number: str = Field(..., alias="Batch Number / AR Number", description="Batch Number / AR Number")
    product_material_code: str = Field(..., alias="Product / Material Code", description="Product / Material Code")
    product_material_name: str = Field(..., alias="Product Name / Material Name", description="Product Name / Material Name")
    deviation_to: str = Field(..., alias="Deviation To", description="Deviation To")
    equipment_name: str = Field(..., alias="Equipment Name", description="Equipment Name")
    description: str = Field(..., description="Description of the deviation")
    instrument_id_number: str = Field(..., alias="Instrument ID Number", description="Instrument ID Number")
    name_of_the_instrument: str = Field(..., alias="Name of the Instrument", description="Name of the Instrument")
    observed_by: str = Field(..., alias="Observed By", description="Observed By")
    # observation_date: str = Field(..., description="Date of observation (YYYY-MM-DD)")  # EXTRA, commented out
    # failure_duration: str = Field(..., description="Duration of failure")  # EXTRA, commented out
    # related_market: str = Field(..., description="Related Market")  # EXTRA, commented out
    # related_customer: str = Field(..., description="Related Customer")  # EXTRA, commented out
    # observation_time: str = Field(..., description="Time of observation (HH:MM:SS)")  # EXTRA, commented out
    # is_microbial_em_failure: bool = Field(..., description="Is it a Microbial EM Failure?")  # EXTRA, commented out
    # responsible_department: Optional[str] = Field(None, description="Responsible Department")  # EXTRA, commented out


class OOSTrackwiseFields(BaseModel):
    """Trackwise fields for OOS/OOT events (Excel-aligned)."""
    title: str = Field(..., description="Title of the OOS/OOT")
    description: str = Field(..., description="Detailed description")
    observation_date: str = Field(..., description="Observation Date")
    laboratory_details: str = Field(..., alias="Laboratory Details", description="Laboratory Details")
    specification_number: str = Field(..., alias="Specification Number", description="Specification Number")
    stability_condition: str = Field(..., alias="Stability Condition", description="Stability Condition")
    stability_protocol_number: str = Field(..., alias="Stability Protocol Number", description="Stability Protocol Number")
    labelled_storage_conditions: str = Field(..., alias="Labelled Storage Conditions", description="Labelled Storage Conditions")
    failure_type: str = Field(..., alias="Failure type", description="Failure type")
    observation_time: str = Field(..., alias="Observation Time", description="Observation Time")
    product_type: str = Field(..., alias="Product Type", description="Product Type")
    stp_number: str = Field(..., alias="STP Number", description="STP Number")
    stability_time_point: str = Field(..., alias="Stability Time Point", description="Stability Time Point")
    analyst_name: Optional[str] = Field(None, alias="Analyst Name", description="Analyst Name")
    batch_number_ar_number: Optional[str] = Field(None, alias="Batch Number / AR Number", description="Batch Number / AR Number")
    product_material_name: Optional[str] = Field(None, alias="Product Name / Material Name", description="Product Name / Material Name")
    batches_details: Optional[str] = Field(None, alias="Batches Details", description="Batches Details")
    instrument_id_number: Optional[str] = Field(None, alias="Instrument ID Number", description="Instrument ID Number")
    product_material_code: Optional[str] = Field(None, alias="Product / Material Code", description="Product / Material Code")
    name_of_the_instrument: Optional[str] = Field(None, alias="Name of the Instrument", description="Name of the Instrument")
    name_of_the_test: Optional[str] = Field(None, alias="Name of the Test", description="Name of the Test")
    sample_number: Optional[str] = Field(None, alias="Sample Number", description="Sample Number")
    # related_market: str = Field(..., description="Related Market")  # EXTRA, commented out
    # related_customer: str = Field(..., description="Related Customer")  # EXTRA, commented out
    # test_name: Optional[str] = Field(None, description="Name of the Test")  # Renamed to name_of_the_test


class MarketComplaintTrackwiseFields(BaseModel):
    """Trackwise fields for Market Complaint events (Excel-aligned)."""
    title: str = Field(..., description="Title of the complaint")
    date_complaint_received: str = Field(..., alias="Date Complaint Received", description="Date Complaint Received")
    market_complaint_reported_by: str = Field(..., alias="Market Complaint Reported By", description="Market Complaint Reported By")
    reference_complaint_number: str = Field(..., alias="Reference Complaint Number", description="Reference Complaint Number")
    description: str = Field(..., description="Description of the complaint")
    products_information: str = Field(..., alias="Products Information", description="Products Information")
    dosage_form: str = Field(..., alias="Dosage Form", description="Dosage Form")
    market: str = Field(..., alias="Market", description="Market")
    product_manufacturing_info: str = Field(..., alias="Product Manufacturing Info", description="Product Manufacturing Info")
    complainant_name: str = Field(..., alias="Complainant Name", description="Complainant Name")
    complaint_received_by: str = Field(..., alias="Complaint Received By", description="Complaint Received By")
    customer: str = Field(..., alias="Customer", description="Customer")
    complaint_country: str = Field(..., alias="Complaint Country", description="Complaint Country")
    complaint_number: Optional[str] = Field(None, alias="Complaint Number", description="Complaint Number")
    # product_manufacture_info: str = Field(..., description="Product Manufacturing Information")  # Renamed to product_manufacturing_info


class ProblemStatementGenerationRequest(BaseModel):
    """Request to generate structured problem statement."""
    event_type: Literal["Deviation", "OOS", "OOT", "Market Complaint"]
    trackwise_fields: Dict[str, Any] = Field(
        ...,
        description="Dictionary of trackwise fields based on event type"
    )


class ProblemStatementGenerationResponse(BaseModel):
    """Response with generated problem statement."""
    event_type: str = Field(..., description="Type of event")
    problem_statement: str = Field(
        ...,
        description="Generated structured problem statement"
    )