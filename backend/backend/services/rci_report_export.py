"""Fills the company's real RCI Report Word template (assets/rci_report_template.docx)
with a generated RCI report's data, for the RCI Report page's "Accept and Push to
TW" download.

Structure (confirmed via python-docx, 2026-08-25) — this template is almost
entirely guidance paragraphs with a handful of blank lines to type an answer
into, unlike RCI Plan's template which is built from fillable table cells
throughout:

  - Page header (doc.sections[0].header, appears on every page — a single
    un-linked section, confirmed): a 4x4 table — row 0 is the repeated
    title banner; rows 1-3 are label/value pairs (Product/Material Name,
    Product/material Code, Parent record number, RCI record number,
    Batch(es)/AR No. involved, Date of initiation). Parent record number is
    the deviation id (`record_id`), RCI record number is the genuine
    TrackWise RCI id (`trackwise_fields["RCI Number"]` — dim_rci.rci_key,
    confirmed distinct from the deviation id elsewhere in this app).
  - Table 0 (13x4): the INDEX/table-of-contents — left untouched (page
    numbers aren't tracked anywhere in this app).
  - Executive Summary (body paragraphs, no table): 6 named sub-headings
    (Problem Description / Immediate containment action / Determination of
    root cause / Root Cause-Probable Cause statement / Impact Assessment /
    Correction-CAPA), each followed by one or more blank paragraphs to fill.
    ExecutiveSummarySection has 8 fields (adds `summary` and
    `conclusion_statement`, neither of which has its own heading) — `summary`
    goes in the first blank before "Problem Description", and
    `conclusion_statement` shares the last sub-heading's blank block (there
    are 6 blank paragraphs there, more than enough for both fields).
  - Table 1 (7x2): Description of Event, one row per field — clean 1:1 map.
  - Table 2 / Table 3: Initial Impact Assessment's material/product and
    equipment impact lists.
  - Table 4: History Review's prior-events rows.
  - Table 5 (3x1): Root Cause conclusion — row 1 is the narrative, row 2 is
    "Category: / Subcategory:".
  - Table 6 (2x1): Correction/Remedial — these two rows are just the
    template's own definitions of the two terms, not fillable; the actual
    `items`/`additional_notes` go in the blank paragraphs right after the
    table (no per-item table exists here).
  - Table 7/8/9: CAPA actions / interim controls / extrapolation.
  - Table 10: CAPA effectiveness check plan.
  - Table 11 (8x2): Annexures — always present (pass-through, never None).
  - Table 12 (6x5): Approval — fixed role rows (Prepared by/Investigator,
    Reviewed by/HOD, /QA, /SIT, Approved by/Head-QA); always present
    (pass-through, never None) — filled by matching `role` to these labels.

No slot exists anywhere in this template for RiskAssessmentSection (it's
absent from the INDEX table too — this template predates/doesn't cover the
Market-Complaint-only risk scoring workflow). Rather than inventing new
document structure the company hasn't approved, its content is appended
into the same blank paragraph as Impact Assessment's optional
MC/OOS-specific fields, clearly labeled, so it's still visible rather than
silently dropped.

Every section field on RciReportSections is Optional — ds skips a section
(leaving it None) when a required TrackWise field was blank or a dependency
section itself failed (2026-08-24 finding, `errors` dict explains why). Per
the user (2026-08-25): a null section must show up AS SUCH in the document,
not leave the reader guessing whether it was overlooked. One clear note is
written at that section's first slot (`errors[section_key]` if present,
else a generic line) — the rest of that section's slots are left at the
template's own default (blank/guidance), rather than repeating the note
everywhere, since one clear flag per section is enough.

We fill this exact template in place (matching rci_plan_export.py's own
convention) so all of its original borders/merges/styling survive untouched.
Unlike that template, this one's own runs already have no explicit font set
(theme default throughout, confirmed via every existing run's `font.name`
being None) — so a freshly created run reusing an existing run's formatting
never introduces a font mismatch here, and no Times-New-Roman forcing is
needed the way RCI Plan's export required.
"""
from __future__ import annotations

