from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class SourcedText(BaseModel):
    """Cross-cutting primitive for fields TrackWise doesn't back for every event
    type (e.g. MC's Primary Defect, OOS/OOT's Immediate Actions). Renders an
    explicit manual-entry state to the UI instead of a silently blank string.
    """
    value: str
    # Constrained to a Literal 2026-08-09 (was a free str) — nothing previously
    # stopped an off-vocabulary value (e.g. "TrackWise" capitalized) from silently
    # passing through and breaking any downstream logic keyed on this field. See
    # GAPS.md.
    source: Literal["trackwise", "manual_entry_required", "manual_entry_provided", "synthesized"] = Field(
        ...,
        description=(
            "'trackwise' (populated from a TrackWise field), "
            "'manual_entry_required' (no TrackWise field for this event type and "
            "no manual_entries override was supplied), 'manual_entry_provided' "
            "(no TrackWise field, but the caller supplied one via manual_entries), "
            "'synthesized' (composed/derived by the LLM from other inputs, not a "
            "single source field)."
        ),
    )


class InterimControlItem(BaseModel):
    description: str
    responsibility: str
    due_date: str  # literal date OR a status word, e.g. "Completed"


class CAPAExtrapolationItem(BaseModel):
    """Matches the live DB's actual shape: one row with array-valued columns
    (capa_number, related_customer, related_market are all text[]), not one row
    per customer/market/CAPA.
    """
    applicable: bool
    justification: str
    scope_description: str  # e.g. "all HDPE containers used for material storage and handling in OSD block"
    related_customers: List[str] = Field(default_factory=list)
    related_markets: List[str] = Field(default_factory=list)
    capa_numbers: List[str] = Field(default_factory=list)
    # TW Digital field: "Related CAPA & Related Change control" -- a distinct linked
    # record type from capa_numbers, cited alongside it in all three Word templates.
    related_change_controls: List[str] = Field(default_factory=list)
    responsibility: str
    due_date: str

    @model_validator(mode="after")
    def _justification_required_when_not_applicable(self):
        if not self.applicable and not self.justification.strip():
            raise ValueError("applicable is False but justification is empty")
        return self


class AnnexureItem(BaseModel):
    annexure_no: str
    title: str


class ApprovalRow(BaseModel):
    role: str
    name: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    signature_date: Optional[str] = None
