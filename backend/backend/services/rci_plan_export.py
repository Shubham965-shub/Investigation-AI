"""Fills the company's real RCI Plan Word template (assets/rci_plan_template.docx)
with a generated RCI plan's data, for the RCI Plan page's "Accept and Push to
TW" download.

Template replaced 2026-08-05 (the prior version, "New format.docx" from
2026-07-31, was IRM/rights-protected and unreadable by any tool without a
Microsoft RMS license). An earlier version of this file assumed the new
template was flat (no nested tables) because `cell.text` reads empty for a
cell whose only content is a nested table — `cell.text` ignores nested
tables entirely, it does not mean the cell has no content. Calling
`cell.text = ...` on such a cell replaces its ENTIRE content, nested table
included, with one plain paragraph — which is what "disassembled" the
tables in that version. Re-verified properly this time via `cell.tables`:

  - row 2 (outer) -> a nested 2x4 table: header row (Parent record number /
    RCI Number / RCI Owner / RCI Initiated on) + one blank value row —
    IDENTICAL structure to the old template's Event Details table.
  - row 3 (outer) -> no nested table, genuinely blank — left untouched,
    manual entry (per the user, 2026-08-05).
  - row 4 (outer) -> a single instructional paragraph ("A description of
    what has happened...") that stands in for the description field itself
    — same as the old template.
  - row 6 (outer) -> a nested 19x5 table: header row + 6 task-number blocks
    of 3 rows each (S.No. vertically merged per block) — IDENTICAL
    structure to the old template's Investigation tasks table, including
    the same fixed 6-slot capacity.
  - row 8 (outer) -> header labels already printed in the template:
    Investigator | Task Owner 1 | Task Owner 2 | Task Owner 3 | Task Owner 4
    (this row itself is not filled).
  - row 9 (outer) -> the value row under those headers — genuinely flat (no
    nested table), confirmed via the same cell.tables check. col 0 = the
    overall RCI owner/investigator, cols 1-4 = each section's own assignee,
    capped at the template's 4 Task Owner slots.

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
# any sections beyond this are dropped from the Investigation tasks table
# rather than silently expanding the template's row count (risks corrupting
# the vMerge structure). Surfaced to the caller via the returned `truncated`
# count so it isn't silent.
MAX_TEMPLATE_SECTIONS = 6

# The Sign-off row only has 4 Task Owner slots — sections beyond this still
# have their tasks in full in the Investigation tasks table (up to the
# 6-slot cap above), they just don't get a named owner in the Sign-off row.
MAX_SIGN_OFF_OWNERS = 4


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
) -> tuple[bytes, int, int]:
    """Returns (docx_bytes, truncated_section_count, truncated_owner_count)."""
    doc = docx.Document(str(TEMPLATE_PATH))
    outer = doc.tables[0]

    # ── 1.0 Event Details ──────────────────────────────────────────────
    fields_table = outer.rows[2].cells[1].tables[0]
    value_row = fields_table.rows[1]
    # dim_investigator.investigator (the real assigned investigator) is
    # preferred; "Deviation Owner" (dim_event.owner_name, a different column)
    # and a section's manually-typed assignee are both weaker fallbacks for
    # when investigator_key isn't set on this event (2026-08-07, per the user).
    rci_owner = (
        trackwise_fields.get("Investigator")
        or trackwise_fields.get("Deviation Owner")
        or next((s.assignee for s in sections if s.assignee), "")
    )
    _set_cell_text(value_row.cells[0], record_id)
    rci_number = trackwise_fields.get("RCI Number")
    # dim_rci.rci_key (the actual Trackwise RCI ID — see db/queries.py) is an
    # integer column, unlike every other Trackwise field here which is
    # already text — stringify explicitly, since python-docx's cell.text
    # setter requires a str (2026-08-14, per the user: confirmed rci_key,
    # not dim_rci.reference_number, is the real RCI number to fill in here).
    _set_cell_text(value_row.cells[1], str(rci_number) if rci_number is not None else "")
    _set_cell_text(value_row.cells[2], rci_owner or "")
    _set_cell_text(value_row.cells[3], datetime.date.today().strftime("%d-%b-%Y"))
    # Row 3 intentionally left blank — manual entry, not auto-filled.

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

    # ── 3.0 RCI Plan Sign-off ────────────────────────────────────────────
    # Genuinely flat (no nested table, confirmed via cell.tables) — headers
    # (Investigator | Task Owner 1-4) are already printed at outer row 8.
    sign_off_row = outer.rows[9]
    _set_cell_text(sign_off_row.cells[0], rci_owner or "")
    owners_truncated = max(0, len(sections) - MAX_SIGN_OFF_OWNERS)
    for i, section in enumerate(sections[:MAX_SIGN_OFF_OWNERS]):
        _set_cell_text(sign_off_row.cells[i + 1], section.assignee or "Unassigned")

    buffer = io.BytesIO()
    doc.save(buffer)
    # Two distinct truncation reasons, returned separately rather than
    # merged — `truncated` sections are actually dropped from the
    # Investigation tasks table entirely; `owners_truncated` sections still
    # have their full tasks in that table, they just have no named owner in
    # the Sign-off row. Collapsing these into one number would make the
    # router's warning describe the wrong thing when only one of the two
    # actually applies.
    return buffer.getvalue(), truncated, owners_truncated