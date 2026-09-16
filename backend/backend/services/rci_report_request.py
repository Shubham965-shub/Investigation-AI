"""Assembles the JSON body for ds's POST /rci-report/generate from this backend's stored RCI Plan/Task Critique/RC & CAPA data; fields with no real source yet are defaulted rather than blocking generation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# Per-field cap for RC & CAPA extracted text — each field feeds its own LLM call, so one generous cap bounds a pathological upload without truncating real values.
_MAX_RC_CAPA_FIELD_CHARS = 8000


def _accepted_rc_conclusion(rc_capa_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if rc_capa_report is None:
        return {"rc_conclusion_text": "", "overall_verdict": "accept", "review_comments": []}
    rc_critique = next((c for c in rc_capa_report["critiques"] if c["category"] == "rc_impact"), None)
    recs = rc_critique["recommendations"] if rc_critique else []
    any_rejected = any(r["decision"] == "rejected" for r in recs)
    # Prefer the verbatim extracted RC Conclusion text over the thin critique summary; falls back to summary for rows uploaded before this column existed.
    raw_text = (rc_critique.get("rc_conclusion_text_raw") if rc_critique else "") or ""
    condensed_text = (rc_critique["summary"] if rc_critique else "") or ""
    return {
        "rc_conclusion_text": _truncate(raw_text, _MAX_RC_CAPA_FIELD_CHARS) if raw_text else condensed_text,
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
    raw_text = (capa_critique.get("capa_text_raw") if capa_critique else "") or ""
    condensed_text = (capa_critique["summary"] if capa_critique else "") or ""
    return {
        "capa_items": (capa_critique.get("capa_items") if capa_critique else []) or [],
        "capa_overall_text": _truncate(raw_text, _MAX_RC_CAPA_FIELD_CHARS) if raw_text else condensed_text,
        # interim_controls/extrapolation/capa_not_applicable_justification: no real source yet, left at ds's defaults.
        "overall_verdict": "accept_with_comments" if any_rejected else "accept",
        "review_comments": [r["description"] for r in recs],
    }


def _uploaded_section_text(
    rc_capa_report: Optional[Dict[str, Any]], category: str, key: str
) -> Optional[str]:
    """Verbatim uploaded Impact Assessment / Correction & Remedial Action text. None if no report uploaded yet or the section wasn't found — caller falls back to TrackWise sourcing."""
    if rc_capa_report is None:
        return None
    critique = next((c for c in rc_capa_report["critiques"] if c["category"] == category), None)
    text = (critique.get(key) if critique else None) or None
    return _truncate(text, _MAX_RC_CAPA_FIELD_CHARS) if text else None


def _rci_plan_sections_payload(rci_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ds's RciSectionItem is a slimmer shape than ours: just title/correlation/tasks. Same "checked = keep it" filtering as rci_plan_export.py."""
    return [
        {
            "title": s["title"],
            "correlation": s.get("correlation"),
            "tasks": [{"description": t["description"]} for t in s["tasks"] if t.get("is_checked", True)],
        }
        for s in rci_sections
        if s.get("is_checked", True)
    ]


# Caps for _format_task_findings — a verbose report's section block once overflowed the RCI Report LLM call's context window; bounds each block to ~6KB.
_MAX_FINDING_FIELD_CHARS = 1200
_MAX_SECTION_FINDINGS_CHARS = 6000


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "... [truncated for length]"


def _format_task_findings(findings: List[Dict[str, Any]]) -> Optional[str]:
    """Renders ds's per-task extraction as report-style text blocks. These don't line up positionally with the RCI Plan's subtask list, so kept at section granularity, like `summary`."""
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

    # Keep whole blocks only, never truncate mid-block, so a subtask's outcome isn't grounded in a half-sentence.
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
    """One TaskAssignmentItem per RCI Plan subtask (not per section); `tick` mirrors the export's "<task>.<subtask>" numbering. `critique` prefers real extracted `task_findings` over the thin `summary` fallback (kept only for rows uploaded before that column existed) — not recommendations[].reason, which is commentary about the review decision, not the investigation's actual findings."""
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
        # 24 months matches real reports' stated lookback; 12 months missed genuinely similar older records.
        "history_lookback_months": 24,
        "manual_entries": manual_entries,
        # approval_workflow/attachments omitted — ds defaults both to empty.
    }
