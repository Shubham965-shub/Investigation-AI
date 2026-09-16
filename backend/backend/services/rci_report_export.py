"""Fills the RCI Report Word template (assets/rci_report_template.docx) in place, preserving its borders/merges/styling.
Template: header table (record/RCI ids); table 0 = index/TOC; Executive Summary is body paragraphs (no table), 6 sub-headings; table 1 = Description of Event; tables 2/3 = Initial Impact material/equipment; table 4 = History Review; table 5 = Root Cause conclusion; Correction/Remedial Action is paragraphs, no table; tables 6/7/8 = CAPA actions/interim/extrapolation; table 9 = CAPA effectiveness; table 10 = Annexures; table 11 = Approval (fixed role rows).
RiskAssessmentSection has no template slot — appended into Impact Assessment's trailing paragraph instead, clearly labeled.
Every RciReportSections field is Optional; a None section gets one clear note at its first slot (from `errors`) rather than being left ambiguous.
"""
from __future__ import annotations

import copy
import io
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from pypdf import PdfReader

from backend.schemas.rci_report import RciReportSections

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "rci_report_template.docx"

MISSING_NOTE_FALLBACK = "This section could not be generated — the related TrackWise field(s) aren't filled."

# Template text is 11pt despite the doc's Normal style defaulting to 12pt — a fresh run would silently inherit 12pt, so force it explicitly. Table content is one step down at 10pt.
FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(11)
TABLE_FONT_SIZE = Pt(10)


def _apply_font(run, size=None) -> None:
    run.font.name = FONT_NAME
    run.font.size = size or FONT_SIZE


def _missing_note(errors: dict, key: str) -> str:
    return f"[{errors.get(key) or MISSING_NOTE_FALLBACK}]"


# C0/C1 control chars aren't legal XML 1.0 text and lxml raises on them (seen live: a stray 0x13 where an en-dash was meant) — strip defensively at write time.
_INVALID_XML_CHARS_RE = re.compile("[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")


def _xml_safe(text: str) -> str:
    return _INVALID_XML_CHARS_RE.sub("", text) if text else text


def _set_cell_text(cell, text: str) -> None:
    """Always inside a table — locked to TABLE_FONT_SIZE (10pt), one step
    down from body content's 11pt."""
    cell.text = _xml_safe(text) or ""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            _apply_font(run, TABLE_FONT_SIZE)


class _Cursor:
    """Wraps `doc` with a running paragraph-index offset — hardcoded indices are the RAW TEMPLATE's positions, but expanding a slot into several real paragraphs (_set_bulleted_paragraphs) shifts every later index by (N-1). `.paragraph(index)` resolves against template index + offset; `.doc` still works for `.tables[N]` since tables aren't affected."""

    def __init__(self, doc):
        self.doc = doc
        self.offset = 0

    def paragraph(self, index: int) -> Paragraph:
        return Paragraph(self.doc.element.body[index + self.offset], self.doc)


# Shared hanging indent + matching tab stop so a bullet's "•" sits flush and wrapped continuation lines land at the same indent everywhere.
_BULLET_HANG = Pt(18)


def _set_paragraph_text(cursor: _Cursor, index: int, text: str, clear_italic: bool = False) -> None:
    """Reuses the first run's formatting, clearing the rest so no guidance text lingers; font/size are always force-set since a blank paragraph's run has neither. `clear_italic` also blackens color, for slots where the answer replaces guidance text itself (which is grey+italic). left/first_line indent reset to 0 — the template's ad hoc indent values otherwise mismatch a wrapped line against its own first line."""
    text = _xml_safe(text)
    para = cursor.paragraph(index)
    para.paragraph_format.left_indent = 0
    para.paragraph_format.first_line_indent = 0
    if para.runs:
        run = para.runs[0]
        run.text = text
        if clear_italic:
            run.italic = False
            run.font.color.rgb = RGBColor(0, 0, 0)
        for extra in para.runs[1:]:
            extra.text = ""
    else:
        run = para.add_run(text)
        if clear_italic:
            run.italic = False
            run.font.color.rgb = RGBColor(0, 0, 0)
    _apply_font(run)