import copy
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

from backend.schemas.rci_report import RciReportSections

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "rci_report_template.docx"

MISSING_NOTE_FALLBACK = "This section could not be generated — the related TrackWise field(s) aren't filled."

# The template's own headings/guidance/table text almost all explicitly set
# 11pt (confirmed run-by-run, 2026-08-25) even though the document's Normal
# style itself defaults to 12pt Times New Roman — a run we create fresh
# (cell.text=, add_run(), add_paragraph()) sets neither, so it would
# silently inherit that 12pt style default and read as a different size
# from every answer sitting right next to it, despite both resolving to the
# same font family. Forced explicitly on every run this file touches so
# every generated font/size/heading/in-table text matches the template's
# own convention exactly (2026-08-25, per the user). Table content is
# additionally locked to 10pt, one step down from body content's 11pt
# (2026-08-25, per the user), matching how a real Word table's contents
# commonly run a point smaller than the surrounding body text.
FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(11)
TABLE_FONT_SIZE = Pt(10)


def _apply_font(run, size=None) -> None:
    run.font.name = FONT_NAME
    run.font.size = size or FONT_SIZE


def _missing_note(errors: dict, key: str) -> str:
    return f"[{errors.get(key) or MISSING_NOTE_FALLBACK}]"


def _set_cell_text(cell, text: str) -> None:
    """Always inside a table — locked to TABLE_FONT_SIZE (10pt), one step
    down from body content's 11pt."""
    cell.text = text or ""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            _apply_font(run, TABLE_FONT_SIZE)


def _body_paragraph(doc, index: int) -> Paragraph:
    return Paragraph(doc.element.body[index], doc)


def _set_paragraph_text(doc, index: int, text: str, clear_italic: bool = False) -> None:
    """Reuses the first run's formatting (list-level, any other non-font
    properties) so this paragraph's existing style carries over, clearing
    any other runs so no template guidance text lingers alongside the real
    answer. Font/size are always forced (see FONT_NAME/FONT_SIZE above), not
    just carried over, since a genuinely blank paragraph's fresh run has
    neither set. `clear_italic` is for the couple of slots where the real
    answer replaces a paragraph that WAS the guidance text itself (e.g. Root
    Cause/Probable Cause statement) — per the user, 2026-08-25, the answer
    must read as real content, not still look like an italicized instruction."""
    para = _body_paragraph(doc, index)
    if para.runs:
        run = para.runs[0]
        run.text = text
        if clear_italic:
            run.italic = False
        for extra in para.runs[1:]:
            extra.text = ""
    else:
        run = para.add_run(text)
        if clear_italic:
            run.italic = False
    _apply_font(run)


def _set_paragraph_lines(doc, index: int, lines: List[str], clear_italic: bool = False) -> None:
    """Like _set_paragraph_text, but joins multiple lines with real line
    breaks (not just a delimiter) so multi-item narrative content (findings,
    history rows, checklists) actually reads as a list in the document."""
    lines = [line for line in lines if line]
    para = _body_paragraph(doc, index)
    run = para.runs[0] if para.runs else para.add_run()
    run.text = lines[0] if lines else ""
    if clear_italic:
        run.italic = False
    for line in lines[1:]:
        run.add_break()
        run.add_text(line)
    _apply_font(run)
    for extra in para.runs[1:]:
        extra.text = ""


