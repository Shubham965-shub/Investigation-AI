"""Fills the RCI Plan Word template (assets/rci_plan_template.docx) in place, preserving its borders/merges/styling — only blank text runs are replaced.
Template layout: outer row 2 = nested Event Details table; row 3 = blank/manual entry; row 4 = description placeholder paragraph; row 6 = nested Investigation tasks table (6 fixed 3-row blocks, only each block's first row is filled, the other two deleted); row 8/9 = Sign-off headers/values (col 0 is a blank label column, not the Investigator slot).
`cell.text = ...` wipes a cell's ENTIRE content including any nested table — never call it on a cell whose only content is a nested table.
"""
from __future__ import annotations

import copy
import datetime
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH

from backend.schemas.rci_plan import RciPrerequisiteChecklist, RciSectionItem

_PREREQUISITE_CHECKLIST_ITEMS = (
    ("bench_top_verification_done", "Bench-top verification done?"),
    ("preliminary_checklist_done", "Preliminary investigation checklist done?"),
    ("personnel_interview_done", "Personnel interview done?"),
    ("photographic_evidence_collected", "Photographic evidence collected?"),
)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "rci_plan_template.docx"

# 6 fixed task-number slots; sections beyond this are dropped (not silently — surfaced via the returned `truncated` count).
MAX_TEMPLATE_SECTIONS = 6

# Sign-off row only has 4 Task Owner slots; sections beyond this still get their tasks listed, just no named owner there.
MAX_SIGN_OFF_OWNERS = 4


def _set_cell_text(cell, text: str) -> None:
    """cell.text = ... creates runs with no explicit font, silently inheriting the template's Calibri-like default instead of Times New Roman — force it."""
    cell.text = text or ""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.font.name = "Times New Roman"


def _format_ddmmyyyy(iso: Optional[str]) -> str:
    """due_date is a plain "yyyy-mm-dd" string; exported as dd/mm/yyyy to match the RCI Plan page's read-only display."""
    if not iso:
        return ""
    parts = iso.split("-")
    if len(parts) != 3:
        return iso
    y, m, d = parts
    return f"{d}/{m}/{y}"


def _set_description_paragraph(doc, text: str) -> None:
    """Replaces the template's instructional placeholder paragraph — the
    cell at outer row 4 whose text starts with "A description of what has
    happened" — with the real problem statement/description text."""
    outer = doc.tables[0]
    cell = outer.rows[4].cells[1]
    if cell.paragraphs:
        # Reuse the first paragraph/run to keep its formatting; clear the rest so placeholder text doesn't linger.
        first = cell.paragraphs[0]
        if first.runs:
            first.runs[0].text = text
            first.runs[0].font.name = "Times New Roman"
            for run in first.runs[1:]:
                run.text = ""
        else:
            first.add_run(text).font.name = "Times New Roman"
        for para in cell.paragraphs[1:]:
            for run in para.runs:
                run.text = ""
    else:
        _set_cell_text(cell, text)


def _set_problem_statement_label(doc) -> None:
    """Labels the box above the description paragraph as "Problem Statement" — the template otherwise gives no indication of what it holds."""
    outer = doc.tables[0]
    cell = outer.rows[3].cells[1]
    _set_cell_text(cell, "Problem Statement")
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in paragraph.runs:
            run.font.bold = True


