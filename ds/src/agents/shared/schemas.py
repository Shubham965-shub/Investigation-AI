from pydantic import AliasChoices, BaseModel, Field, ValidationError
from typing import Any, Dict, List, Optional


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
    failure_type: Optional[str] = Field(None, alias="Failure type")
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
    # validation_alias accepts both the correct label and the old "Market
    # Complaint Reported By" label backend's field_mapping.py currently still
    # sends (see rci_plan/GAPS.md, 2026-08-09) — backend isn't ours to change
    # on our timeline, so ds tolerates either instead of depending on it being
    # updated. Output (by_alias=False in validate_trackwise_fields) is
    # unaffected either way: always the plain field name below.
    complaint_reported_by: str = Field(
        ...,
        alias="Complaint Reported By",
        validation_alias=AliasChoices("Complaint Reported By", "Market Complaint Reported By"),
    )
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


class RciReportDeviationTrackwiseFields(ExtendedDeviationTrackwiseFields):
    """Additional fields RCI Report generation needs on top of what RCI Plan needs.

    Everything here is Optional: rci_report_db_schema_findings.md confirmed several
    of these (risk_analysis, capa_details, capa_effectiveness) are empty even on a
    fully-complete real report, so treating them as required would hard-reject real
    production records the way validate_trackwise_fields' empty-string check does
    for required fields.
    """
    sub_area: Optional[str] = Field(None, alias="Sub Area")

    # immediate_actions is typed `list` on ExtendedDeviationTrackwiseFields, but the
    # live DB confirms it's a plain TEXT column (one narrative string, not an array)
    # — redeclared here to match reality, same fix already applied to
    # root_cause_conclusion/impact_details below.
    immediate_actions: Optional[str] = Field(None, alias="Immediate Actions")

    # The TW tab is literally "Immediate action & assessment" — a separate structured
    # Yes/No checklist alongside the free-text immediate_actions narrative above.
    # Never modeled until flagged missing (2026-08-03) — see GAPS.md. Modeled as raw
    # text (matching the live DB's own `immediate_actions_and_assessment` column,
    # which stores the 4 question/answer/explanation triples as one JSON-in-text
    # blob) rather than a nested Pydantic structure, consistent with how this module
    # treats other free-text TW fields.
    immediate_actions_and_assessment: Optional[str] = Field(
        None, alias="Immediate Actions And Assessment"
    )
    # Word template (Table 2, "Material / Product" grid) cites this + the segregation/
    # quarantine explanations above as the real source for quantity_on_hold — not a
    # generic TW dump. Confirmed live: text column, e.g. "7,84,301nos of tablets are
    # kept Quarantined." Never modeled until this cross-check (2026-08-03).
    qty_of_material_quarantined: Optional[str] = Field(
        None, alias="Qty Of Material Quarantined"
    )

    # "Affected Batches" grid (Deviation/OOS/OOT) and "Batches Details" grid (MC) —
    # confirmed live DB: text[] on both, populated for the affected/campaign batch(es).
    # Never modeled until this was flagged missing from Initial Impact Assessment's
    # material_product_impacts (2026-08-03) — see GAPS.md.
    affected_batches_product_material_name: List[str] = Field(
        default_factory=list, alias="Affected Batches Product Material Name"
    )
    affected_batches_batch_ar_number: List[str] = Field(
        default_factory=list, alias="Affected Batches Batch AR Number"
    )
    batches_details_product_or_material_name: List[str] = Field(
        default_factory=list, alias="Batches Details Product Or Material Name"
    )
    batches_details_batch_no_ar_no: List[str] = Field(
        default_factory=list, alias="Batches Details Batch No AR No"
    )

    # 3-tier root-cause taxonomy confirmed live (broad_category -> category ->
    # root_cause_sub_category). root_cause_category is NOT modeled: confirmed empty
    # across all 7,161 sample rows in rci_report_db_schema_findings.md — dead column.
    broad_category: Optional[str] = Field(None, alias="Broad Category")
    category: Optional[str] = Field(None, alias="Category")
    root_cause_sub_category: Optional[str] = Field(None, alias="Root Cause Sub Category")

    # Three overlapping severity fields exist live; criticality is the only one
    # confirmed populated on the one fully-complete example record — see
    # src/agents/rci_report/GAPS.md.
    classification: Optional[str] = Field(None, alias="Classification")
    criticality: Optional[str] = Field(None, alias="Criticality")
    final_deviation_classification: Optional[str] = Field(None, alias="Final Deviation Classification")

    # root_cause_conclusion and impact_details are typed `list` on
    # ExtendedDeviationTrackwiseFields (see immediate_actions above), but the live DB
    # confirms both are plain narrative TEXT columns (root_cause_conclusion in
    # particular is one blob spanning root cause + impact + risk + remedial action
    # concatenated) — redeclared here as Optional[str] to match reality.
    root_cause_conclusion: Optional[str] = Field(None, alias="Root Cause Conclusion")
    impact_details: Optional[str] = Field(None, alias="Impact Details")
    # Carries a raw TrackWise audit-log prefix baked into the value, e.g.
    # "10/31/2025 10:02 PM (GMT+5:30) added by R Anand (PID-008030): <text>" — strip
    # via text_cleaning.strip_audit_log_prefix() before use, never read raw.
    correction_or_remedial_action: Optional[str] = Field(None, alias="Correction or Remedial Action")

    # Confirmed empty in practice for a fully-complete example report. Captured here
    # in case a future TrackWise change populates them, but generation logic must
    # never depend on their presence — Risk Assessment and CAPA Effectiveness Check
    # Plan are synthesized from upstream evidence, never field-extracted.
    risk_analysis: Optional[str] = Field(None, alias="Risk Analysis")
    capa_details: Optional[str] = Field(None, alias="CAPA Details")
    capa_effectiveness: Optional[str] = Field(None, alias="CAPA Effectiveness")

    capa_number: List[str] = Field(default_factory=list, alias="CAPA Number")
    # TW Digital field: "CAPA & Change control – Related links & Related CAPA &
    # Related Change control" — a distinct linked-record type alongside Related CAPA,
    # confirmed cited in all three RCI Report Word templates but not previously modeled.
    related_change_control: List[str] = Field(default_factory=list, alias="Related Change Control")
    # DB: text[] — supports multiple markets/customers per CAPA extrapolation.
    # Overrides ExtendedDeviationTrackwiseFields' related_market/related_customer,
    # which are typed plain `str` there; that's a separate, pre-existing typing gap
    # on the base class, out of scope here (see GAPS.md).
    related_market: List[str] = Field(default_factory=list, alias="Related Market")
    related_customer: List[str] = Field(default_factory=list, alias="Related Customer")

    market: Optional[str] = Field(None, alias="Market")
    time_elapsed: Optional[str] = Field(None, alias="Time Elapsed")
    closure_days: Optional[str] = Field(None, alias="Closure Days")

    class Config:
        populate_by_name = True