def _strip_guidance_runs(doc) -> None:
    """Removes every italic run from every top-level body paragraph — this
    template consistently styles pure guidance/instructional text as italic
    (confirmed run-by-run), including runs that trail directly after a
    heading within the SAME paragraph (e.g. "Determination of root cause/
    probable cause: Provide a brief summary..." — the heading label itself
    is plain, only the trailing instruction is italic). Per the user
    (2026-08-25): "remove the small italic guidance texts. they are to be
    replaced by the content" — the two slots this file overwrites in place
    (Root Cause/Probable Cause statement, Impact Assessment's Conclusion
    Statement — the guidance paragraph itself IS the answer slot there, no
    separate blank exists) already have their own run's italic cleared
    before this runs, via _set_paragraph_text's clear_italic, so the real
    content they now hold survives this pass untouched. A paragraph left
    with nothing in it once its only run(s) were guidance is removed
    entirely rather than leaving a stray empty line."""
    for child in list(doc.element.body):
        if child.tag != qn("w:p"):
            continue
        para = Paragraph(child, doc)
        for run in list(para.runs):
            if run.italic:
                run.element.getparent().remove(run.element)
        if not para.runs and not para.text.strip():
            child.getparent().remove(child)


def _ensure_row_count(table, first_data_row: int, count: int, template_row: Optional[int] = None) -> List[Any]:
    """Adjusts `table` so it has exactly `max(count, 1)` data rows starting
    at `first_data_row` — cloning `template_row` (defaults to
    `first_data_row`) to grow, or dropping trailing rows to shrink. Always
    keeps at least one row: a single blank/"N/A" row reads better than a
    headers-only table when a list is genuinely empty. Returns the data rows."""
    if template_row is None:
        template_row = first_data_row
    current = len(table.rows) - first_data_row
    target = max(count, 1)
    if target > current:
        template_tr = copy.deepcopy(table.rows[template_row]._tr)
        for _ in range(target - current):
            table._tbl.append(copy.deepcopy(template_tr))
    elif target < current:
        for row in list(table.rows)[first_data_row + target :]:
            row._tr.getparent().remove(row._tr)
    for row in list(table.rows)[first_data_row : first_data_row + target]:
        for cell in row.cells:
            _set_cell_text(cell, "")
    return list(table.rows)[first_data_row : first_data_row + target]


def _sourced(item) -> str:
    return item.value if item else ""


def _yesno(value: bool) -> str:
    return "Yes" if value else "No"


# ── 1. Executive Summary ────────────────────────────────────────────────

def _fill_executive_summary(doc, section, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(doc, 55, _missing_note(errors, "executive_summary"))
        return
    _set_paragraph_text(doc, 55, section.summary)
    _set_paragraph_text(doc, 59, section.problem_description)
    _set_paragraph_text(doc, 64, section.immediate_containment_action)
    _set_paragraph_text(doc, 71, section.determination_of_root_cause)
    _set_paragraph_text(doc, 74, section.root_cause_probable_cause_statement, clear_italic=True)
    _set_paragraph_text(doc, 80, section.impact_assessment)
    _set_paragraph_text(doc, 86, section.correction_conclusion_preventive_actions)
    _set_paragraph_text(doc, 87, f"Conclusion Statement: {section.conclusion_statement}")


# ── 2. Description of Event ─────────────────────────────────────────────

def _fill_description_of_event(doc, section, errors: dict) -> None:
    table = doc.tables[1]
    if section is None:
        _set_cell_text(table.rows[1].cells[1], _missing_note(errors, "description_of_event"))
        return
    _set_cell_text(table.rows[1].cells[1], section.what_happened)
    _set_cell_text(table.rows[2].cells[1], section.when_happened)
    _set_cell_text(table.rows[3].cells[1], section.who_identified)
    _set_cell_text(table.rows[4].cells[1], section.where_it_happened)
    _set_cell_text(table.rows[5].cells[1], _sourced(section.nonconforming_reference))
    _set_cell_text(table.rows[6].cells[1], _sourced(section.how_detected))


# ── 3. Initial Impact Assessment & Immediate Actions ────────────────────

def _fill_initial_impact_assessment(doc, section, errors: dict) -> None:
    material_table = doc.tables[2]
    equipment_table = doc.tables[3]
    if section is None:
        rows = _ensure_row_count(material_table, 1, 1)
        _set_cell_text(rows[0].cells[1], _missing_note(errors, "initial_impact_assessment"))
        _ensure_row_count(equipment_table, 1, 1)
        _set_paragraph_text(doc, 107, "")
        return

    impacts = section.material_product_impacts
    rows = _ensure_row_count(material_table, 1, len(impacts))
    if not impacts:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, impacts)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.material_product_batch)
        _set_cell_text(row.cells[2], item.stage)
        action = f"{item.type_of_impact} — Qty involved: {item.quantity_involved}; Qty on hold: {_sourced(item.quantity_on_hold)}"
        _set_cell_text(row.cells[3], action)

    equip = section.equipment_impacts
    rows = _ensure_row_count(equipment_table, 1, len(equip))
    if not equip:
        _set_cell_text(rows[0].cells[1], "N/A")
    for row, item in zip(rows, equip):
        _set_cell_text(row.cells[0], "")
        _set_cell_text(row.cells[1], _sourced(item.equipment_instrument))
        _set_cell_text(row.cells[2], _sourced(item.identification_number))
        actions = item.actions_initiated
        lines = []
        if actions.operation_suspended:
            lines.append("Operation suspended.")
        if actions.on_hold_label_affixed:
            lines.append("'On Hold' label affixed.")
        if actions.other_action_taken:
            spec = f" [Specify: {actions.other_action_specify}]" if actions.other_action_specify else ""
            lines.append(f"Other action taken{spec}.")
        _set_cell_text(row.cells[3], " ".join(lines) or "None")

    _set_paragraph_lines(doc, 107, section.immediate_actions)


