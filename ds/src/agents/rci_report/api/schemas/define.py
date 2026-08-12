from typing import List, Literal

from pydantic import BaseModel, model_validator

from src.agents.rci_report.api.schemas.common import SourcedText


class ExecutiveSummarySection(BaseModel):
    """Rollup of the 6 bullets confirmed in the real UI example. Pure synthesis —
    generated last (Wave 2), from every other section's already-finished output.
    """
    summary: str  # short rollup: product/batch, defect, root cause, key measurement
    problem_description: str
    immediate_containment_action: str
    determination_of_root_cause: str  # HOW it was found (narrative), not the conclusion itself
    root_cause_probable_cause_statement: str  # WHAT the cause is (short statement)
    impact_assessment: str
    correction_conclusion_preventive_actions: str  # merges Correction/Remedial + CAPA, per confirmed UI
    # Added 2026-08-09: confirmed by two real reports (Deviation + MC) rendering a
    # final disposition bullet the Word templates never ask for in Executive Summary
    # — see GAPS.md. Sourced from ImpactAssessmentBatchDispositionSection.conclusion,
    # already in this prompt's context.
    conclusion_statement: str


class DescriptionOfEventSection(BaseModel):
    what_happened: str
    when_happened: str  # fused, per confirmed UI: "On 24/10/2025 at 01:30 hrs."
    who_identified: str  # redaction policy unresolved (see GAPS.md) — plain str, not split into name/id/role
    where_it_happened: str  # area + line/equipment id fused, per confirmed UI
    nonconforming_reference: SourcedText  # non-conformance statement + linked spec/standard; manual entry for MC
    how_detected: SourcedText  # manual entry for MC


ImpactType = Literal["Direct", "Indirect", "Not applicable"]


class MaterialProductImpactItem(BaseModel):
    material_product_batch: str  # e.g. "Lamotrigine Tablets 200 mg, batch# 7263940" — name+batch fused, per confirmed UI
    stage: str
    quantity_involved: str
    quantity_on_hold: SourcedText  # no TW field for MC/OOS-OOT — manual entry
    type_of_impact: ImpactType


class EquipmentActionChecklist(BaseModel):
    """Fixed 3-item checklist confirmed from the real UI, not an open list."""
    operation_suspended: bool
    on_hold_label_affixed: bool
    other_action_taken: bool
    other_action_specify: str = ""

    @model_validator(mode="after")
    def _specify_requires_other(self):
        if self.other_action_taken and not self.other_action_specify.strip():
            raise ValueError("other_action_taken is True but other_action_specify is empty")
        if not self.other_action_taken and self.other_action_specify.strip():
            raise ValueError("other_action_specify is set but other_action_taken is False")
        return self


class EquipmentImpactItem(BaseModel):
    equipment_instrument: SourcedText  # entirely manual entry for MC — "Write Manually" for every field
    identification_number: SourcedText
    actions_initiated: EquipmentActionChecklist


class InitialImpactAssessmentSection(BaseModel):
    material_product_impacts: List[MaterialProductImpactItem]
    equipment_impacts: List[EquipmentImpactItem]
    immediate_actions: List[str]  # discrete bulleted items, per confirmed UI — never one blob