class RciReportOOSTrackwiseFields(OOSTrackwiseFields):
    """Additional fields RCI Report generation needs for OOS/OOT events."""
    sub_area: Optional[str] = Field(None, alias="Sub Area")

    # "Affected Batches" grid (Deviation/OOS/OOT) and "Batches Details" grid (MC) —
    # confirmed live DB: text[] on both, populated for the affected/campaign batch(es).
    # Never modeled until this was flagged missing from Initial Impact Assessment's
    # material_product_impacts (2026-08-03) — see GAPS.md.
    affected_batches_product_material_name: List[str] = Field(
        default_factory=list, alias="Affected Batches Product Material Name"
    )
    affected_batches_batch_ar_number: List[str] = Field(
        default_factory=list, alias="Affected Batches Batch AR Number"
    )
    batches_details_product_or_material_name: List[str] = Field(
        default_factory=list, alias="Batches Details Product Or Material Name"
    )
    batches_details_batch_no_ar_no: List[str] = Field(
        default_factory=list, alias="Batches Details Batch No AR No"
    )
    broad_category: Optional[str] = Field(None, alias="Broad Category")
    category: Optional[str] = Field(None, alias="Category")
    root_cause_sub_category: Optional[str] = Field(None, alias="Root Cause Sub Category")
    classification: Optional[str] = Field(None, alias="Classification")
    criticality: Optional[str] = Field(None, alias="Criticality")
    final_deviation_classification: Optional[str] = Field(None, alias="Final Deviation Classification")
    root_cause_conclusion: Optional[str] = Field(None, alias="Root Cause Conclusion")
    impact_details: Optional[str] = Field(None, alias="Impact Details")
    correction_or_remedial_action: Optional[str] = Field(None, alias="Correction or Remedial Action")
    risk_analysis: Optional[str] = Field(None, alias="Risk Analysis")
    capa_details: Optional[str] = Field(None, alias="CAPA Details")
    capa_effectiveness: Optional[str] = Field(None, alias="CAPA Effectiveness")
    capa_number: List[str] = Field(default_factory=list, alias="CAPA Number")
    # TW Digital field: "CAPA & Change control – Related links & Related CAPA &
    # Related Change control" — a distinct linked-record type alongside Related CAPA,
    # confirmed cited in all three RCI Report Word templates but not previously modeled.
    related_change_control: List[str] = Field(default_factory=list, alias="Related Change Control")
    related_market: List[str] = Field(default_factory=list, alias="Related Market")
    related_customer: List[str] = Field(default_factory=list, alias="Related Customer")
    market: Optional[str] = Field(None, alias="Market")
    time_elapsed: Optional[str] = Field(None, alias="Time Elapsed")
    closure_days: Optional[str] = Field(None, alias="Closure Days")

    # OOS/OOT-specific fields not covered by the base OOSTrackwiseFields.
    oos_type: Optional[str] = Field(None, alias="OOS Type")
    oot_type: Optional[str] = Field(None, alias="OOT Type")
    causal_factor: Optional[str] = Field(None, alias="Causal Factor")
    repeat_occurrence: Optional[bool] = Field(None, alias="Repeat Occurrence")
    identified_root_cause: Optional[str] = Field(None, alias="Identified Root Cause")
    # Confirmed: no TrackWise field on Immediate Action for OOS/OOT — expect this to
    # arrive via RciReportGenerationRequest.manual_entries instead, never TrackWise.
    immediate_actions: Optional[str] = Field(None, alias="Immediate Actions")
    # See RciReportDeviationTrackwiseFields — same "Immediate action & assessment"
    # structured checklist, included here in case OOS/OOT ever populates it live;
    # not yet confirmed either way.
    immediate_actions_and_assessment: Optional[str] = Field(
        None, alias="Immediate Actions And Assessment"
    )
    qty_of_material_quarantined: Optional[str] = Field(
        None, alias="Qty Of Material Quarantined"
    )
    # Moved here from RciReportMarketComplaintTrackwiseFields 2026-08-09 — both
    # fields are cited by the templates as OOS/OOT sources ("QA Initial Review &
    # Assessment, fields Impact on Other Batches, Impact Justification" per
    # rci_report_trackwise_fields.md), and the route/prompt already labeled
    # impact_justification "OOS/OOT only" while it only actually existed on the MC
    # class — meaning validate_trackwise_fields silently dropped it on every real
    # OOS/OOT request before it ever reached the prompt. See GAPS.md.
    impact_on_other_batches: Optional[str] = Field(None, alias="Impact on Other Batches")
    impact_justification: Optional[str] = Field(None, alias="Impact Justification")

    class Config:
        populate_by_name = True