# ── 4. Summary of Historical Review ─────────────────────────────────────

def _fill_history_review(doc, section, errors: dict) -> None:
    table = doc.tables[4]
    if section is None:
        rows = _ensure_row_count(table, 1, 1)
        _set_cell_text(rows[0].cells[2], _missing_note(errors, "history_review"))
        _set_paragraph_text(doc, 117, "")
        return

    rows = _ensure_row_count(table, 1, len(section.rows))
    if not section.rows:
        _set_cell_text(rows[0].cells[2], "N/A")
    for i, (row, item) in enumerate(zip(rows, section.rows)):
        _set_cell_text(row.cells[0], f"{i + 1}.")
        _set_cell_text(row.cells[1], item.event_number)
        _set_cell_text(row.cells[2], item.event_title)
        _set_cell_text(row.cells[3], item.capa_description)
        _set_cell_text(row.cells[4], item.capa_implementation_date)

    lines = [
        f"Lookback period: {section.lookback_months} months.",
        "No similar events found in the lookback window." if section.no_similar_events_found else "",
        section.closing_narrative,
        f"Batches manufactured: {section.batches_manufactured_note}" if section.batches_manufactured_note else "",
    ]
    _set_paragraph_lines(doc, 117, lines)


# ── 5. Investigation Task ───────────────────────────────────────────────

