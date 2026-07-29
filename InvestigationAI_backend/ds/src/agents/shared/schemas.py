from pydantic import BaseModel, Field, ValidationError
from typing import Any, Dict, Optional


class DeviationTrackwiseFields(BaseModel):
    """Trackwise fields for Deviation events."""
    title: str = Field(..., description="Title of the deviation")
    batch_number_ar_number: str = Field(..., alias="Batch Number / AR Number")
    product_material_code: str = Field(..., alias="Product / Material Code")
    product_material_name: str = Field(..., alias="Product Name / Material Name")
    deviation_to: str = Field(..., alias="Deviation To")
    equipment_name: str = Field(..., alias="Equipment Name")
    description: str = Field(..., description="Description of the deviation")
    instrument_id_number: str = Field(..., alias="Instrument ID Number")
    name_of_the_instrument: str = Field(..., alias="Name of the Instrument")
    observed_by: str = Field(..., alias="Observed By")

class ExtendedDeviationTrackwiseFields(DeviationTrackwiseFields):
    deviation_number: str = Field(..., alias="Deviation Number")
    date_opened: str = Field(..., alias="Date Opened")
    observation_date: str = Field(..., alias="Observation Date")
    observation_time: str = Field(..., alias="Observation Time")
    failure_duration: str = Field(..., alias="Failure Duration")

    related_market: str = Field(..., alias="Related Market")
    related_customer: str = Field(..., alias="Related Customer")

    equipment_id: str = Field(..., alias="Equipment ID")
    equipment_number: str = Field(..., alias="Equipment Number")

    deviation_owner: str = Field(..., alias="Deviation Owner")
    originator: str = Field(..., alias="Originator")

    immediate_actions: list = Field(
        default_factory=list,
        alias="Immediate Actions"
    )

    impact_on_deviation_batches: str = Field(
        ...,
        alias="Impact on Deviation Batches"
    )

    impact_details: list = Field(
        default_factory=list,
        alias="Impact Details"
    )

    immediate_cause_known: str = Field(
        ...,
        alias="Immediate Cause Known"
    )

    cause_detail: str = Field(
        ...,
        alias="Cause Detail"
    )

    proposal_for_resolution: list = Field(
        default_factory=list,
        alias="Proposal for Resolution"
    )


class OOSTrackwiseFields(BaseModel):
    """Trackwise fields for OOS/OOT events."""
    title: str = Field(..., description="Title of the OOS/OOT")
    description: str = Field(...)
    observation_date: str = Field(..., alias="Observation Date")
    laboratory_details: str = Field(..., alias="Laboratory Details")
    specification_number: str = Field(..., alias="Specification Number")
    stability_condition: str = Field(..., alias="Stability Condition")
    stability_protocol_number: str = Field(..., alias="Stability Protocol Number")
    labelled_storage_conditions: str = Field(..., alias="Labelled Storage Conditions")
    failure_type: str = Field(..., alias="Failure type")
    observation_time: str = Field(..., alias="Observation Time")
    product_type: str = Field(..., alias="Product Type")
    stp_number: str = Field(..., alias="STP Number")
    stability_time_point: str = Field(..., alias="Stability Time Point")
    analyst_name: Optional[str] = Field(None, alias="Analyst Name")
    batch_number_ar_number: Optional[str] = Field(None, alias="Batch Number / AR Number")
    product_material_name: Optional[str] = Field(None, alias="Product Name / Material Name")
    batches_details: Optional[str] = Field(None, alias="Batches Details")
    instrument_id_number: Optional[str] = Field(None, alias="Instrument ID Number")
    product_material_code: Optional[str] = Field(None, alias="Product / Material Code")
    name_of_the_instrument: Optional[str] = Field(None, alias="Name of the Instrument")
    name_of_the_test: Optional[str] = Field(None, alias="Name of the Test")
    sample_number: Optional[str] = Field(None, alias="Sample Number")

    class Config:
        populate_by_name = True


class MarketComplaintTrackwiseFields(BaseModel):
    """Trackwise fields for Market Complaint events."""
    title: str = Field(...)
    date_complaint_received: str = Field(..., alias="Date Complaint Received")
    market_complaint_reported_by: str = Field(..., alias="Market Complaint Reported By")
    reference_complaint_number: str = Field(..., alias="Reference Complaint Number")
    description: str = Field(...)
    products_information: str = Field(..., alias="Products Information")
    dosage_form: str = Field(..., alias="Dosage Form")
    market: str = Field(..., alias="Market")
    product_manufacturing_info: str = Field(..., alias="Product Manufacturing Info")
    complainant_name: Optional[str] = Field(None, alias="Complainant Name")
    complaint_received_by: Optional[str] = Field(None, alias="Complaint Received By")
    customer: Optional[str] = Field(None, alias="Customer")
    complaint_country: Optional[str] = Field(None, alias="Complaint Country")
    complaint_number: Optional[str] = Field(None, alias="Complaint Number")

    class Config:
        populate_by_name = True


class ArchetypeInfo(BaseModel):
    id: Optional[int]
    name: str
    is_new: bool
    confidence_score: Optional[float] = Field(None)
    reasoning: Optional[str] = Field(None)


def validate_trackwise_fields(
    event_type: str,
    v: Dict[str, Any],
    event_functionality: Optional[str] = None,
    by_alias: bool = False,
) -> Dict[str, Any]:
    """Validate and normalise trackwise fields for the given event type."""
    event_type_lower = event_type.lower().strip()

    if event_type_lower == "deviation":
        if event_functionality == "rci_plan":
            schema = ExtendedDeviationTrackwiseFields
        else:
            schema = DeviationTrackwiseFields
    elif event_type_lower in ["oos", "oot", "oos/oot"]:
        schema = OOSTrackwiseFields
    elif event_type_lower == "market complaint":
        schema = MarketComplaintTrackwiseFields
    else:
        raise ValueError(
            f"Invalid event_type: {event_type}. "
            "Must be one of: Deviation, OOS, OOT, OOS/OOT, Market Complaint"
        )

    empty_fields = [
        field.alias or name
        for name, field in schema.model_fields.items()
        if field.is_required()
        and isinstance(v.get(field.alias or name), str)
        and not v.get(field.alias or name).strip()
    ]

    def display_name(loc_key: Any) -> Any:
        field = schema.model_fields.get(loc_key)
        return field.alias or loc_key if field else loc_key

    try:
        validated = schema(**v)
        result = validated.dict(by_alias=by_alias)
    except ValidationError as e:
        missing_fields = [
            display_name(err["loc"][0]) for err in e.errors() if err["type"] == "missing"
        ]
        other_errors = [
            f"{display_name(err['loc'][0])}: {err['msg']}"
            for err in e.errors()
            if err["type"] != "missing"
        ]
        details = []
        if empty_fields:
            details.append(f"empty fields: {', '.join(empty_fields)}")
        if missing_fields:
            details.append(f"missing required fields: {', '.join(missing_fields)}")
        if other_errors:
            details.append(f"invalid fields: {', '.join(other_errors)}")
        raise ValueError(f"Invalid trackwise fields for {event_type}: {'; '.join(details)}")
    except Exception as e:
        raise ValueError(f"Invalid trackwise fields for {event_type}: {e}")

    if empty_fields:
        raise ValueError(
            f"Invalid trackwise fields for {event_type}: "
            f"empty fields: {', '.join(empty_fields)}"
        )
    return result