class RciReportMarketComplaintTrackwiseFields(MarketComplaintTrackwiseFields):
    """Additional fields RCI Report generation needs for Market Complaint events."""
    sub_area: Optional[str] = Field(None, alias="Sub Area")

    # "Affected Batches" grid (Deviation/OOS/OOT) and "Batches Details" grid (MC) —
    # confirmed live DB: text[] on both, populated for the affected/campaign batch(es).
    # Never modeled until this was flagged missing from Initial Impact Assessment's
    # material_product_impacts (2026-08-03) — see GAPS.md.
    affected_batches_product_material_name: List[str] = Field(
        default_factory=list, alias="Affected Batches Product Material Name"
    )
    affected_batches_batch_ar_number: List[str] = Field(
        default_factory=list, alias="Affected Batches Batch AR Number"
    )
    batches_details_product_or_material_name: List[str] = Field(
        default_factory=list, alias="Batches Details Product Or Material Name"
    )
    batches_details_batch_no_ar_no: List[str] = Field(
        default_factory=list, alias="Batches Details Batch No AR No"
    )
    # MC's own real "Product Information (1)" grid — was unconfirmed/disabled in the
    # DE pipeline as of 2026-08-03 (see GAPS.md), now re-enabled and confirmed live:
    # products_information_product_name_list / products_information_batch_name_list,
    # both text[]. batches_details_* above is actually OOS/OOT's grid, not MC's —
    # left in place (harmless) but MC should source from these instead.
    products_information_product_name_list: List[str] = Field(
        default_factory=list, alias="Products Information Product Name List"
    )
    products_information_batch_name_list: List[str] = Field(
        default_factory=list, alias="Products Information Batch Name List"
    )
    broad_category: Optional[str] = Field(None, alias="Broad Category")
    category: Optional[str] = Field(None, alias="Category")
    root_cause_sub_category: Optional[str] = Field(None, alias="Root Cause Sub Category")
    classification: Optional[str] = Field(None, alias="Classification")
    criticality: Optional[str] = Field(None, alias="Criticality")
    final_deviation_classification: Optional[str] = Field(None, alias="Final Deviation Classification")
    root_cause_conclusion: Optional[str] = Field(None, alias="Root Cause Conclusion")
    impact_details: Optional[str] = Field(None, alias="Impact Details")
    correction_or_remedial_action: Optional[str] = Field(None, alias="Correction or Remedial Action")
    risk_analysis: Optional[str] = Field(None, alias="Risk Analysis")
    capa_details: Optional[str] = Field(None, alias="CAPA Details")
    capa_effectiveness: Optional[str] = Field(None, alias="CAPA Effectiveness")
    capa_number: List[str] = Field(default_factory=list, alias="CAPA Number")
    # TW Digital field: "CAPA & Change control – Related links & Related CAPA &
    # Related Change control" — a distinct linked-record type alongside Related CAPA,
    # confirmed cited in all three RCI Report Word templates but not previously modeled.
    related_change_control: List[str] = Field(default_factory=list, alias="Related Change Control")
    related_market: List[str] = Field(default_factory=list, alias="Related Market")
    related_customer: List[str] = Field(default_factory=list, alias="Related Customer")
    market: Optional[str] = Field(None, alias="Market")
    time_elapsed: Optional[str] = Field(None, alias="Time Elapsed")
    closure_days: Optional[str] = Field(None, alias="Closure Days")

    # Market Complaint-specific fields. Several have no TrackWise field at all
    # (confirmed in rci_report_trackwise_fields.md) — expect these via
    # RciReportGenerationRequest.manual_entries, never assume TrackWise populates them.
    complaint_related_to: Optional[str] = Field(None, alias="Complaint Related To")   # no TW field
    primary_defect: Optional[str] = Field(None, alias="Primary Defect")               # no TW field
    nature_of_complaint: Optional[str] = Field(None, alias="Nature of Complaint")     # no TW field
    reserve_sample_observations: Optional[str] = Field(None, alias="Reserve Sample Observations")
    stability_review_comments: Optional[str] = Field(None, alias="Stability Review Comments")
    counterfeiting_details: Optional[str] = Field(None, alias="Counterfeiting Details")
    explanation_reg_notification: Optional[str] = Field(None, alias="Explanation - Reg. Notification")
    rationale_for_recall_decision: Optional[str] = Field(None, alias="Rationale for Recall decision")
    medical_investigation_summary: Optional[str] = Field(None, alias="Medical Investigation Summary")
    medical_impact_analysis: Optional[str] = Field(None, alias="Medical Impact Analysis")
    health_hazard_evaluation: Optional[str] = Field(None, alias="Health Hazard Evaluation")
    # impact_justification removed from here 2026-08-09 (moved to
    # RciReportOOSTrackwiseFields) — the templates never cite it as an MC-specific
    # field, only OOS/OOT; the route/prompt already only ever read it as "OOS/OOT
    # only". impact_on_other_batches stays here — the MC template independently
    # cites "Impact on Other Batches" under Preliminary Investigation. See GAPS.md.
    impact_on_other_batches: Optional[str] = Field(None, alias="Impact on Other Batches")

    class Config:
        populate_by_name = True


