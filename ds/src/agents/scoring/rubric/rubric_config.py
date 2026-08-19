"""
Rubric configuration — the single source of truth for report scoring.

Encodes the two marking checklists as structured data:
  • Task Report Execution rubric (Task_Report_Execution_Rubric_40marks.docx) → section "task_report"
  • IQ Score rubric (IQ _ RC ,IMPACT & CAPA .xlsx)                          → sections "rc", "impact", "capa"

The LLM only judges each checkpoint (verdict + rationale + evidence quote).
All marks and totals are computed HERE, deterministically, so scoring is
reproducible and auditable — the model never does arithmetic.

Scoring model (per the product decision): binary full-marks-or-zero per
checkpoint, except RC which is a single mutually-exclusive classification.

  • binary checkpoint  → verdict ∈ {"Yes", "No", "NA"}
        Yes → max_marks | No → 0 | NA → excluded from numerator AND denominator
        (NA only allowed where allow_na=True)
  • RC classification  → verdict ∈ {"assignable", "probable", "none"}
        assignable → 30 | probable → 10 | none → -5   (always applicable)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Verdict constants ──────────────────────────────────────────────────────────
YES = "Yes"
NO = "No"
NA = "NA"
BINARY_VERDICTS = frozenset({YES, NO, NA})

# RC classification tiers (mutually exclusive)
RC_TIERS: Dict[str, float] = {"assignable": 30.0, "probable": 10.0, "none": -5.0}

# CAPA 7.2 effectiveness levels (mutually exclusive). Marks per the checklist's
# Max-Score column: L1=4, L2=4, L3=8, L4=10, L5=10; 'none' = no adequate CAPA.
CAPA_LEVELS: Dict[str, float] = {
    "none": 0.0,
    "level_1": 4.0,
    "level_2": 4.0,
    "level_3": 8.0,
    "level_4": 10.0,
    "level_5": 10.0,
}


@dataclass(frozen=True)
class Checkpoint:
    """One scoreable line in a checklist."""

    id: str                      # stable id, e.g. "3.1a" or "1"
    sub_criteria: str            # grouping label, e.g. "3.1 Evidence & Objectivity"
    text: str                    # what the checkpoint asks for
    max_marks: float             # marks awarded when satisfied
    kind: str = "binary"         # "binary" | "classification"
    allow_na: bool = False       # whether NA is a permitted verdict
    tiers: Optional[Dict[str, float]] = None  # for kind="classification"


@dataclass(frozen=True)
class SectionSpec:
    section: str                 # "task_report" | "rc" | "impact" | "capa"
    label: str
    native_max: float            # total as printed on the checklist (for display/labelling)
    checkpoints: List[Checkpoint] = field(default_factory=list)

    @property
    def achievable_max(self) -> float:
        """Sum of positive checkpoint maxima — the max a report can actually earn."""
        return sum(cp.max_marks for cp in self.checkpoints)


# ── Task Report Execution rubric (/40) ─────────────────────────────────────────
_TASK_REPORT = SectionSpec(
    section="task_report",
    label="Task Report Execution",
    native_max=40.0,
    checkpoints=[
        Checkpoint(
            "2.2a", "2.2 Title & Objective Quality",
            "Each investigation task has a clear, specific Title that identifies what is "
            "being investigated.",
            4.0,
        ),
        Checkpoint(
            "2.2b", "2.2 Title & Objective Quality",
            "Each task states a specific, answerable Objective linked to the problem or a "
            "hypothesis.",
            4.0,
        ),
        Checkpoint(
            "3.1a", "3.1 Evidence & Objectivity",
            "Findings are supported by objective evidence & data (records, logbooks, trend "
            "data, interviews, reconstruction) rather than unsupported assertions.",
            6.0,
        ),
        Checkpoint(
            "3.1b", "3.1 Evidence & Objectivity",
            "Both confirming and disconfirming evidence is captured (no cherry-picking); "
            "findings state fact and are quantified where relevant.",
            4.0,
        ),
        Checkpoint(
            "3.2a", "3.2 Completeness & Traceability",
            "Each task's stated Objective is actually answered by its Findings — the task is "
            "executed to closure, not left open.",
            4.0,
        ),
        Checkpoint(
            "3.2b", "3.2 Completeness & Traceability",
            "Data / evidence in the Findings is traceable to authenticated source records "
            "(ALCOA+).",
            6.0,
        ),
        Checkpoint(
            "4.1a", "4.1 Logical Linkage & Analytical Depth",
            "Each Inference follows logically from that task's Findings (no leaps or "
            "unsupported conclusions).",
            4.0,
        ),
        Checkpoint(
            "4.1b", "4.1 Logical Linkage & Analytical Depth",
            "Ruled-out lines are justified by findings; the inference reaches a systemic "
            "level; underlying systemic contributors are examined.",
            4.0,
            allow_na=True,
        ),
        Checkpoint(
            "4.1c", "4.1 Logical Linkage & Analytical Depth",
            "The inferences collectively provide a coherent, gap-free basis for the "
            "root-cause determination.",
            4.0,
        ),
    ],
)

# ── RC / Probable Causes (/30) ─────────────────────────────────────────────────
_RC = SectionSpec(
    section="rc",
    label="Root Cause / Probable Causes",
    native_max=30.0,
    checkpoints=[
        Checkpoint(
            "1", "1 Root Cause / Probable Causes",
            "Classify the root-cause conclusion: 'assignable' = proven through evidence, "
            "reproducible, direct linkage established (30); 'probable' = evidence/data "
            "suggest a likely reason, scientifically justified (10); 'none' = no root cause "
            "established (-5).",
            30.0,
            kind="classification",
            tiers=dict(RC_TIERS),
        ),
    ],
)

# ── Final Impact Assessment (/10) ──────────────────────────────────────────────
_IMPACT = SectionSpec(
    section="impact",
    label="Final Impact Assessment",
    native_max=10.0,
    checkpoints=[
        # 6.1 — Final Impact Assessment on Current Batches (max 4 = 4 rows × 1)
        Checkpoint(
            "6.1a", "6.1 Final Impact Assessment on Current Batches",
            "Impact on the current/affected batch(es) is accurately identified (patient "
            "safety, product quality, area compliance status or other status such as "
            "documentation) based on the nature of the non-conformance.",
            1.0,
        ),
        Checkpoint(
            "6.1b", "6.1 Final Impact Assessment on Current Batches",
            "Where patient safety is impacted and the product is in market, the "
            "health-hazard-evaluation (HHE) requirement has been checked — or it is "
            "appropriately reasoned that HHE is not required.",
            1.0,
        ),
        Checkpoint(
            "6.1c", "6.1 Final Impact Assessment on Current Batches",
            "Where product quality / patient safety is impacted, the requirement of "
            "regulatory submission / market notification has been evaluated — or it is "
            "appropriately reasoned that none is required.",
            1.0,
        ),
        Checkpoint(
            "6.1d", "6.1 Final Impact Assessment on Current Batches",
            "Where product quality or regulatory compliance is impacted, continuation of "
            "production in similar areas/sites has been evaluated — or it is appropriately "
            "reasoned as not applicable.",
            1.0,
        ),
        # 6.2 — Extended Impact Assessment (max 4 = 2 rows × 2)
        Checkpoint(
            "6.2a", "6.2 Extended Impact Assessment",
            "Impact on other batches / area / process / products / systems has been mentioned "
            "with rationale (patient safety, product quality, compliance, documentation) — or, "
            "if there is no impact on other product, that has been stated.",
            2.0,
        ),
        Checkpoint(
            "6.2b", "6.2 Extended Impact Assessment",
            "If only the current batch/area/process is impacted and there is no impact on other "
            "batches, the rationale for the same has been mentioned.",
            2.0,
        ),
        # 6.3 — Batch Disposition (max 2 = 1 row × 2)
        Checkpoint(
            "6.3", "6.3 Batch Disposition",
            "The batch disposition decision is clearly written (i.e. whether the "
            "non-conformance affects release of the current / other batches).",
            2.0,
        ),
    ],
)

# ── Effectiveness of Corrections and CAPA (/20) ────────────────────────────────
_CAPA = SectionSpec(
    section="capa",
    label="Effectiveness of Corrections and CAPA",
    native_max=20.0,
    checkpoints=[
        # 7.1 — Remedial action / Correction (max 2 = 2 rows × 1)
        Checkpoint(
            "7.1a", "7.1 Remedial Action (Correction)",
            "The correction / remedial action addresses the effect of the non-conformance "
            "based on its nature and root cause (what, where documented, who, by when) — or a "
            "rationale is given if no correction is recommended.",
            1.0,
        ),
        Checkpoint(
            "7.1b", "7.1 Remedial Action (Correction)",
            "Evidence / justification is provided that the correction does not adversely "
            "affect product quality and allows the product to meet specifications.",
            1.0,
        ),
        # 7.2 — CAPA effectiveness level (max 10; pick one level)
        Checkpoint(
            "7.2", "7.2 Corrective Action / Preventive Action (CAPA)",
            "Classify the CAPA proposed against the identified root cause by its effectiveness "
            "level (marks: Level 1=4, Level 2=4, Level 3=8, Level 4=10, Level 5=10). Use "
            "'none' when there is no adequate CAPA. Higher levels are more robust / systemic; "
            "see the level definitions in the CAPA prompt.",
            10.0,
            kind="classification",
            tiers=dict(CAPA_LEVELS),
        ),
        # Interim control (max 4)
        Checkpoint(
            "7.3", "7.2 Corrective Action / Preventive Action (CAPA)",
            "Interim control is explained appropriately with clear objectives, "
            "responsibilities and a timeline (or appropriate justification if not applicable).",
            4.0,
            allow_na=True,
        ),
        # CAPA effectiveness check (max 4)
        Checkpoint(
            "7.4", "7.2 Corrective Action / Preventive Action (CAPA)",
            "CAPA effectiveness check is explained appropriately with clear objectives, "
            "responsibilities and a timeline (or appropriate justification if not applicable).",
            4.0,
            allow_na=True,
        ),
    ],
)

# ── Registry ───────────────────────────────────────────────────────────────────
SECTIONS: Dict[str, SectionSpec] = {
    s.section: s for s in (_TASK_REPORT, _RC, _IMPACT, _CAPA)
}

# Sections that are scored together in the single "IQ" LLM call and that make up
# the "IQ Score /60" total on the source checklist.
IQ_SECTIONS: tuple[str, ...] = ("rc", "impact", "capa")
TASK_REPORT_SECTION = "task_report"

ALL_SECTION_KEYS: tuple[str, ...] = ("task_report", "rc", "impact", "capa")


def get_section(section: str) -> SectionSpec:
    if section not in SECTIONS:
        raise KeyError(f"Unknown rubric section: {section!r}")
    return SECTIONS[section]


# ── Marks resolution ───────────────────────────────────────────────────────────

def clamp_percentage(value: float) -> float:
    """Bound a percentage to [0, 100] and round to 2 dp (RC 'none' can go negative)."""
    return round(max(0.0, min(100.0, value)), 2)


def _is_justified_na(rationale: str) -> bool:
    """True if `rationale` explains the non-applicability rather than just
    restating the NA verdict itself (e.g. a bare "NA" / "Not applicable")."""
    norm = re.sub(r"[^a-z]", "", rationale.lower())
    return bool(norm) and norm not in ("na", "notapplicable", "nonapplicable")


def resolve_checkpoint(cp: Checkpoint, verdict: str, rationale: str = "") -> tuple[str, float, bool]:
    """
    Map a raw LLM verdict to (normalised_verdict, marks_awarded, is_applicable).

    Unknown/blank verdicts are treated conservatively as the worst applicable
    outcome (No for binary, 'none' for RC) so a malformed model reply can never
    silently inflate a score. Likewise, a checkpoint claimed "NA" without a
    substantive `rationale` is not excused from scoring — it is scored as unmet.
    """
    raw = (verdict or "").strip()

    if cp.kind == "classification":
        tiers = cp.tiers or {}
        # Tolerate decorated verdicts, e.g. "Assignable (proven)" → 'assignable',
        # "CAPA Level 3" → 'level_3'. Digit-aware and negation-safe (must START
        # with the tier); unrecognised → the lowest-marks (conservative) tier.
        norm = re.sub(r"[^a-z0-9]", "", raw.lower())

        def _nk(k: str) -> str:
            return re.sub(r"[^a-z0-9]", "", k.lower())

        key = next((k for k in tiers if norm == _nk(k)), None)
        if key is None:
            starts = sorted((k for k in tiers if _nk(k) and norm.startswith(_nk(k))),
                            key=lambda k: -len(_nk(k)))
            key = starts[0] if starts else None
        # Contains-match (e.g. "capalevel3" → level_3), but skip when the verdict
        # is negated ("not ...", "no ...") so RC "not assignable" stays 'none'.
        if key is None and "not" not in norm and not norm.startswith("no"):
            has = sorted((k for k in tiers if _nk(k) and _nk(k) in norm),
                         key=lambda k: -len(_nk(k)))
            key = has[0] if has else None
        if key is None:
            key = min(tiers, key=lambda k: tiers[k])  # conservative default
            logger.warning("Classification verdict %r for %s not recognised; defaulting to %r.",
                           verdict, cp.id, key)
        return key, tiers[key], True

    # binary
    low = raw.lower()
    if low in ("yes", "y", "true", "pass"):
        return YES, cp.max_marks, True
    if low in ("na", "n/a", "not applicable"):
        if cp.allow_na and _is_justified_na(rationale):
            return NA, 0.0, False
        # NA not permitted here, or claimed without a real justification → treat as unmet
        return NO, 0.0, True
    return NO, 0.0, True