def _insert_prerequisite_checklist_rows(outer, checklist: RciPrerequisiteChecklist) -> None:
    """Inserts "1.5 Pre-requisite of Investigation Plan" as 2 new rows directly before the
    "2.0 Investigation tasks" header row (outer.rows[5] at the time this runs, before either
    insertion) — a header row (cloned from that same row's merged-header style) plus a content
    row holding a small nested Y/N table (cloned from the Investigation tasks row's "wide merged
    cell holding a nested table" structure, then swapped for a fresh 2-column checklist table).
    Every row index from here on shifts by +2 — callers must use the POST-insertion indices."""
    tasks_header_row = outer.rows[5]
    tasks_content_row = outer.rows[6]

    # Header row: clone the tasks header's merged-cell style, relabel to "1.5".
    new_header_tr = copy.deepcopy(tasks_header_row._tr)
    tasks_header_row._tr.addprevious(new_header_tr)
    new_header_row = outer.rows[5]  # the row we just inserted, now at the old tasks-header's slot
    _set_cell_text(new_header_row.cells[0], "1.5")
    _set_cell_text(new_header_row.cells[1], "Pre-requisite of Investigation Plan")

    # Content row: clone the tasks content row's "wide merged cell holding a nested table" style,
    # then discard the cloned nested table (an unwanted copy of the — still empty at this point —
    # Investigation tasks table) and build a fresh checklist table in its place.
    new_content_tr = copy.deepcopy(tasks_content_row._tr)
    tasks_header_row._tr.addprevious(new_content_tr)  # still before the (now-shifted) tasks header
    new_content_row = outer.rows[6]
    wide_cell = new_content_row.cells[1]
    for nested_tbl in list(wide_cell.tables):
        nested_tbl._tbl.getparent().remove(nested_tbl._tbl)
    checklist_table = wide_cell.add_table(rows=len(_PREREQUISITE_CHECKLIST_ITEMS), cols=2)
    checklist_dict = checklist.model_dump()
    for row, (field, label) in zip(checklist_table.rows, _PREREQUISITE_CHECKLIST_ITEMS):
        _set_cell_text(row.cells[0], label)
        _set_cell_text(row.cells[1], "Yes" if checklist_dict[field] else "No")