def _fill_investigation_task(doc, section, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(doc, 132, _missing_note(errors, "investigation_task"))
        return

    lines = [f"RCA method evidence: {section.rca_method_evidence}"]
    if section.rca_methods_used:
        lines.append(f"RCA method(s) used: {', '.join(section.rca_methods_used)}")
    for group in section.groups:
        lines.append(group.section_title)
        for sub in group.subsections:
            factors = f" ({', '.join(sub.six_m_factors)})" if sub.six_m_factors else ""
            lines.append(f"  {sub.title}{factors}")
            for finding in sub.findings:
                prefix = f"{finding.sop_reference}: " if finding.sop_reference else ""
                lines.append(f"    - {prefix}{finding.finding}")
    _set_paragraph_lines(doc, 132, lines)


# ── 6. Root Cause conclusion ─────────────────────────────────────────────

def _fill_root_cause_conclusion(doc, section, errors: dict) -> None:
    table = doc.tables[5]
    if section is None:
        _set_cell_text(table.rows[1].cells[0], _missing_note(errors, "root_cause_conclusion"))
        return
    _set_cell_text(table.rows[1].cells[0], section.conclusion)
    repeat_para = table.rows[1].cells[0].add_paragraph(
        f"Repeat occurrence: {_yesno(section.is_repeat_occurrence)} — {section.repeat_occurrence_evidence}"
    )
    for run in repeat_para.runs:
        _apply_font(run, TABLE_FONT_SIZE)
    _set_cell_text(table.rows[2].cells[0], f"Category: {section.taxonomy.category}   Subcategory: {section.taxonomy.sub_category}")


# ── 7. Impact Assessment & Conclusion (Batch disposition) ──────────────

_IMPACT_SUBSECTION_LABELS = [
    ("impact_on_affected_batches", "Impact on Affected Batches"),
    ("impact_on_marketed_released_batches", "Impact on Marketed/Released Batches"),
    ("impact_on_other_product_material_area_process", "Impact on Other Product/Material/Area/Process"),
    ("impact_on_regulatory_filing", "Impact on Regulatory Filing"),
    ("impact_on_facility_equipment_instrument", "Impact on Facility/Equipment/Instrument"),
    ("impact_on_manufacturing_process_analytical_method", "Impact on Manufacturing Process/Analytical Method"),
    ("business_continuity", "Business Continuity"),
    ("impact_on_data_integrity", "Impact on Data Integrity"),
    ("stability_repackaging_requirement", "Stability/Repackaging Requirement"),
    ("patient_safety", "Patient Safety"),
    ("others_as_applicable", "Others, as applicable"),
]


def _fill_impact_assessment_batch_disposition(doc, section, risk_section, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(doc, 165, _missing_note(errors, "impact_assessment_batch_disposition"))
    else:
        lines = []
        for field_name, label in _IMPACT_SUBSECTION_LABELS:
            sub = getattr(section, field_name)
            if not sub.applicable:
                continue
            lines.append(f"{label}: {sub.narrative}")
            if field_name == "impact_on_affected_batches" and sub.batch_shipper_table:
                for row in sub.batch_shipper_table:
                    lines.append(f"  - Batch {row.batch_number}: {row.number_of_shippers} shipper(s), defects: {row.defects}")
        if not lines:
            lines = ["Not applicable."]
        _set_paragraph_lines(doc, 165, lines)
        _set_paragraph_text(doc, 170, f"Conclusion Statement: {section.conclusion}", clear_italic=True)

    extra_lines = []
    if section is not None:
        if section.medical_investigation_summary:
            extra_lines.append(f"Medical Investigation Summary: {section.medical_investigation_summary}")
        if section.health_hazard_evaluation:
            extra_lines.append(f"Health Hazard Evaluation: {section.health_hazard_evaluation}")
        if section.impact_justification:
            extra_lines.append(f"Impact Justification: {section.impact_justification}")

    # No slot exists anywhere in this template for Risk Assessment (see
    # module docstring) — appended here, clearly labeled, rather than
    # silently dropped.
    if risk_section is None:
        extra_lines.append(f"Risk Assessment: {_missing_note(errors, 'risk_assessment')}")
    else:
        extra_lines.append(f"Risk Assessment applicability: {risk_section.applicable} — {risk_section.applicability_reason}")
        for c in risk_section.candidates:
            extra_lines.append(
                f"  - {c.cause_label}: Severity {c.factors.severity.tier} ({c.severity_score}), "
                f"Repeatability {c.factors.repeatability.tier} ({c.repeatability_score}), "
                f"Detectability {c.factors.detectability.tier} ({c.detectability_score}), "
                f"RPN {c.rpn}, Risk level {c.risk_level}"
            )
    _set_paragraph_lines(doc, 171, extra_lines)


# ── 8. Correction and/or Remedial Action ────────────────────────────────

def _fill_correction_remedial_action(doc, section, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(doc, 174, _missing_note(errors, "correction_remedial_action"))
        _set_paragraph_text(doc, 175, "")
        return
    lines = [f"{item.observation} — Status: {item.status}" + (f" [Ref: {item.reference_number}]" if item.reference_number else "") for item in section.items]
    _set_paragraph_lines(doc, 174, lines or ["N/A"])
    _set_paragraph_lines(doc, 175, section.additional_notes)


# ── 9/10/11. CAPA (actions / interim controls / extrapolation) ─────────

def _fill_capa(doc, section, errors: dict) -> None:
    actions_table = doc.tables[7]
    interim_table = doc.tables[8]
    extrapolation_table = doc.tables[9]

    if section is None:
        _set_paragraph_text(doc, 181, _missing_note(errors, "capa"))
        rows = _ensure_row_count(actions_table, 1, 1)
        _set_cell_text(rows[0].cells[1], _missing_note(errors, "capa"))
        _ensure_row_count(interim_table, 1, 1)
        _ensure_row_count(extrapolation_table, 1, 1)
        return

    _set_paragraph_text(doc, 181, section.capa_not_applicable_justification or "")

    rows = _ensure_row_count(actions_table, 1, len(section.capa_actions))
    if not section.capa_actions:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, section.capa_actions)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.description)
        _set_cell_text(row.cells[2], item.responsibility or "")
        _set_cell_text(row.cells[3], item.due_date)

    rows = _ensure_row_count(interim_table, 1, len(section.interim_controls))
    if not section.interim_controls:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, section.interim_controls)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.description)
        _set_cell_text(row.cells[2], item.responsibility)
        _set_cell_text(row.cells[3], item.due_date)

    rows = _ensure_row_count(extrapolation_table, 1, 1)
    extrapolation = section.extrapolation
    if not extrapolation.applicable:
        _set_cell_text(rows[0].cells[1], f"Not applicable — {extrapolation.justification}")
    else:
        details = [extrapolation.justification, extrapolation.scope_description]
        for label, values in (
            ("Customers", extrapolation.related_customers),
            ("Markets", extrapolation.related_markets),
            ("CAPA numbers", extrapolation.capa_numbers),
            ("Change controls", extrapolation.related_change_controls),
        ):
            if values:
                details.append(f"{label}: {', '.join(values)}")
        _set_cell_text(rows[0].cells[1], " | ".join(d for d in details if d))
    _set_cell_text(rows[0].cells[0], "1.")
    _set_cell_text(rows[0].cells[2], extrapolation.responsibility)
    _set_cell_text(rows[0].cells[3], extrapolation.due_date)