def _set_paragraph_lines(cursor: _Cursor, index: int, lines: List, clear_italic: bool = False) -> None:
    """Like _set_paragraph_text, but joins lines with real line breaks for narrative content never bulleted in any real report (History Review, Investigation Task, etc). A line may be a `(text, bold)` tuple — bold is run-level, so each such line gets its own run. left/first_line indent reset to 0, same reason as _set_paragraph_text."""
    def _split(line):
        text, bold = line if isinstance(line, tuple) else (line, False)
        return _xml_safe(text), bold

    lines = [line for line in lines if _split(line)[0]]
    para = cursor.paragraph(index)
    para.paragraph_format.left_indent = 0
    if len(lines) > 1:
        para.paragraph_format.first_line_indent = 0

    first_run = para.runs[0] if para.runs else para.add_run()
    # Clear other pre-existing template runs before adding new ones below.
    for extra in list(para.runs[1:]):
        extra.text = ""

    text0, bold0 = _split(lines[0]) if lines else ("", False)
    first_run.text = text0
    first_run.bold = bold0
    if clear_italic:
        first_run.italic = False
    _apply_font(first_run)

    for line in lines[1:]:
        text, bold = _split(line)
        run = para.add_run()
        run.add_break()
        # add_text() would insert a literal tab character, not a real <w:tab/> tab-stop jump — split and use add_tab() instead.
        for i, part in enumerate(text.split("\t")):
            if i > 0:
                run.add_tab()
            if part:
                run.add_text(part)
        run.bold = bold
        if clear_italic:
            run.italic = False
        _apply_font(run)


def _set_bulleted_paragraphs(cursor: _Cursor, index: int, lines: List[str], clear_italic: bool = False, hanging: bool = True) -> None:
    """One genuine paragraph per item (not soft-broken lines in one paragraph) — Word's hanging indent only recognizes one "first line" per paragraph, so each item needs its own to indent wrapped continuation lines correctly.
    `hanging=True` applies the hanging indent + tab stop for bulleted content; `hanging=False` keeps items flush left (real OOS reports use unbulleted separate paragraphs).
    Clones the anchor paragraph's XML per extra item and bumps `cursor.offset` by (item count - 1), same accounting as _Cursor."""
    lines = [_xml_safe(line) for line in lines if line]
    para = cursor.paragraph(index)
    if hanging:
        para.paragraph_format.left_indent = _BULLET_HANG
        para.paragraph_format.first_line_indent = -_BULLET_HANG
        para.paragraph_format.tab_stops.clear_all()
        para.paragraph_format.tab_stops.add_tab_stop(_BULLET_HANG, WD_TAB_ALIGNMENT.LEFT)
    else:
        para.paragraph_format.left_indent = 0
        para.paragraph_format.first_line_indent = 0
    para.paragraph_format.space_after = Pt(10)

    def _fill_one(target_para: Paragraph, text: str) -> None:
        run = target_para.runs[0] if target_para.runs else target_para.add_run()
        for extra in list(target_para.runs[1:]):
            extra.text = ""
        # run.text= doesn't translate an embedded tab into a real <w:tab/> element — split and add_tab() explicitly.
        run.text = ""
        for i, part in enumerate(text.split("\t")):
            if i > 0:
                run.add_tab()
            if part:
                run.add_text(part)
        if clear_italic:
            run.italic = False
            run.font.color.rgb = RGBColor(0, 0, 0)
        _apply_font(run)

    if not lines:
        _fill_one(para, "")
        return

    _fill_one(para, lines[0])
    prev_p = para._p
    for line in lines[1:]:
        new_p = copy.deepcopy(para._p)
        prev_p.addnext(new_p)
        prev_p = new_p
        _fill_one(Paragraph(new_p, cursor.doc), line)
    cursor.offset += len(lines) - 1


def _strip_guidance_runs(doc) -> None:
    """Removes every italic run from every top-level body paragraph — this template styles pure guidance text as italic. Slots overwritten in place already had clear_italic applied, so real content survives untouched. A paragraph left empty is removed entirely."""
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
    """Adjusts `table` to exactly `max(count, 1)` data rows, cloning/dropping as needed. Always keeps at least one row — a blank/"N/A" row reads better than headers-only. Returns the data rows."""
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


# Real reports bullet these sections only for Deviation; OOS/OOT/Market Complaint stay plain (OOT samples were mixed, so defaults to plain on weak evidence).
def _maybe_bullet(lines: List[str], event_type: str) -> List[str]:
    if event_type != "Deviation":
        return lines
    return [f"•\t{line}" for line in lines]


def _sourced(item) -> str:
    return item.value if item else ""


def _yesno(value: bool) -> str:
    return "Yes" if value else "No"


