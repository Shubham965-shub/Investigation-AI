"""How many modules does Trackwise's own status (dim_event.module) imply are
already done.

Used by the 4 individual module GET endpoints (src/routers/{problem_statement,
evidence,questionnaire,rci_plan}.py) — when Trackwise's own status implies a
module is already complete, that module's page shows a read-only summary of
the real trackwise fields instead of an editable entry form / instead of
auto-generating content via DS, even when this app has never actually
generated anything for that record (2026-07-24 user decision — see project
memory: action_center_roles / module_progress_grouping for why this mapping
exists and its explicitly-placeholder nature).

Also used by the Action Center dashboard's per-investigation "X/6 steps"
progress bar AND the investigation preview side panel (both driven by the
same `stage`/`total_stages` values from src/routers/action_center.py) as of
2026-07-28 — this is now the SOLE source for that stage, not combined with
the generated-content-table completion count (fetch_module_completion() is
no longer called from action_center.py at all; kept defined in
action_center_queries.py in case it's needed again, per the user).

Real module workflow order (2026-07-28, per the user) and the "modules done"
count each real dim_event.module value implies — i.e. MODULE_LABELS position
+ 1, consistently:
  1 Problem Statement    (never observed live yet)
  2 Evidence Collection  (never observed live yet)
  3 Interview Questionnaire
  4 RCI Plan Creation (dim_event.module: "RCI Plan"/"rci plan")
  5 Task Critique (implied done once module reaches RC & CAPA Critique below
    — Task Critique itself has no distinct backing table/module value yet)
  [RC & CAPA Critique sits between Task Critique and RCI Report in the real
   workflow, but isn't one of the 6 MODULE_LABELS itself — reaching it means
   all of stages 1-5 above are done, so it maps to stage 5 same as "Task
   Critique done", with RCI Report next]
  6 RCI Report — reaching it means all 6 are done (next_module_label returns
    "Complete", not "RCI Report" — there's nothing left pending after this)
"""
from __future__ import annotations

from typing import Any, Dict

# Maps a dim_event.module value (case/whitespace-insensitive — see stage_for)
# to a 0-6 "modules done" stage. Extend this as new status values appear in
# the real DB — do not guess new mappings without confirming with the user/
# data engineer first. dim_event.module's real text has already drifted once
# mid-project without a corresponding etl_table_metadata timestamp change
# (2026-07-24: "rci report generation" -> 2026-07-28: "RCI Report", same
# underlying state, different spelling) — both spellings are kept here for
# resilience against a future revert, rather than assuming the latest text
# is permanent.
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
