"""
Rubric configuration — the single source of truth for report scoring.

Encodes the two marking checklists as structured data:
  • Task Report Execution rubric (Task_Report_Execution_Rubric_40marks.docx) → section "task_report"
  • IQ Score rubric (IQ _ RC ,IMPACT & CAPA_revised .xlsx)                  → sections "rc", "impact", "capa"

The LLM only judges each checkpoint (verdict + rationale + evidence quote).
All marks and totals are computed HERE, deterministically, so scoring is
reproducible and auditable — the model never does arithmetic.

Scoring model (per the product decision): binary full-marks-or-zero per
checkpoint, except RC which is a single mutually-exclusive classification.

  • binary checkpoint  → verdict ∈ {"Yes", "No", "NA"}
        Yes → max_marks | No → 0 | NA (justified) → max_marks, counted as applicable
        (NA only allowed where allow_na=True; an unjustified/unpermitted NA claim
        is scored as No)
  • RC classification  → verdict ∈ {"assignable", "probable", "none"}
        assignable → 30 | probable → 20 | none → -5   (always applicable)
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
RC_TIERS: Dict[str, float] = {"assignable": 30.0, "probable": 20.0, "none": -5.0}


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
            "1", "2.2 Title & Objective Quality",
            "Title is clear and specific. It states what is being investigated.",
            4.0,
        ),
        Checkpoint(
            "2", "2.2 Title & Objective Quality",
            "Each task states a specific, answerable Objective linked to the problem / a "
            "hypothesis.",
            4.0,
        ),
        Checkpoint(
            "3", "3.1 Evidence & Objectivity",
            "Findings are supported by objective evidence and data (batch records, logbooks, "
            "trend data, interviews, reconstruction).",
            6.0,
        ),
        Checkpoint(
            "4", "3.1 Evidence & Objectivity",
            "Evidence both for and against is recorded. No cherry-picking. Findings state "
            "facts and are quantified where relevant.",
            4.0,
        ),
        Checkpoint(
            "5", "3.2 Completeness & Traceability",
            "Every part of the task is completed. Any gap is declared, not left open.",
            4.0,
        ),
        Checkpoint(
            "6", "3.2 Completeness & Traceability",
            "All data in the Findings can be traced to a source.",
            6.0,
        ),
        Checkpoint(
            "7", "4.1 Logical Linkage & Analytical Depth",
            "Inference follows logically from that task's findings. No unsupported "
            "conclusions.",
            4.0,
        ),
        Checkpoint(
            "8", "4.1 Logical Linkage & Analytical Depth",
            "Ruled-out causes are justified by the findings. Listed factors are examined "
            "(mark NA if not applicable).",
            4.0,
            allow_na=True,
        ),
        Checkpoint(
            "9", "4.1 Logical Linkage & Analytical Depth",
            "All inferences together give a complete, gap-free basis for the root cause. "
            "This is explained clearly even if the inference is no root cause.",
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
            "suggest a likely reason, scientifically justified (20); 'none' = no root cause "
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
        # 6.1 — Final Impact Assessment on Current Batches (max 4 = 2 + 1 + 1)
        Checkpoint(
            "6.1a", "6.1 Final Impact Assessment on Current Batches",
            "Impact on the current/affected batch(es) is accurately identified (patient "
            "safety, product quality, area compliance status or other status such as "
            "documentation) based on the nature of the non-conformance.",
            2.0,
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
            "The batch disposition decision is clearly written, if applicable (i.e. whether "
            "the non-conformance affects release of the current / other batches).",
            2.0,
            allow_na=True,
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
            "The correction addresses the non-conformance (if applicable).",
            1.0,
            allow_na=True,
        ),
        Checkpoint(
            "7.1b", "7.1 Remedial Action (Correction)",
            "Evidence / justification is provided for the correction done (if applicable).",
            1.0,
            allow_na=True,
        ),
        # CAPA consistency with the investigation (max 10)
        Checkpoint(
            "7.2", "7.2 Corrective Action / Preventive Action (CAPA)",
            "The CAPA is consistent with the problem statement and investigation findings, "
            "contradicting nothing established during the investigation.",
            10.0,
            allow_na=True,
        ),
        # Interim control (max 4)
        Checkpoint(
            "7.3", "7.2 Corrective Action / Preventive Action (CAPA)",
            "Interim control is explained appropriately with clear objectives, "
            "responsibilities and a timeline (or appropriate justification if not applicable).",
            4.0,
            allow_na=True,
        ),
        # CAPA scope extension (max 4)
        Checkpoint(
            "7.4", "7.2 Corrective Action / Preventive Action (CAPA)",
            "CAPA scope is extended to other products / area / equipment as applicable "
            "(or appropriate justification if not applicable).",
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
            return NA, cp.max_marks, True
        # NA not permitted here, or claimed without a real justification → treat as unmet
        return NO, 0.0, True
    return NO, 0.0, True