def _insert_heading_paragraph(cursor: _Cursor, index: int, heading_text: str) -> None:
    """Inserts a new bold, spaced-apart heading paragraph directly before the paragraph at `index`, cloning its XML first. Bumps `cursor.offset` by 1, same accounting as _Cursor."""
    anchor = cursor.paragraph(index)
    heading_p = copy.deepcopy(anchor._p)
    anchor._p.addprevious(heading_p)
    heading_para = Paragraph(heading_p, cursor.doc)
    heading_para.paragraph_format.left_indent = 0
    heading_para.paragraph_format.first_line_indent = 0
    heading_para.paragraph_format.space_before = Pt(12)
    heading_para.paragraph_format.space_after = Pt(6)
    run = heading_para.runs[0] if heading_para.runs else heading_para.add_run()
    for extra in list(heading_para.runs[1:]):
        extra.text = ""
    run.text = heading_text
    run.bold = True
    run.italic = False
    run.font.color.rgb = RGBColor(0, 0, 0)
    _apply_font(run)
    cursor.offset += 1


# ── 1. Executive Summary ────────────────────────────────────────────────

def _fill_executive_summary(cursor: _Cursor, section, event_type: str, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(cursor, 55, _missing_note(errors, "executive_summary"))
        return
    # OOS (and the combined "OOS/OOT") renders this narrative as plain unbulleted sentences; every other event type bullets it.
    is_plain = event_type in ("OOS", "OOS/OOT")

    # Each field is a list of bullet-point strings from the LLM — just needs the "•\t" prefix _set_bulleted_paragraphs expects.
    def lines_for(items: List[str]) -> List[str]:
        return list(items) if is_plain else [f"•\t{item}" for item in items]

    # Paragraph 55 (section.summary) is deliberately left unpopulated — a blank slot with no runs, so _strip_guidance_runs removes it entirely.
    _set_bulleted_paragraphs(cursor, 59, lines_for(section.problem_description), hanging=not is_plain)
    _set_bulleted_paragraphs(cursor, 64, lines_for(section.immediate_containment_action), hanging=not is_plain)
    _set_bulleted_paragraphs(cursor, 71, lines_for(section.determination_of_root_cause), hanging=not is_plain)
    _set_bulleted_paragraphs(cursor, 74, lines_for(section.root_cause_probable_cause_statement), clear_italic=True, hanging=not is_plain)
    _set_bulleted_paragraphs(cursor, 80, lines_for(section.impact_assessment), hanging=not is_plain)
    _set_bulleted_paragraphs(cursor, 86, lines_for(section.correction_conclusion_preventive_actions), hanging=not is_plain)
    # Conclusion Statement gets its own bold heading; _insert_heading_paragraph bumps cursor.offset so this call (still "87") hits the original content paragraph.
    _insert_heading_paragraph(cursor, 87, "Conclusion Statement")
    _set_bulleted_paragraphs(cursor, 87, lines_for(section.conclusion_statement), hanging=not is_plain)


# ── 2. Description of Event ─────────────────────────────────────────────

def _fill_description_of_event(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[1]
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

def _fill_initial_impact_assessment(cursor: _Cursor, section, event_type: str, errors: dict) -> None:
    material_table = cursor.doc.tables[2]
    equipment_table = cursor.doc.tables[3]
    if section is None:
        rows = _ensure_row_count(material_table, 1, 1)
        _set_cell_text(rows[0].cells[1], _missing_note(errors, "initial_impact_assessment"))
        _ensure_row_count(equipment_table, 1, 1)
        _set_paragraph_text(cursor, 107, "")
        return

    impacts = section.material_product_impacts
    rows = _ensure_row_count(material_table, 1, len(impacts))
    if not impacts:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, impacts)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.material_product_batch)
        _set_cell_text(row.cells[2], item.batch_number)
        # cells[3] header is "Action taken (Hold/Quarantined etc.)" — lead with hold status, not the impact classification which isn't such an action.
        hold_status = f"On hold: {_sourced(item.quantity_on_hold)}" if _sourced(item.quantity_on_hold) else "No hold/quarantine action recorded"
        action = f"{hold_status} (Qty involved: {item.quantity_involved}; Impact: {item.type_of_impact})"
        _set_cell_text(row.cells[3], action)

    equip = section.equipment_impacts
    rows = _ensure_row_count(equipment_table, 1, len(equip))
    if not equip:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, equip)):
        _set_cell_text(row.cells[0], str(i + 1))
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

    is_deviation = event_type == "Deviation"
    _set_bulleted_paragraphs(cursor, 107, _maybe_bullet(section.immediate_actions, event_type), hanging=is_deviation)