# ── 12. CAPA Effectiveness Check Plan ────────────────────────────────────

def _fill_capa_effectiveness_check_plan(doc, section, errors: dict) -> None:
    table = doc.tables[10]
    if section is None:
        _set_paragraph_text(doc, 189, _missing_note(errors, "capa_effectiveness_check_plan"), clear_italic=True)
        _ensure_row_count(table, 1, 1)
        return

    _set_paragraph_text(doc, 189, section.capa_not_applicable_justification or "", clear_italic=True)

    plans = section.generated_plans
    rows = _ensure_row_count(table, 1, len(plans))
    if not plans:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, plans)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.capa_description)
        _set_cell_text(row.cells[2], "; ".join(item.effectiveness_check))
        criteria = "; ".join(item.effectiveness_criteria)
        extra = f" (Duration: {item.monitoring_duration} — {item.duration_tier})"
        _set_cell_text(row.cells[3], criteria + extra)
        _set_cell_text(row.cells[4], item.responsibility)


# Body-paragraph indices of every major heading in the real template — a
# page break is forced immediately before each one so every section starts
# on its own page (2026-08-25, per the user), matching how a real printed/
# reviewed investigation report is organized. In heading order: Executive
# Summary, Description of Event, Initial Impact Assessment, Summary of
# Historical Review, Investigation Task, Root Cause conclusion, Impact
# Assessment & Conclusion, Correction and/or Remedial Action, Corrective &
# Preventive Action (CAPA), CAPA Effectiveness Check Plan, List of
# Annexures, Report Approval. Risk Assessment has no heading of its own
# (see module docstring) so it isn't included. Indices are fixed at the
# TEMPLATE's own layout, not affected by _strip_guidance_runs (which only
# ever removes pure-guidance paragraphs, never a heading).
_SECTION_HEADING_INDICES = [53, 92, 95, 110, 128, 133, 163, 172, 177, 186, 193, 196]