def build_rci_plan_docx(
    record_id: str,
    trackwise_fields: Dict[str, Any],
    sections: List[RciSectionItem],
    checklist: RciPrerequisiteChecklist,
) -> tuple[bytes, int, int]:
    """Returns (docx_bytes, truncated_section_count, truncated_owner_count)."""
    # Unchecked sections are excluded entirely — same "checked = keep it" convention as RciTaskItem.is_checked.
    sections = [s for s in sections if s.is_checked]

    doc = docx.Document(str(TEMPLATE_PATH))
    outer = doc.tables[0]

    # ── 1.0 Event Details ──────────────────────────────────────────────
    fields_table = outer.rows[2].cells[1].tables[0]
    value_row = fields_table.rows[1]
    # dim_investigator.investigator preferred; "Deviation Owner" and a section's assignee are weaker fallbacks for when investigator_key isn't set.
    rci_owner = (
        trackwise_fields.get("Investigator")
        or trackwise_fields.get("Deviation Owner")
        or next((s.assignee for s in sections if s.assignee), "")
    )
    _set_cell_text(value_row.cells[0], record_id)
    rci_number = trackwise_fields.get("RCI Number")
    # dim_rci.rci_key is an integer column, unlike other Trackwise fields here — stringify explicitly since cell.text requires a str.
    _set_cell_text(value_row.cells[1], str(rci_number) if rci_number is not None else "")
    _set_cell_text(value_row.cells[2], rci_owner or "")
    _set_cell_text(value_row.cells[3], datetime.date.today().strftime("%d/%m/%Y"))
    # Row 3 intentionally left blank — manual entry, not auto-filled.

    _set_problem_statement_label(doc)
    _set_description_paragraph(doc, trackwise_fields.get("description") or trackwise_fields.get("title") or "")

    # ── 1.5 Pre-requisite of Investigation Plan ─────────────────────────
    # Inserts 2 new rows before the (at this point still original-indexed) "2.0 Investigation
    # tasks" header — every row index below is the POST-insertion index (+2 from the template's
    # raw layout, see this file's module docstring).
    _insert_prerequisite_checklist_rows(outer, checklist)

    # ── 2.0 Investigation tasks ─────────────────────────────────────────
    tasks_table = outer.rows[8].cells[1].tables[0]
    truncated = max(0, len(sections) - MAX_TEMPLATE_SECTIONS)
    # Each 3-row block only gets its first row filled; the other two are deleted. Deletion happens in descending row order so earlier deletions don't shift later indices.
    rows_to_delete: List[int] = []
    for i in range(MAX_TEMPLATE_SECTIONS):
        block_start = 1 + i * 3  # header row is row 0; each section owns rows [block_start, block_start+2]
        if i < len(sections):
            section = sections[i]
            row = tasks_table.rows[block_start]
            objective = section.title if not section.correlation else f"{section.title}\n{section.correlation}"
            # Unchecked tasks excluded. Numbered "<task>.<subtask>" so subtasks stay identifiable within the one cell (the block's other rows are deleted).
            checked = [t for t in section.tasks if t.is_checked]
            details = "\n".join(f"{i + 1}.{j + 1} {t.description}" for j, t in enumerate(checked))
            _set_cell_text(row.cells[0], str(i + 1))
            # A blank objective/details/TCD shows "N/A"; "Unassigned" is already a specific-enough label on its own.
            _set_cell_text(row.cells[1], objective or "N/A")
            _set_cell_text(row.cells[2], details or "N/A")
            _set_cell_text(row.cells[3], section.assignee or "Unassigned")
            _set_cell_text(row.cells[4], _format_ddmmyyyy(section.due_date) or "N/A")
            rows_to_delete.extend([block_start + 1, block_start + 2])
        else:
            # No section for this slot at all — the whole block is unused.
            rows_to_delete.extend([block_start, block_start + 1, block_start + 2])
    for row_idx in sorted(rows_to_delete, reverse=True):
        row = tasks_table.rows[row_idx]
        row._tr.getparent().remove(row._tr)

    # ── 3.0 RCI Plan Sign-off ────────────────────────────────────────────
    # Flat table, headers at row 10 (was row 8 before the 1.5 checklist's 2 new rows above):
    # ['', 'Investigator', 'Task Owner 1'..'Task Owner 4'] — cell 0 is a blank label column, NOT the Investigator slot.
    sign_off_row = outer.rows[11]
    header_row = outer.rows[10]
    # Dedup by name (preserving first-appearance order) — otherwise a repeat name could burn a slot while a distinct owner further down gets none.
    unique_owners: List[str] = []
    for section in sections:
        name = section.assignee or "Unassigned"
        if name not in unique_owners:
            unique_owners.append(name)

    _set_cell_text(sign_off_row.cells[1], rci_owner or "N/A")
    # All 4 Task Owner slots get written, even unused ones — blank cells in this table should read "N/A", not stay truly empty.
    filled_owners = unique_owners[:MAX_SIGN_OFF_OWNERS]
    for i in range(MAX_SIGN_OFF_OWNERS):
        _set_cell_text(sign_off_row.cells[i + 2], filled_owners[i] if i < len(filled_owners) else "N/A")

    # More than 4 distinct owners: extend the SAME table with rows cloned from the header/value pair (captured pristine, before filling), 5 more slots each.
    EXTRA_OWNERS_PER_ROW = 5
    remaining_owners = unique_owners[MAX_SIGN_OFF_OWNERS:]
    owners_truncated = 0
    if remaining_owners:
        header_tr_template = copy.deepcopy(header_row._tr)
        value_tr_template = copy.deepcopy(sign_off_row._tr)
        next_owner_number = MAX_SIGN_OFF_OWNERS + 1
        for batch_start in range(0, len(remaining_owners), EXTRA_OWNERS_PER_ROW):
            batch = remaining_owners[batch_start : batch_start + EXTRA_OWNERS_PER_ROW]
            outer._tbl.append(copy.deepcopy(header_tr_template))
            outer._tbl.append(copy.deepcopy(value_tr_template))
            new_header_row = outer.rows[-2]
            new_value_row = outer.rows[-1]
            for i in range(EXTRA_OWNERS_PER_ROW):
                if i < len(batch):
                    _set_cell_text(new_header_row.cells[i + 1], f"Task Owner {next_owner_number + i}")
                    _set_cell_text(new_value_row.cells[i + 1], batch[i])
                else:
                    # Header stays blank for an unused column; value cell still gets N/A.
                    _set_cell_text(new_header_row.cells[i + 1], "")
                    _set_cell_text(new_value_row.cells[i + 1], "N/A")
            next_owner_number += len(batch)

    buffer = io.BytesIO()
    doc.save(buffer)
    # Returned separately: `truncated` sections are dropped entirely; `owners_truncated` sections keep their tasks but lose a named owner.
    return buffer.getvalue(), truncated, owners_truncated