# ── 4. Summary of Historical Review ─────────────────────────────────────

def _fill_history_review(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[4]
    if section is None:
        rows = _ensure_row_count(table, 1, 1)
        _set_cell_text(rows[0].cells[2], _missing_note(errors, "history_review"))
        _set_paragraph_text(cursor, 117, "")
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
        section.search_scope_note,
        f"Lookback period: {section.lookback_months} months.",
        # Trust the table's own rows over ds's no_similar_events_found flag — the two have been observed to disagree.
        "No similar events found in the lookback window." if section.no_similar_events_found and not section.rows else "",
        section.closing_narrative,
        f"Batches manufactured: {section.batches_manufactured_note}" if section.batches_manufactured_note else "",
    ]
    _set_paragraph_lines(cursor, 117, lines)


# ── 5. Investigation Task ───────────────────────────────────────────────

def _fill_investigation_task(cursor: _Cursor, section, errors: dict):
    """Section 5: task_summary, why_why_analysis, then root_cause_identification, in that order — Why-Why is the only RCA method this section demonstrates.
    Only task_summary/why_why header go into paragraph 132 here; the Why-Why table and root_cause_identification are appended later by _insert_why_why_table_and_grounding (must run after every other _fill_* call). Returns the paragraph-132 element captured now so that later call can anchor off it regardless of subsequent cursor.offset growth.
    Paragraph 132's template style is "Heading 1" (inherited from the section heading above it), unlike every other section's blank — reset to "Normal" so real content doesn't render as an oversized heading.
    """
    cursor.paragraph(132).style = "Normal"

    if section is None:
        _set_paragraph_text(cursor, 132, _missing_note(errors, "investigation_task"))
        return None

    # Grouped under a "N. <6M factor>" heading whenever six_m_factor changes; group number is read off task.tick ("<group>.<item>") so they can't drift apart.
    lines = [section.task_summary.overview, ""]
    last_group: Optional[str] = None
    for task in section.task_summary.tasks:
        group = task.tick.split(".", 1)[0]
        if group != last_group:
            lines.append((f"{group}.\t{task.six_m_factor}", True))
            last_group = group
        lines.append("")
        lines.append(f"{task.tick}\t{task.title} ({task.six_m_factor}): {task.outcome}")

    lines.append("")
    demo = section.why_why_analysis
    lines.append(f"Why-Why Analysis (6M Factor: {demo.six_m_factor}): {demo.method_rationale}")
    lines.append("  See table below.")

    _set_paragraph_lines(cursor, 132, lines)
    return cursor.paragraph(132)._p


def _insert_why_why_table_and_grounding(doc, section, anchor) -> None:
    """Inserts the Why-Why Analysis table after the Investigation Task paragraph, then root_cause_identification's grounding evidence after that table.
    MUST run after every other _fill_* call — first place in this file that inserts a brand-new top-level body element rather than mutating in place. `anchor` is the actual element captured earlier, so it stays valid regardless of later cursor.offset growth.
    """
    if section is None or anchor is None:
        return
    reference_style = doc.tables[1].style  # Description of Event — a plain 2-column table

    demo = section.why_why_analysis
    table = doc.add_table(rows=1 + len(demo.why_why_chain), cols=2)
    table.style = reference_style
    header_cells = table.rows[0].cells
    _set_cell_text(header_cells[0], "Question")
    _set_cell_text(header_cells[1], "Answer")
    for cell in header_cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for row, step in zip(table.rows[1:], demo.why_why_chain):
        _set_cell_text(row.cells[0], step.question)
        _set_cell_text(row.cells[1], step.answer)
    anchor.addnext(table._tbl)
    anchor = table._tbl

    grounding_lines = [
        "Root cause identification:",
        section.root_cause_identification.grounding_evidence,
    ]
    for link in section.root_cause_identification.applicable_tasks:
        grounding_lines.append(f"  {link.tick}\t{link.title} ({link.six_m_factor}): {link.explanation}")
    grounding_lines = [_xml_safe(line) for line in grounding_lines]

    new_para = doc.add_paragraph()
    run = new_para.add_run(grounding_lines[0])
    for line in grounding_lines[1:]:
        run.add_break()
        run.add_text(line)
    _apply_font(run)
    anchor.addnext(new_para._p)


