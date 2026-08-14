from pydantic import BaseModel
from typing import List, Optional


class ExtractedTask(BaseModel):
    task_number: int
    title: str
    objective: str            # what this task aims to determine
    findings: str             # full factual findings, including inline table content
    inference: str            # concluding inference for this task
    section_labels: List[str]  # exact table/section header texts — used to map photos to tasks


class ExtractionResult(BaseModel):
    problem_statement: str
    objective: str
    tasks: List[ExtractedTask]


class SectionTasks(BaseModel):
    tasks: List[ExtractedTask]


class _ExtractionHeader(BaseModel):
    problem_statement: str
    objective: str


class ImageAnalysisResult(BaseModel):
    is_evidence_photo: bool
    observation: str
    compliance_concerns: str
    supports_written_claim: bool


class PreviousRecommendationCheck(BaseModel):
    """Forces an explicit, evidence-grounded verdict per previously accepted recommendation
    before the model writes `recommendations` (2026-08-14, per the user — mirrors the identical
    fix in api/schemas.py for RC & CAPA Critique: a bundled single-pass judgment on 'is this
    specific prior concern resolved?' proved imprecise in live testing there; duplicated here
    rather than imported since graph/ and api/ don't otherwise share schema code — see
    ds/src/agents/critique/GAPS.md)."""
    recommendation: str              # the previous recommendation being checked, verbatim
    resolved: bool                   # true only if the CURRENT report genuinely resolves it
    evidence: str                    # quote/reference to the specific current-report text the verdict rests on


class TaskCritiqueDetail(BaseModel):
    task_number: int
    title: str
    # Declared before `recommendations` so structured-output generation reasons through each
    # previously accepted item, with cited evidence, before writing the final list.
    previous_recommendation_checks: List[PreviousRecommendationCheck] = []
    recommendations: List[str]   # flat list of actionable recommendations, not tagged by dimension
    strengths: str                # 1-2 sentences on what was done well for this task


class AllTaskCritiquesResult(BaseModel):
    task_critiques: List[TaskCritiqueDetail]
    overall_report_summary: str


class TaskReportCritiqueResponse(BaseModel):
    problem_statement: str
    objective: str
    task_critiques: List[TaskCritiqueDetail]
    overall_report_summary: str
    total_tasks_analyzed: int
