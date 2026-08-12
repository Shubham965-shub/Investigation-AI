from typing import Dict, List, Tuple

from src.agents.rci_report.api.schemas.measure_analyze import (
    DetectabilityTier,
    GeneratedRiskFactors,
    RepeatabilityTier,
    RiskAssessmentCandidate,
    RiskAssessmentSection,
    RiskLevel,
    SeverityTier,
)

# Verbatim from the Word template (identical across Deviation/MC/OOS-OOT) — see
# rci_report_trackwise_fields.md §7. The LLM only picks a tier; these scores and
# the RPN/band computation below are never LLM-authored, to eliminate the risk
# of a self-reported arithmetic error needing a validate-and-retry cycle.
SEVERITY_SCORES: Dict[SeverityTier, int] = {"Critical": 27, "Medium": 10, "Low": 1}
REPEATABILITY_SCORES: Dict[RepeatabilityTier, int] = {"High": 10, "Medium": 5, "Low": 1}
DETECTABILITY_SCORES: Dict[DetectabilityTier, int] = {"High": 5, "Medium": 3, "Low": 1}


def score_rpn(
    severity_tier: SeverityTier, repeatability_tier: RepeatabilityTier, detectability_tier: DetectabilityTier
) -> Tuple[int, int, int, int, RiskLevel]:
    """Pure function: tiers in, (severity_score, repeatability_score,
    detectability_score, rpn, risk_level) out. No I/O, no LLM — trivially
    unit-testable and the single source of truth for RPN banding.
    """
    severity_score = SEVERITY_SCORES[severity_tier]
    repeatability_score = REPEATABILITY_SCORES[repeatability_tier]
    detectability_score = DETECTABILITY_SCORES[detectability_tier]
    rpn = severity_score * repeatability_score * detectability_score

    if rpn == 1:
        risk_level: RiskLevel = "L1"
    elif rpn < 10:
        risk_level = "L2"
    elif rpn < 27:
        risk_level = "L3"
    elif rpn < 300:
        risk_level = "L4"
    else:
        risk_level = "L5"

    return severity_score, repeatability_score, detectability_score, rpn, risk_level


def build_risk_assessment_section(generated: GeneratedRiskFactors) -> RiskAssessmentSection:
    """Combine the LLM's tier selections (generated, via get_structured_response
    against the GeneratedRiskFactors schema) with deterministically-computed
    scores/RPN/band from score_rpn() above."""
    candidates: List[RiskAssessmentCandidate] = []
    for label, factors in zip(generated.candidate_labels, generated.candidates):
        severity_score, repeatability_score, detectability_score, rpn, risk_level = score_rpn(
            factors.severity.tier, factors.repeatability.tier, factors.detectability.tier
        )
        candidates.append(
            RiskAssessmentCandidate(
                cause_label=label,
                factors=factors,
                severity_score=severity_score,
                repeatability_score=repeatability_score,
                detectability_score=detectability_score,
                rpn=rpn,
                risk_level=risk_level,
            )
        )

    return RiskAssessmentSection(
        applicability_reason=generated.applicability_reason,
        applicable=generated.applicable,
        candidates=candidates,
    )