class ArchetypeInfo(BaseModel):
    id: Optional[int]
    name: str
    is_new: bool
    confidence_score: Optional[float] = Field(None)
    reasoning: Optional[str] = Field(None)


def _resolve_trackwise_schema(event_type: str, event_functionality: Optional[str] = None):
    event_type_lower = event_type.lower().strip()

    if event_type_lower == "deviation":
        if event_functionality == "rci_report":
            return RciReportDeviationTrackwiseFields
        elif event_functionality == "rci_plan":
            return ExtendedDeviationTrackwiseFields
        return DeviationTrackwiseFields
    elif event_type_lower in ["oos", "oot", "oos/oot"]:
        return RciReportOOSTrackwiseFields if event_functionality == "rci_report" else OOSTrackwiseFields
    elif event_type_lower == "market complaint":
        return (
            RciReportMarketComplaintTrackwiseFields
            if event_functionality == "rci_report"
            else MarketComplaintTrackwiseFields
        )
    raise ValueError(
        f"Invalid event_type: {event_type}. "
        "Must be one of: Deviation, OOS, OOT, OOS/OOT, Market Complaint"
    )


def validate_trackwise_fields(
    event_type: str,
    v: Dict[str, Any],
    event_functionality: Optional[str] = None,
    by_alias: bool = False,
    strict: bool = True,
) -> Dict[str, Any]:
    """Validate and normalise trackwise fields for the given event type.

    strict=False tolerates missing/blank required fields instead of raising —
    they're filled with "" so the model still constructs, and the normalised
    dict is returned as usual. Genuinely malformed fields (wrong type) still
    raise either way. Callers that want to know which required fields ended
    up missing/blank should check missing_required_trackwise_fields() against
    the returned dict.
    """
    schema = _resolve_trackwise_schema(event_type, event_functionality)

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

    patched = v
    if not strict:
        patched = dict(v)
        for name, field in schema.model_fields.items():
            alias = field.alias or name
            if field.is_required() and alias not in patched:
                patched[alias] = ""

    try:
        validated = schema(**patched)
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

    if empty_fields and strict:
        raise ValueError(
            f"Invalid trackwise fields for {event_type}: "
            f"empty fields: {', '.join(empty_fields)}"
        )
    return result


def missing_required_trackwise_fields(
    event_type: str,
    normalised_fields: Dict[str, Any],
    event_functionality: Optional[str] = None,
) -> List[str]:
    """Given the dict validate_trackwise_fields(..., by_alias=False) returned,
    lists which required fields (by attribute name) are still blank — for
    strict=False callers to attribute missing data to specific fields.
    """
    schema = _resolve_trackwise_schema(event_type, event_functionality)
    return sorted(
        name
        for name, field in schema.model_fields.items()
        if field.is_required() and not str(normalised_fields.get(name, "")).strip()
    )


def required_trackwise_fields(event_type: str, event_functionality: Optional[str] = None) -> List[str]:
    """Every required field name (by attribute name) for this event type's
    schema, populated or not — the total universe missing_required_trackwise_fields
    draws its "missing" subset from. Callers that need to distinguish "some
    required fields are blank" from "every relevant required field is blank"
    (rather than treating any single blank field as fatal) compare against this.
    """
    schema = _resolve_trackwise_schema(event_type, event_functionality)
    return sorted(name for name, field in schema.model_fields.items() if field.is_required())
