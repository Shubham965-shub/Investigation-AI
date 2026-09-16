"""Maps Trackwise's own status (dim_event.module) to a 0-6 "modules done"
stage. Used by the 4 module GET endpoints (read-only summary vs. editable
form/DS-generation) and by Action Center's per-row "X/6 steps" progress bar
(the sole source for that stage; the generated-content-table completion
count is no longer combined in). RC & CAPA Critique isn't one of the 6
MODULE_LABELS itself — reaching it implies stages 1-5 are done, same as
"Task Critique done", with RCI Report next. See STATUS_TO_STAGE for the
concrete mapping.
"""
from __future__ import annotations

from typing import Any, Dict

# Case/whitespace-insensitive (see stage_for). dim_event.module's text has
# already drifted once mid-project without a metadata change ("rci report
# generation" -> "RCI Report", same state) — both spellings kept for
# resilience. Don't guess new mappings without confirming with the data engineer.
STATUS_TO_STAGE: Dict[str, int] = {
    "interview questionnaire": 3,
    "rci plan": 4,
    "root cause and capa critique": 5,
    "rc & capa critique": 5,
    "rci report generation": 6,
    "rci report": 6,
}

MODULE_LABELS = [
    "Problem Statement",
    "Evidence Collection",
    "Interview Questionnaire",
    "RCI Plan Creation",
    "Task Critique",
    "RCI Report",
]


def stage_for(status: Any) -> int:
    if not isinstance(status, str):
        return 0
    return STATUS_TO_STAGE.get(status.strip().lower(), 0)


def next_module_label(stage: int) -> str:
    if stage >= len(MODULE_LABELS):
        return "Complete"
    return MODULE_LABELS[stage]
