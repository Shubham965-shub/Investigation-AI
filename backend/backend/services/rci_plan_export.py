"""Fills the company's real RCI Plan Word template (assets/rci_plan_template.docx
— supplied by the user, 2026-07-31, "New format.docx") with a generated RCI
plan's data, for the RCI Plan page's "Accept and Push to TW" download.

The template is a single outer table with 3 numbered sections (1.0 Event
Details, 2.0 Investigation tasks, 3.0 RCI Plan Sign-off), each containing a
nested table for its actual fillable fields — confirmed via python-docx
introspection (see PR discussion, 2026-07-31):
  - outer row 2 -> nested 2x4 table: header row (Parent record number / RCI
    Number / RCI Owner / RCI Initiated on) + one blank row to fill.
  - outer row 4 -> a single instructional paragraph ("A description of what
    has happened...") that stands in for the description field itself.
  - outer row 6 -> nested 19x5 table: header row + 6 task-number blocks of
    3 rows each (S.No. is vertically merged per block) — one block per RCI
    plan section, up to the template's fixed capacity of 6.

We fill this exact template in place (rather than rebuilding the table from
scratch) so all of its original borders/merges/styling survive untouched —
only the blank text runs are replaced.
"""
from __future__ import annotations

import datetime
import io
from pathlib import Path
from typing import Any, Dict, List

import docx

from backend.schemas.rci_plan import RciSectionItem

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "rci_plan_template.docx"

# The template only has 6 fixed task-number slots (see module docstring) —
# any sections beyond this are dropped rather than silently expanding the
# template's row count (risks corrupting the vMerge structure). Surfaced to
# the caller via the returned `truncated` count so it isn't silent.
MAX_TEMPLATE_SECTIONS = 6


def _set_cell_text(cell, text: str) -> None:
    cell.text = text or ""


def _set_description_paragraph(doc, text: str) -> None:
    """Replaces the template's instructional placeholder paragraph — the
    cell at outer row 4 whose text starts with "A description of what has
    happened" — with the real problem statement/description text."""
    outer = doc.tables[0]
    cell = outer.rows[4].cells[1]
    if cell.paragraphs:
        # Reuse the first paragraph/run so its original formatting carries
        # over, clearing any others so old placeholder text doesn't linger.
        first = cell.paragraphs[0]
        if first.runs:
            first.runs[0].text = text
            for run in first.runs[1:]:
                run.text = ""
        else:
            first.add_run(text)
        for para in cell.paragraphs[1:]:
            for run in para.runs:
                run.text = ""
    else:
        cell.text = text


def build_rci_plan_docx(
    record_id: str,
    trackwise_fields: Dict[str, Any],
    sections: List[RciSectionItem],
) -> tuple[bytes, int]:
    """Returns (docx_bytes, truncated_section_count)."""
    doc = docx.Document(str(TEMPLATE_PATH))
    outer = doc.tables[0]

    # ── 1.0 Event Details ──────────────────────────────────────────────
    fields_table = outer.rows[2].cells[1].tables[0]
    value_row = fields_table.rows[1]
    rci_owner = trackwise_fields.get("Deviation Owner") or next(
        (s.assignee for s in sections if s.assignee), ""
    )
    _set_cell_text(value_row.cells[0], record_id)
    _set_cell_text(value_row.cells[1], "")  # RCI Number — assigned by Trackwise itself on real push, not generated here
    _set_cell_text(value_row.cells[2], rci_owner or "")
    _set_cell_text(value_row.cells[3], datetime.date.today().strftime("%d-%b-%Y"))

    _set_description_paragraph(doc, trackwise_fields.get("description") or trackwise_fields.get("title") or "")

    # ── 2.0 Investigation tasks ─────────────────────────────────────────
    tasks_table = outer.rows[6].cells[1].tables[0]
    truncated = max(0, len(sections) - MAX_TEMPLATE_SECTIONS)
    for i, section in enumerate(sections[:MAX_TEMPLATE_SECTIONS]):
        block_start = 1 + i * 3  # header row is row 0; each section owns rows [block_start, block_start+2]
        row = tasks_table.rows[block_start]
        objective = section.title if not section.correlation else f"{section.title}\n{section.correlation}"
        # Unchecked tasks are excluded from the exported report — same
        # "checked = keep it" convention Evidence Collection/Interview
        # Questionnaire already use.
        details = "\n".join(f"- {t.description}" for t in section.tasks if t.is_checked)
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], objective)
        _set_cell_text(row.cells[2], details)
        _set_cell_text(row.cells[3], section.assignee or "Unassigned")
        _set_cell_text(row.cells[4], section.due_date or "")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue(), truncated