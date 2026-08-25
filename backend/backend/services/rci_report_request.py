"""Assembles the JSON body for ds's real POST /rci-report/generate from
this backend's own already-stored module data — RCI Plan sections, Task
Critique reports, and RC & CAPA Critique's locked report. Kept separate
from the router, same separation rci_plan_export.py already models for RCI
Plan's docx-filling logic.

ds's request schema (RciReportGenerationRequest, re-read directly 2026-08-21)
asks for a few fields this backend has no real source for yet — those are
defaulted rather than block generation on them; see the module docstring in
schemas/rci_report.py and the plan this was built from for the full list.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _accepted_rc_conclusion(rc_capa_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if rc_capa_report is None:
        return {"rc_conclusion_text": "", "overall_verdict": "accept", "review_comments": []}
    rc_critique = next((c for c in rc_capa_report["critiques"] if c["category"] == "rc_impact"), None)
    recs = rc_critique["recommendations"] if rc_critique else []
    any_rejected = any(r["decision"] == "rejected" for r in recs)
    return {
        "rc_conclusion_text": (rc_critique["summary"] if rc_critique else "") or "",
        # is_repeat_occurrence/broad_category/category/root_cause_sub_category:
        # no real source on investigation_rc_capa_reports today — left at
        # ds's own Optional defaults (None) rather than fabricated.
        "overall_verdict": "accept_with_comments" if any_rejected else "accept",
        "review_comments": [r["description"] for r in recs],
    }


def _accepted_capa(rc_capa_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if rc_capa_report is None:
        return {"capa_items": [], "overall_verdict": "accept", "review_comments": []}
    capa_critique = next((c for c in rc_capa_report["critiques"] if c["category"] == "capa"), None)
    recs = capa_critique["recommendations"] if capa_critique else []
    any_rejected = any(r["decision"] == "rejected" for r in recs)
    # capa_items must hold real ACCEPTED CAPA actions ({description,
    # responsibility, due_date} per ds's CAPAItemDetail) — but
    # investigation_rc_capa_reports' capa_recommendations are CAPA Critique's
    # gap-commentary about the source report's CAPA table (e.g. "This action
    # doesn't name a responsible person"), not accepted actions themselves.
    # There is no real accepted-CAPA-action source yet, so capa_items stays
    # empty here (same honest-gap pattern as _accepted_rc_conclusion above)
    # and ds's own "skip CAPA cleanly" gate (commit 872fb70) presents this
    # correctly as CAPA not yet accepted, instead of rendering the gap
    # commentary as if it were real CAPA content.
    return {
        "capa_items": [],
        "capa_overall_text": (capa_critique["summary"] if capa_critique else "") or "",
        # interim_controls/extrapolation/capa_not_applicable_justification:
        # no real source yet — left at ds's own Optional/empty-list defaults.
        "overall_verdict": "accept_with_comments" if any_rejected else "accept",
        "review_comments": [r["description"] for r in recs],
    }


def _rci_plan_sections_payload(rci_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ds's own RciSectionItem (ds/src/agents/rci_plan/schemas.py) is a
    plimmer shape than this backend's own — just title/correlation/tasks
    (each task just a description) — no due_date/assignee/is_checked/id.
    Same "checked = keep it" filtering rci_plan_export.py already uses for
    excluded sections/unchecked tasks."""
    return [
        {
            "title": s["title"],
            "correlation": s.get("correlation"),
            "tasks": [{"description": t["description"]} for t in s["tasks"] if t.get("is_checked", True)],
        }
        for s in rci_sections
        if s.get("is_checked", True)
    ]


def _task_critique_payload(
    rci_sections: List[Dict[str, Any]], task_critique_reports: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """One TaskAssignmentItem per RCI Plan subtask (not per section) —
    `tick` mirrors the RCI Plan export's own "<task>.<subtask>" numbering
    convention. Task Critique's task_index is the 0-based RCI Plan section
    index (see task_critique_queries.py's own module docstring), not a
    per-subtask index.

    `critique` is the owning section's Task Critique `summary` — the
    substantive analysis of what the uploaded, completed investigation
    document actually demonstrated (e.g. "compares the same TAC/RMG/347
    equipment across validation, campaign, and deviation batches..."), which
    is what ds's investigation_task_system.txt prompt is actually written to
    synthesize from ("the Task Critique step's output... per-task critique
    comments"). Previously this joined recommendations[].reason instead —
    that field is meta-commentary about why an individual review
    recommendation was accepted/rejected (frequently blank, or literal
    placeholder text like "testing" in test data), never the investigation's
    actual findings, so the report ended up echoing the RCI Plan's own
    planned-task wording back with almost no real evidence behind it. Same
    class of bug as the CAPA gap-commentary conflation fixed earlier
    (recs are commentary about the review, not the review's substance).
    """
    items: List[Dict[str, Any]] = []
    for i, section in enumerate(rci_sections):
        if not section.get("is_checked", True):
            continue
        report = task_critique_reports.get(i)
        critique_text = (report.get("summary") or None) if report else None
        checked_tasks = [t for t in section["tasks"] if t.get("is_checked", True)]
        for j, task in enumerate(checked_tasks):
            items.append(
                {
                    "tick": f"{i + 1}.{j + 1}",
                    "task": task["description"],
                    "responsible_person": section.get("assignee") or "Unassigned",
                    "selected": True,  # already filtered to checked tasks above
                    "critique": critique_text,
                    "mandatory": True,  # no weaker/stronger distinction exists today
                }
            )
    return items


def build_rci_report_request(
    *,
    record_id: str,
    event_type: str,
    trackwise_fields: Dict[str, Any],
    rci_sections: List[Dict[str, Any]],
    task_critique_reports: Dict[int, Dict[str, Any]],
    rc_capa_report: Optional[Dict[str, Any]],
    mc_confirmed: Optional[bool],
    manual_entries: Dict[str, str],
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "deviation_id": record_id,
        "trackwise_fields": trackwise_fields,
        "rci_plan_sections": _rci_plan_sections_payload(rci_sections),
        "task_critique": _task_critique_payload(rci_sections, task_critique_reports),
        "accepted_rc_conclusion": _accepted_rc_conclusion(rc_capa_report),
        "accepted_capa": _accepted_capa(rc_capa_report),
        "mc_confirmed": mc_confirmed,
        # 24 months ("last 2 years") — matches real reports' stated lookback;
        # 12 months caused genuinely similar older records to be missed. See
        # ds's RciReportGenerationRequest.history_lookback_months.
        "history_lookback_months": 24,
        "manual_entries": manual_entries,
        # approval_workflow/attachments: pure pass-through, no LLM — omitted
        # (ds defaults both to empty if absent). Populating annexures from
        # Evidence Collection or approval rows from athena_users is a
        # natural v2, not required now.
    }