# ── 6. Root Cause conclusion ─────────────────────────────────────────────

def _fill_root_cause_conclusion(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[5]
    if section is None:
        _set_cell_text(table.rows[1].cells[0], _missing_note(errors, "root_cause_conclusion"))
        return
    _set_cell_text(table.rows[1].cells[0], section.conclusion)
    repeat_para = table.rows[1].cells[0].add_paragraph(
        _xml_safe(f"Repeat occurrence: {_yesno(section.is_repeat_occurrence)} — {section.repeat_occurrence_evidence}")
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


def _fill_impact_assessment_batch_disposition(cursor: _Cursor, section, risk_section, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(cursor, 165, _missing_note(errors, "impact_assessment_batch_disposition"))
    else:
        lines = []
        for field_name, label in _IMPACT_SUBSECTION_LABELS:
            sub = getattr(section, field_name)
            # Renders even when not applicable — otherwise a reader can't tell "considered, ruled out" from "never considered."
            lines.append(f"{label}: {sub.narrative}")
            if field_name == "impact_on_affected_batches" and sub.batch_shipper_table:
                for row in sub.batch_shipper_table:
                    lines.append(f"  - Batch {row.batch_number}: {row.number_of_shippers} shipper(s), defects: {row.defects}")
        _set_paragraph_lines(cursor, 165, lines)
        _set_paragraph_text(cursor, 170, f"Conclusion Statement: {section.conclusion}", clear_italic=True)

    extra_lines = []
    if section is not None:
        if section.medical_investigation_summary:
            extra_lines.append(f"Medical Investigation Summary: {section.medical_investigation_summary}")
        if section.health_hazard_evaluation:
            extra_lines.append(f"Health Hazard Evaluation: {section.health_hazard_evaluation}")
        if section.impact_justification:
            extra_lines.append(f"Impact Justification: {section.impact_justification}")

    # No template slot for Risk Assessment — appended here, clearly labeled, rather than silently dropped.
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
    _set_paragraph_lines(cursor, 171, extra_lines)


# ── 8. Correction and/or Remedial Action ────────────────────────────────

def _fill_correction_remedial_action(cursor: _Cursor, section, event_type: str, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(cursor, 173, _missing_note(errors, "correction_remedial_action"))
        _set_paragraph_text(cursor, 174, "")
        return
    lines = [f"{item.observation} — Status: {item.status}" + (f" [Ref: {item.reference_number}]" if item.reference_number else "") for item in section.items]
    is_deviation = event_type == "Deviation"
    _set_bulleted_paragraphs(cursor, 173, _maybe_bullet(lines or ["N/A"], event_type), hanging=is_deviation)
    _set_bulleted_paragraphs(cursor, 174, _maybe_bullet(section.additional_notes, event_type), hanging=is_deviation)


# ── 9/10/11. CAPA (actions / interim controls / extrapolation) ─────────

def _fill_capa(cursor: _Cursor, section, errors: dict) -> None:
    actions_table = cursor.doc.tables[6]
    interim_table = cursor.doc.tables[7]
    extrapolation_table = cursor.doc.tables[8]

    if section is None:
        _set_paragraph_text(cursor, 180, _missing_note(errors, "capa"))
        rows = _ensure_row_count(actions_table, 1, 1)
        _set_cell_text(rows[0].cells[1], _missing_note(errors, "capa"))
        _ensure_row_count(interim_table, 1, 1)
        _ensure_row_count(extrapolation_table, 1, 1)
        return

    _set_paragraph_text(cursor, 180, section.capa_not_applicable_justification or "")

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

def _fill_capa_effectiveness_check_plan(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[9]
    if section is None:
        _set_paragraph_text(cursor, 188, _missing_note(errors, "capa_effectiveness_check_plan"), clear_italic=True)
        _ensure_row_count(table, 1, 1)
        return

    _set_paragraph_text(cursor, 188, section.capa_not_applicable_justification or "", clear_italic=True)

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


# Body-paragraph indices of every major heading (template's own layout, fixed order) — a page break is forced before each so every section starts on its own page. Risk Assessment has no heading of its own, so it isn't included.
_SECTION_HEADING_INDICES = [53, 92, 95, 110, 128, 133, 163, 172, 176, 185, 192, 195]

# One bookmark per heading above, same order — lets the Index table's "Page No." column reference each section via a PAGEREF field (Word resolves these on open; python-docx can't paginate).
_SECTION_BOOKMARK_NAMES = [
    "sec_executive_summary",
    "sec_description_of_event",
    "sec_initial_impact_assessment",
    "sec_historical_review",
    "sec_investigation_tasks",
    "sec_root_cause_conclusion",
    "sec_impact_assessment_conclusion",
    "sec_correction_remedial_action",
    "sec_capa",
    "sec_effectiveness_check_plan",
    "sec_annexures",
    "sec_approval",
]


def _insert_bookmark(paragraph: Paragraph, bookmark_id: int, name: str) -> None:
    p = paragraph._p
    pPr = p.find(qn("w:pPr"))
    index = list(p).index(pPr) + 1 if pPr is not None else 0

    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))

    p.insert(index, start)
    p.insert(index + 1, end)


def _add_page_breaks(cursor: _Cursor) -> List[str]:
    # Called first, before any bulleted-paragraph expansion, so cursor.offset is still 0. Also plants each section's bookmark here for the same reason.
    # Returns heading texts (same order as _SECTION_BOOKMARK_NAMES) so _compute_section_page_numbers can locate each in a rendered PDF even if wording changes.
    heading_texts: List[str] = []
    for bookmark_id, (index, name) in enumerate(zip(_SECTION_HEADING_INDICES, _SECTION_BOOKMARK_NAMES)):
        heading = cursor.paragraph(index)
        heading.paragraph_format.page_break_before = True
        _insert_bookmark(heading, bookmark_id, name)
        heading_texts.append(heading.text.strip())
    return heading_texts


def _set_cell_pageref(cell, bookmark_name: str) -> None:
    """Replaces a cell's content with a Word PAGEREF field pointing at `bookmark_name`; Word computes the real page number on open ("1" is just the unresolved placeholder)."""
    cell.text = ""
    paragraph = cell.paragraphs[0]
    p = paragraph._p
    for old_run in list(paragraph.runs):
        p.remove(old_run._element)

    def _field_char(fld_type: str, dirty: bool = False):
        run_el = OxmlElement("w:r")
        fld = OxmlElement("w:fldChar")
        fld.set(qn("w:fldCharType"), fld_type)
        if dirty:
            fld.set(qn("w:dirty"), "true")
        run_el.append(fld)
        return run_el

    begin_run = _field_char("begin", dirty=True)

    instr_run = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" PAGEREF {bookmark_name} \\h "
    instr_run.append(instr)

    separate_run = _field_char("separate")

    result_run = OxmlElement("w:r")
    result_text = OxmlElement("w:t")
    result_text.text = "1"
    result_run.append(result_text)

    end_run = _field_char("end")

    for run_el in (begin_run, instr_run, separate_run, result_run, end_run):
        p.append(run_el)
        _apply_font(Run(run_el, paragraph), TABLE_FONT_SIZE)


def _fill_index_page_numbers(cursor: _Cursor) -> None:
    table = cursor.doc.tables[0]
    for row_offset, name in enumerate(_SECTION_BOOKMARK_NAMES):
        _set_cell_pageref(table.rows[row_offset + 1].cells[3], name)


def _normalize_for_search(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _compute_section_page_numbers(docx_bytes: bytes, heading_texts: List[str]) -> List[int]:
    """Renders `docx_bytes` to PDF via headless LibreOffice and returns each heading's real 1-based page number, since python-docx never lays out text/paginates.
    Raises on any failure — callers MUST catch broadly and fall back to PAGEREF-field behavior rather than let a rendering hiccup break the export.
    Searches monotonically forward from the previous heading's page, since sections are always filled in the same fixed order.
    """
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("soffice/libreoffice not found on PATH")

    with tempfile.TemporaryDirectory() as tmp_dir:
        docx_path = Path(tmp_dir) / "report.docx"
        docx_path.write_bytes(docx_bytes)
        subprocess.run(
            [soffice, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", tmp_dir, str(docx_path)],
            check=True,
            timeout=90,
            capture_output=True,
        )
        pdf_path = docx_path.with_suffix(".pdf")
        if not pdf_path.exists():
            raise RuntimeError("soffice did not produce a PDF output file")

        reader = PdfReader(str(pdf_path))
        page_texts = [_normalize_for_search(page.extract_text() or "") for page in reader.pages]

    page_numbers: List[int] = []
    search_from = 0
    for heading in heading_texts:
        # First ~40 normalized chars: long enough for a confident match, short enough to stay robust to PDF text-extraction glitches further in.
        needle = _normalize_for_search(heading)[:40]
        if not needle:
            raise RuntimeError(f"Empty heading text, cannot locate a page for it: {heading!r}")
        found_at = next((i for i in range(search_from, len(page_texts)) if needle in page_texts[i]), None)
        if found_at is None:
            raise RuntimeError(f"Could not locate heading in the rendered PDF: {heading!r}")
        page_numbers.append(found_at + 1)  # 1-based
        search_from = found_at

    return page_numbers


def _enable_field_auto_update(doc) -> None:
    # settings.append() puts <w:updateFields> after <w:rsid>, the wrong OOXML schema slot — Word silently ejects it there instead of erroring. Inserting as the first child sidesteps the ordering requirement entirely.
    settings = doc.settings.element
    update_fields = OxmlElement("w:updateFields")
    update_fields.set(qn("w:val"), "true")
    settings.insert(0, update_fields)


# ── 13. Annexures & Approval (pure pass-through, never None) ────────────

def _fill_annexures(cursor: _Cursor, section) -> None:
    table = cursor.doc.tables[10]
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


def _fill_approval(cursor: _Cursor, section) -> None:
    table = cursor.doc.tables[11]
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
    """First non-empty TrackWise field among `keys`, stringified — values may be a plain string, a list (joined), or a number (dim_rci.rci_key is an int)."""
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


def build_rci_report_docx(record_id: str, trackwise_fields: Dict[str, Any], report: RciReportSections, event_type: str) -> bytes:
    doc = docx.Document(str(TEMPLATE_PATH))
    errors = report.errors or {}
    # Sections MUST run in the same top-to-bottom order they appear in the document — each one that expands into several paragraphs grows cursor.offset immediately, so a call running out of order would resolve against the wrong paragraph.
    cursor = _Cursor(doc)

    heading_texts = _add_page_breaks(cursor)
    _fill_index_page_numbers(cursor)
    _fill_header_table(doc, record_id, trackwise_fields)
    _fill_executive_summary(cursor, report.executive_summary, event_type, errors)
    _fill_description_of_event(cursor, report.description_of_event, errors)
    _fill_initial_impact_assessment(cursor, report.initial_impact_assessment, event_type, errors)
    _fill_history_review(cursor, report.history_review, errors)
    investigation_task_anchor = _fill_investigation_task(cursor, report.investigation_task, errors)
    _fill_root_cause_conclusion(cursor, report.root_cause_conclusion, errors)
    _fill_impact_assessment_batch_disposition(cursor, report.impact_assessment_batch_disposition, report.risk_assessment, errors)
    _fill_correction_remedial_action(cursor, report.correction_remedial_action, event_type, errors)
    _fill_capa(cursor, report.capa, errors)
    _fill_capa_effectiveness_check_plan(cursor, report.capa_effectiveness_check_plan, errors)
    _fill_annexures(cursor, report.annexures)
    _fill_approval(cursor, report.approval)

    # Must run after every _fill_* call above — inserts new body elements, which would shift every fixed index still relied on above.
    _insert_why_why_table_and_grounding(doc, report.investigation_task, investigation_task_anchor)

    # Must run last — reads final paragraph structure directly, not by index; each _fill_* call above still needs its guidance runs intact until written.
    _strip_guidance_runs(doc)
    _enable_field_auto_update(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    docx_bytes = buffer.getvalue()

    # Best-effort real pagination: overwrites the Index table's PAGEREF fields with static page numbers from an actual LibreOffice render — correct on open, unlike PAGEREF which needs a manual refresh. Any failure just leaves the PAGEREF fields in place.
    try:
        page_numbers = _compute_section_page_numbers(docx_bytes, heading_texts)
        index_table = doc.tables[0]
        for row_offset, page_number in enumerate(page_numbers):
            _set_cell_text(index_table.rows[row_offset + 1].cells[3], str(page_number))
        buffer = io.BytesIO()
        doc.save(buffer)
        docx_bytes = buffer.getvalue()
    except Exception:
        logger.warning(
            "Could not compute real RCI Report TOC page numbers via LibreOffice; "
            "falling back to Word PAGEREF fields (needs a manual field refresh)",
            exc_info=True,
        )

    return docx_bytes
