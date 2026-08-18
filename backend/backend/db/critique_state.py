"""Shared upload/lock/status state machine for both Task Critique and
RC & CAPA Critique. Extracted so the identical business rule (per the user,
2026-08-05, reaffirmed 2026-08-06 for RC & CAPA) isn't duplicated:
  - 3 uploads total, then locked regardless of remaining rejected
    recommendations.
  - Reupload is only possible once EVERY recommendation on the latest report
    has been decided (accepted or rejected) — a single reject with other
    recommendations still pending does not unlock it (per the user,
    2026-08-07). Once fully decided, any rejection present flips can_upload
    True.
  - If a report's recommendations end up ALL rejected, the *next* upload is
    a "gospel" report — no critique, locks immediately.

This function is deliberately agnostic to what a "recommendation" belongs to
(a single category for Task Critique, or flattened across two categories for
RC & CAPA Critique) — callers flatten whatever they have into one
recommendations list per report before calling this.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

MAX_UPLOADS = 3


def compute_upload_state(latest: Optional[Dict[str, Any]], upload_count: int) -> Dict[str, Any]:
    """`latest` is the most recent report (or the only one, for callers that
    no longer keep prior-attempt history) — a dict with at least
    `is_gospel: bool` and `recommendations: list[{"decision": ...}]` (already
    flattened across however many critique categories the caller has).
    `upload_count` is the caller's own attempt counter, since it can no
    longer always be inferred from how many report rows exist."""
    if latest is None or upload_count == 0:
        return {
            "status": "pending",
            "upload_count": 0,
            "locked": False,
            "can_upload": True,
            "next_upload_is_final": False,
            "latest": None,
        }

    if latest["is_gospel"]:
        return {
            "status": "complete",
            "upload_count": upload_count,
            "locked": True,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }

    if latest.get("critique_failed"):
        # Rejected outright — wrong report format, or DS found nothing real to
        # critique (see task_report_format.py / the total_tasks_analyzed==0
        # check in routers/task_critique.py) — never a genuine critique, so it
        # must not lock the section or block a reupload (2026-08-14, per the
        # user: uploading the wrong file must still leave the door open to
        # upload the correct one). Falls through to here rather than the
        # "not recs" branch below, which would otherwise treat this the same
        # as "critique not back yet" and never let go — RC & CAPA reports have
        # no critique_failed column, so `.get` is always falsy there and this
        # branch is unreachable for that caller.
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": True,
            "next_upload_is_final": False,
            "latest": latest,
        }

    recs = latest["recommendations"]
    if not recs:
        # Critique not back yet (or DS not wired up yet) — nothing to decide.
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }

    decisions = {r["decision"] for r in recs}
    if upload_count >= MAX_UPLOADS:
        # Final attempt consumed — locked regardless of remaining decision mix.
        return {
            "status": "complete",
            "upload_count": upload_count,
            "locked": True,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }
    if "pending" in decisions:
        # At least one recommendation is still undecided — no reupload until
        # every single one has been accepted or rejected (per the user,
        # 2026-08-07), even if some have already been rejected.
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }
    if decisions == {"rejected"}:
        # Every recommendation rejected — the already-uploaded report is
        # immediately treated as final and locked (2026-08-14, per the user),
        # rather than requiring a further no-critique "gospel" upload. The
        # report itself was still genuinely critiqued (unlike a real gospel
        # upload), so `is_gospel` on the row stays False — callers score it
        # the same way a gospel/3rd-attempt report gets scored.
        return {
            "status": "complete",
            "upload_count": upload_count,
            "locked": True,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }
    if "rejected" in decisions:
        # Mixed accept/reject, not all rejected — reupload stays optional
        # (not required); the next upload would be a normal, freshly-critiqued
        # attempt, not gospel.
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": True,
            "next_upload_is_final": False,
            "latest": latest,
        }
    # Everything's been decided and none were rejected — nothing left to
    # decide on this report, but accepting-all is not itself grounds to
    # auto-complete/lock it either (per the user, 2026-08-06). Leave the door
    # open for another upload if the investigator wants one.
    return {
        "status": "in_progress",
        "upload_count": upload_count,
        "locked": False,
        "can_upload": True,
        "next_upload_is_final": False,
        "latest": latest,
    }