def _add_page_breaks(doc) -> None:
    for index in _SECTION_HEADING_INDICES:
        _body_paragraph(doc, index).paragraph_format.page_break_before = True


# ── 13. Annexures & Approval (pure pass-through, never None) ────────────

def _fill_annexures(doc, section) -> None:
    table = doc.tables[11]
    rows = _ensure_row_count(table, 1, len(section.items))
    for row, item in zip(rows, section.items):
        _set_cell_text(row.cells[0], item.annexure_no)
        _set_cell_text(row.cells[1], item.title)


_APPROVAL_ROLE_LABELS = {
    "investigator": 1,
    "hod": 2,
    "qa": 3,
    "sit": 4,
    "head-qa": 5,
    "head qa": 5,
}


def _fill_approval(doc, section) -> None:
    table = doc.tables[12]
    for row in section.rows:
        row_idx = _APPROVAL_ROLE_LABELS.get(row.role.strip().lower())
        if row_idx is None:
            continue
        target = table.rows[row_idx]
        _set_cell_text(target.cells[1], row.name or "")
        _set_cell_text(target.cells[2], row.title or "")
        _set_cell_text(target.cells[3], row.department or "")
        _set_cell_text(target.cells[4], row.signature_date or "")


def _tw_text(trackwise_fields: Dict[str, Any], *keys: str) -> str:
    """First non-empty TrackWise field among `keys`, stringified — values
    here can be a plain string, a list (joined), or a number
    (dim_rci.rci_key, unlike every other TrackWise field, is an int)."""
    for key in keys:
        value = trackwise_fields.get(key)
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if value:
            return str(value)
    return ""


def _fill_header_table(doc, record_id: str, trackwise_fields: Dict[str, Any]) -> None:
    table = doc.sections[0].header.tables[0]
    _set_cell_text(table.rows[1].cells[1], _tw_text(trackwise_fields, "Product Name / Material Name", "Products Information"))
    _set_cell_text(table.rows[1].cells[3], _tw_text(trackwise_fields, "Product / Material Code"))
    _set_cell_text(table.rows[2].cells[1], record_id)
    _set_cell_text(table.rows[2].cells[3], _tw_text(trackwise_fields, "RCI Number"))
    _set_cell_text(table.rows[3].cells[1], _tw_text(trackwise_fields, "Batch Number / AR Number"))
    _set_cell_text(table.rows[3].cells[3], _tw_text(trackwise_fields, "Date Opened", "Date Complaint Received"))


def build_rci_report_docx(record_id: str, trackwise_fields: Dict[str, Any], report: RciReportSections) -> bytes:
    doc = docx.Document(str(TEMPLATE_PATH))
    errors = report.errors or {}

    _add_page_breaks(doc)
    _fill_header_table(doc, record_id, trackwise_fields)
    _fill_executive_summary(doc, report.executive_summary, errors)
    _fill_description_of_event(doc, report.description_of_event, errors)
    _fill_initial_impact_assessment(doc, report.initial_impact_assessment, errors)
    _fill_history_review(doc, report.history_review, errors)
    _fill_investigation_task(doc, report.investigation_task, errors)
    _fill_root_cause_conclusion(doc, report.root_cause_conclusion, errors)
    _fill_impact_assessment_batch_disposition(doc, report.impact_assessment_batch_disposition, report.risk_assessment, errors)
    _fill_correction_remedial_action(doc, report.correction_remedial_action, errors)
    _fill_capa(doc, report.capa, errors)
    _fill_capa_effectiveness_check_plan(doc, report.capa_effectiveness_check_plan, errors)
    _fill_annexures(doc, report.annexures)
    _fill_approval(doc, report.approval)

    # Must run last — every _fill_* call above still relies on this
    # template's original body-paragraph indices, which shift as soon as
    # any of these are deleted.
    _strip_guidance_runs(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
