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

    recs = latest["recommendations"]

    # 3rd/final attempt is always terminally locked regardless of decision
    # mix, checked before the critique_failed branch below — critique_failed
    # is now overloaded with a second meaning (2026-08-18, ticket 500954: a
    # final report whose separate SCORING call failed, added by a teammate's
    # commit to routers/task_critique.py's set_task_score) that must stay
    # locked/complete, unlike the original meaning (wrong report
    # format/degenerate critique, never a genuine critique at all). Checking
    # upload_count here first, ahead of critique_failed, means a 3rd-attempt
    # report whose scoring failed correctly stays locked instead of being
    # unlocked for a reupload the investigator has no attempts left for.
    if upload_count >= MAX_UPLOADS:
        return {
            "status": "complete",
            "upload_count": upload_count,
            "locked": True,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }

    if latest.get("critique_failed"):
        # Reaching here means NOT gospel and NOT the final attempt — so this
        # is the original meaning: wrong report format, or DS found nothing
        # real to critique (see task_report_format.py / the
        # total_tasks_analyzed==0 check in routers/task_critique.py) — never
        # a genuine critique, so it must not lock the section or block a
        # reupload (2026-08-14, per the user: uploading the wrong file must
        # still leave the door open to upload the correct one). Falls through
        # to here rather than the "not recs" branch below, which would
        # otherwise treat this the same as "critique not back yet" and never
        # let go — RC & CAPA reports have no critique_failed column, so `.get`
        # is always falsy there and this branch is unreachable for that caller.
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": True,
            "next_upload_is_final": False,
            "latest": latest,
        }

    if not recs:
        # BUGFIX (2026-09-10, per the user — confirmed live on record 507944:
        # a 2nd attempt whose critique genuinely came back with zero
        # recommendations got stuck permanently, not locked/complete but also
        # not re-uploadable, with nothing to accept/reject since there was
        # nothing to decide). By the time a report row exists here at all,
        # its critique call already ran and was persisted in the SAME request
        # that created it (routers/task_critique.py's upload_task_report /
        # rc_capa_critique.py's equivalent — there is no separate "insert a
        # placeholder now, the critique fills in later" step for either
        # caller), so an empty list here means DS genuinely found nothing to
        # flag, never "critique still pending" despite this branch's
        # original comment assuming otherwise. Treated the same as "every
        # recommendation rejected" below: the report is already good enough,
        # so it locks as complete instead of leaving a dead end.
        return {
            "status": "complete",
            "upload_count": upload_count,
            "locked": True,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }

    decisions = {r["decision"] for r in recs}
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