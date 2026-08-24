from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator

from src.agents.critique.api.schemas import CAPAItemDetail, TaskAssignmentItem
from src.agents.rci_plan.schemas import RciSectionItem
from src.agents.rci_report.api.schemas.common import CAPAExtrapolationItem, InterimControlItem
from src.agents.rci_report.api.schemas.response import AnnexuresSection, ApprovalSection
from src.agents.shared.schemas import validate_trackwise_fields

OverallVerdict = Literal["accept", "accept_with_comments", "rework"]


class AcceptedRCConclusion(BaseModel):
    """RC & CAPA Critique step output, RC half — the already-critiqued/accepted
    root cause conclusion. This module compiles it; it does not re-derive root
    cause from scratch.
    """
    rc_conclusion_text: str
    is_repeat_occurrence: Optional[bool] = None
    broad_category: Optional[str] = None
    category: Optional[str] = None
    root_cause_sub_category: Optional[str] = None
    overall_verdict: OverallVerdict = "accept"
    review_comments: List[str] = Field(default_factory=list)


class AcceptedCAPAProposal(BaseModel):
    """RC & CAPA Critique step output, CAPA half — the already-critiqued/accepted
    CAPA proposal. This module compiles it; it does not re-derive CAPA from scratch.
    """
    capa_items: List[CAPAItemDetail]
    capa_overall_text: Optional[str] = None
    interim_controls: List[InterimControlItem] = Field(default_factory=list)
    extrapolation: Optional[CAPAExtrapolationItem] = None
    capa_not_applicable_justification: Optional[str] = None
    overall_verdict: OverallVerdict = "accept"
    review_comments: List[str] = Field(default_factory=list)


class RciReportGenerationRequest(BaseModel):
    event_type: Literal["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"]
    # The id of the record this report is being generated for — used solely to
    # exclude this record from its own History Review "similar historical events"
    # search (a search seeded with this record's own description otherwise
    # self-matches with near-perfect relevance once the record itself is a row in
    # the searchable table). Not required for generation itself to succeed.
    deviation_id: Optional[str] = None
    trackwise_fields: Dict[str, Any]
    rci_plan_sections: List[RciSectionItem] = Field(default_factory=list)
    task_critique: List[TaskAssignmentItem] = Field(default_factory=list)
    accepted_rc_conclusion: AcceptedRCConclusion
    accepted_capa: AcceptedCAPAProposal
    # Gates Risk Assessment; None -> module defaults to "applicable" (the safer
    # default for a compliance report — see GAPS.md).
    mc_confirmed: Optional[bool] = None
    # Changed to 12 (2026-08-06, explicit request) — was 24 (UI's stated value;
    # emails only ever said "last 2 years" for a different, unrelated feature).
    # A request parameter, not a hardcoded constant, so it's changeable without
    # further code changes. See GAPS.md.
    history_lookback_months: int = 12
    # Investigator-provided text for fields with no TrackWise backing for this
    # event type (e.g. MC's primary_defect/nature_of_complaint, OOS/OOT's
    # immediate_actions). Keys documented in rci_report_trackwise_fields.md.
    manual_entries: Dict[str, str] = Field(default_factory=dict)
    approval_workflow: Optional[ApprovalSection] = None
    attachments: Optional[AnnexuresSection] = None

    @validator("trackwise_fields", pre=True)
    def _validate_trackwise_fields(cls, v, values):
        # strict=False: a missing/blank required field must not block the whole
        # report — generate_rci_report() attributes it to the specific
        # section(s) that need it instead (see _SECTION_REQUIRED_TW_FIELDS).
        return validate_trackwise_fields(
            event_type=values.get("event_type", ""),
            event_functionality="rci_report",
            v=v,
            by_alias=False,
            strict=False,
        )
