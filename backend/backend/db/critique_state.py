"""Shared upload/lock/status state machine for Task Critique and RC & CAPA
Critique (identical business rule, extracted to avoid duplication):
  - 3 uploads max, then locked regardless of remaining rejected recommendations.
  - Reupload only once every recommendation on the latest report is decided;
    once fully decided, any rejection present allows reupload.
  - If a report ends up all-rejected, the next upload is a "gospel" report
    (no critique) that locks immediately.
Agnostic to recommendation categories — callers flatten their own into one
list per report before calling.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

MAX_UPLOADS = 3


def compute_upload_state(latest: Optional[Dict[str, Any]], upload_count: int) -> Dict[str, Any]:
    """`latest`: the most recent report, a dict with `is_gospel: bool` and a
    flattened `recommendations: list[{"decision": ...}]`. `upload_count` is
    the caller's own attempt counter (not always inferable from row count)."""
    if latest is None or upload_count == 0:
        return {
            "status": "pending",
            "upload_count": 0,
            "locked": False,
            "can_upload": True,
            "next_upload_is_final": False,
            "latest": None,
        }

    if latest.get("critique_pending"):
        # Upload persisted, DS critique/scoring still running in the background (see
        # routers/task_critique.py's/_process_task_report_async and its RC&CAPA equivalent) —
        # checked before every other branch below, since an in-flight row can otherwise look
        # identical to "DS genuinely found nothing to flag" (empty recommendations) and lock
        # itself as falsely complete before the background call has even run.
        return {
            "status": "processing",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
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

    # Final attempt always locks regardless of decision mix; checked before
    # critique_failed since critique_failed is overloaded with a second
    # meaning (a final report whose scoring call failed, ticket 500954) that
    # must also stay locked, unlike its original "bad file" meaning below.
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
        # Original meaning here (not final attempt): bad report format / DS
        # found nothing to critique — never a genuine critique, so it must
        # not lock or block a reupload. Also reached by a background DS
        # failure during async upload processing (both Task Critique and,
        # since 2026-09-28, RC & CAPA Critique — see each router's
        # _process_*_async).
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": True,
            "next_upload_is_final": False,
            "latest": latest,
        }

    if not recs:
        # Empty here means DS genuinely found nothing to flag, never
        # "critique still pending" — the critique call already ran and was
        # persisted in the same request that created this row. Treated like
        # all-rejected below: locks as complete instead of a dead end.
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
        # At least one recommendation still undecided — no reupload until all are decided.
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }
    if decisions == {"rejected"}:
        # All rejected — treat as final/locked immediately rather than
        # requiring a separate gospel upload; is_gospel stays False since it
        # was still genuinely critiqued.
        return {
            "status": "complete",
            "upload_count": upload_count,
            "locked": True,
            "can_upload": False,
            "next_upload_is_final": False,
            "latest": latest,
        }
    if "rejected" in decisions:
        # Mixed accept/reject — reupload stays optional; next upload not gospel.
        return {
            "status": "in_progress",
            "upload_count": upload_count,
            "locked": False,
            "can_upload": True,
            "next_upload_is_final": False,
            "latest": latest,
        }
    # All decided, none rejected — accepting-all isn't itself grounds to
    # auto-lock; leave the door open for another upload if wanted.
    return {
        "status": "in_progress",
        "upload_count": upload_count,
        "locked": False,
        "can_upload": True,
        "next_upload_is_final": False,
        "latest": latest,
    }