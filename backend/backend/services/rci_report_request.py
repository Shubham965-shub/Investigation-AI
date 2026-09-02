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


# Per-field cap for the RC & CAPA document's own extracted text — each field feeds its own
# separate LLM call (unlike Task Critique's per-section blocks, which get summed together into
# one prompt), so a single generous cap is enough; 8000 comfortably covers the longest real
# value seen live (rc_conclusion_text at 8625 chars for record 505542, itself an unusually
# verbose critique-annotated document) while still bounding a pathological upload.
_MAX_RC_CAPA_FIELD_CHARS = 8000


def _accepted_rc_conclusion(rc_capa_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if rc_capa_report is None:
        return {"rc_conclusion_text": "", "overall_verdict": "accept", "review_comments": []}
    rc_critique = next((c for c in rc_capa_report["critiques"] if c["category"] == "rc_impact"), None)
    recs = rc_critique["recommendations"] if rc_critique else []
    any_rejected = any(r["decision"] == "rejected" for r in recs)
    # Prefer the uploaded document's own verbatim Root Cause Conclusion text
    # (rc_conclusion_text_raw — deterministically extracted, no LLM condensation) over the
    # thin critique summary; falls back to summary only for rows uploaded before this column
    # existed. Same "richer over thin" preference already established for task_findings.
    raw_text = (rc_critique.get("rc_conclusion_text_raw") if rc_critique else "") or ""
    condensed_text = (rc_critique["summary"] if rc_critique else "") or ""
    return {
        "rc_conclusion_text": _truncate(raw_text, _MAX_RC_CAPA_FIELD_CHARS) if raw_text else condensed_text,
        # Real source now exists (extract_rci_report_sections' deterministic detection) —
        # was always None here before 2026-08-25, since no column persisted it.
        "is_repeat_occurrence": (rc_critique.get("is_repeat_occurrence") if rc_critique else None),
        "overall_verdict": "accept_with_comments" if any_rejected else "accept",
        "review_comments": [r["description"] for r in recs],
    }


def _accepted_capa(rc_capa_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if rc_capa_report is None:
        return {"capa_items": [], "overall_verdict": "accept", "review_comments": []}
    capa_critique = next((c for c in rc_capa_report["critiques"] if c["category"] == "capa"), None)
    recs = capa_critique["recommendations"] if capa_critique else []
    any_rejected = any(r["decision"] == "rejected" for r in recs)
    # capa_items now comes from the uploaded document's own real CAPA action table
    # (deterministically parsed by extract_rci_report_sections, no LLM) — previously always
    # empty here because no column persisted it (the old comment on this line claimed "no
    # real accepted-CAPA-action source yet"; that's no longer true as of 2026-08-25).
    raw_text = (capa_critique.get("capa_text_raw") if capa_critique else "") or ""
    condensed_text = (capa_critique["summary"] if capa_critique else "") or ""
    return {
        "capa_items": (capa_critique.get("capa_items") if capa_critique else []) or [],
        "capa_overall_text": _truncate(raw_text, _MAX_RC_CAPA_FIELD_CHARS) if raw_text else condensed_text,
        # interim_controls/extrapolation/capa_not_applicable_justification:
        # no real source yet — left at ds's own Optional/empty-list defaults.
        "overall_verdict": "accept_with_comments" if any_rejected else "accept",
        "review_comments": [r["description"] for r in recs],
    }


def _uploaded_section_text(
    rc_capa_report: Optional[Dict[str, Any]], category: str, key: str
) -> Optional[str]:
    """The uploaded RC & CAPA document's own verbatim Impact Assessment / Correction &
    Remedial Action text — doesn't fit AcceptedRCConclusion/AcceptedCAPAProposal (neither is
    an "accepted proposal" concept), so these are new top-level sibling fields on the request
    instead. None when no RC & CAPA document has been uploaded yet, or the section wasn't
    found in it — callers must fall back to today's TrackWise-field sourcing in that case."""
    if rc_capa_report is None:
        return None
    critique = next((c for c in rc_capa_report["critiques"] if c["category"] == category), None)
    text = (critique.get(key) if critique else None) or None
    return _truncate(text, _MAX_RC_CAPA_FIELD_CHARS) if text else None


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


# Per-field and per-section caps for _format_task_findings — a real live run against a report
# with several verbose tasks produced a single section block of 53,886 characters, which by
# itself overflowed the RCI Report LLM call's context window once combined with the other 5
# sections' blocks plus the rest of the prompt (confirmed live, 2026-08-25). These bounds keep
# each section's block at most ~6KB (still 15-25x richer than the old ~250-340 char
# strengths-only summary it replaces) while a single verbose field can never dominate the budget.
_MAX_FINDING_FIELD_CHARS = 1200
_MAX_SECTION_FINDINGS_CHARS = 6000


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "... [truncated for length]"


def _format_task_findings(findings: List[Dict[str, Any]]) -> Optional[str]:
    """Render ds's real per-task extraction (objective/findings/inference — see
    TaskReportCritiqueResponse.task_evidence) as report-style text blocks, one per
    "Inference:" block ds found in the uploaded document. These blocks do NOT line up
    positionally with the RCI Plan's own subtask list (extract_tasks' task_number is just
    the order "Inference:" markers were found in the document, confirmed live 2026-08-25 —
    e.g. a 6-subtask RCI Plan section had 7 extracted blocks, an 8-subtask section had 6),
    so this stays applied at section granularity like `summary` below, just with far more
    of the uploaded report's actual content than the old strengths-only blurb carried."""
    if not findings:
        return None
    blocks = []
    for f in findings:
        lines = [f"Task {f.get('task_number')}: {f.get('title', '')}".strip()]
        if f.get("objective"):
            lines.append(f"Objective: {_truncate(f['objective'], _MAX_FINDING_FIELD_CHARS)}")
        if f.get("findings"):
            lines.append(f"Findings: {_truncate(f['findings'], _MAX_FINDING_FIELD_CHARS)}")
        if f.get("inference"):
            lines.append(f"Inference: {_truncate(f['inference'], _MAX_FINDING_FIELD_CHARS)}")
        blocks.append("\n".join(lines))

    text = "\n\n".join(blocks)
    if len(text) <= _MAX_SECTION_FINDINGS_CHARS:
        return text

    # Keep as many whole blocks as fit within the section cap rather than truncating mid-block,
    # so a subtask's outcome is never grounded in a half-sentence.
    kept: List[str] = []
    total = 0
    omitted = 0
    for block in blocks:
        if kept and total + len(block) + 2 > _MAX_SECTION_FINDINGS_CHARS:
            omitted += 1
            continue
        kept.append(block)
        total += len(block) + 2
    result = "\n\n".join(kept)
    if omitted:
        result += f"\n\n[{omitted} additional task finding block(s) omitted for length.]"
    return result


def _task_critique_payload(
    rci_sections: List[Dict[str, Any]], task_critique_reports: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """One TaskAssignmentItem per RCI Plan subtask (not per section) —
    `tick` mirrors the RCI Plan export's own "<task>.<subtask>" numbering
    convention. Task Critique's task_index is the 0-based RCI Plan section
    index (see task_critique_queries.py's own module docstring), not a
    per-subtask index.

    `critique` prefers the owning section's real extracted findings
    (`task_findings` — see _format_task_findings) over the old `summary`
    fallback. `summary` is a thin, strengths-only blurb (2-3 sentences,
    ~1-2% of the uploaded report's length, confirmed 2026-08-25) built by
    `task_critique.py` from every extracted task's positive-only `strengths`
    line — real findings/inference were computed by ds's extract_tasks step
    but discarded before reaching this backend at all until `task_findings`
    was added. `summary` is kept as a fallback only for rows uploaded before
    this column existed (task_findings empty). Previously this joined
    recommendations[].reason instead — that field is meta-commentary about
    why an individual review recommendation was accepted/rejected (frequently
    blank, or literal placeholder text like "testing" in test data), never
    the investigation's actual findings, so the report ended up echoing the
    RCI Plan's own planned-task wording back with almost no real evidence
    behind it. Same class of bug as the CAPA gap-commentary conflation fixed
    earlier (recs are commentary about the review, not the review's substance).
    """
    items: List[Dict[str, Any]] = []
    for i, section in enumerate(rci_sections):
        if not section.get("is_checked", True):
            continue
        report = task_critique_reports.get(i)
        critique_text = _format_task_findings(report.get("task_findings") or []) if report else None
        if not critique_text:
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
        "uploaded_impact_assessment_text": _uploaded_section_text(rc_capa_report, "rc_impact", "impact_assessment_text"),
        "uploaded_impact_conclusion_text": _uploaded_section_text(rc_capa_report, "rc_impact", "impact_conclusion_text"),
        "uploaded_correction_remedial_text": _uploaded_section_text(rc_capa_report, "capa", "correction_remedial_text"),
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
