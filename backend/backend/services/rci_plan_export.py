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
    of 3 rows each — IDENTICAL structure to the old template's Investigation
    tasks table, including the same fixed 6-slot capacity. Despite looking
    vertically merged in the raw template, each row's vMerge is independently
    `val="restart"` (verified via each cell's `w:tcPr/w:vMerge`, 2026-08-19) —
    there is no real w:vMerge continuation tying the 3 rows of a block
    together, so only the block's first row is ever filled and the other two
    are deleted outright (see build_rci_plan_docx) rather than left as blank
    placeholder rows.
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

import copy
import datetime
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _format_ddmmyyyy(iso: Optional[str]) -> str:
    """due_date is always a plain "yyyy-mm-dd" string (native <input
    type="date">'s value format, see RciPlanPage.tsx) — the exported docx
    shows it as dd/mm/yyyy (2026-08-18, per the user), matching the RCI Plan
    page's own read-only display."""
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
    # Unchecked sections are excluded from the final plan entirely (2026-08-20,
    # per the user) — same "checked = keep it" convention already used for
    # individual subtasks (RciTaskItem.is_checked) here, one level up.
    sections = [s for s in sections if s.is_checked]

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
    _set_cell_text(value_row.cells[3], datetime.date.today().strftime("%d/%m/%Y"))
    # Row 3 intentionally left blank — manual entry, not auto-filled.

    _set_description_paragraph(doc, trackwise_fields.get("description") or trackwise_fields.get("title") or "")

    # ── 2.0 Investigation tasks ─────────────────────────────────────────
    tasks_table = outer.rows[6].cells[1].tables[0]
    truncated = max(0, len(sections) - MAX_TEMPLATE_SECTIONS)
    # Each 3-row block only ever gets its first row filled — the other two
    # are deleted outright (2026-08-19, per the user: leftover blank rows,
    # each still showing the block's placeholder S.No. text with nothing
    # else, were showing up under every task). Deleted in descending row
    # index order at the end so earlier deletions don't shift the indices of
    # rows still queued for removal.
    rows_to_delete: List[int] = []
    for i in range(MAX_TEMPLATE_SECTIONS):
        block_start = 1 + i * 3  # header row is row 0; each section owns rows [block_start, block_start+2]
        if i < len(sections):
            section = sections[i]
            row = tasks_table.rows[block_start]
            objective = section.title if not section.correlation else f"{section.title}\n{section.correlation}"
            # Unchecked tasks are excluded from the exported report — same
            # "checked = keep it" convention Evidence Collection/Interview
            # Questionnaire already use. Numbered "<task>.<subtask>" so
            # subtasks are identifiable individually within the one cell
            # (2026-08-19, per the user), since the block's other rows are
            # removed rather than used to hold one subtask each.
            checked = [t for t in section.tasks if t.is_checked]
            details = "\n".join(f"{i + 1}.{j + 1} {t.description}" for j, t in enumerate(checked))
            _set_cell_text(row.cells[0], str(i + 1))
            # "Unassigned" (assignee) is already a deliberate, more specific
            # label than a blank cell — left as-is. Objective/details/TCD
            # have no such existing fallback, so a genuinely blank one shows
            # "N/A" instead (2026-08-19, per the user).
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
    # Genuinely flat (no nested table, confirmed via cell.tables) — headers
    # at outer row 8 are ['', 'Investigator', 'Task Owner 1', 'Task Owner 2',
    # 'Task Owner 3', 'Task Owner 4'] (6 cells, confirmed 2026-08-19) — cell 0
    # is a blank label column, NOT the Investigator slot. The previous
    # off-by-one (writing rci_owner into cell 0 and assignees into cells
    # 1-4) squashed the investigator's name into that blank cell, put the
    # first task owner's name in the actual Investigator column, and left
    # the last Task Owner slot (cell 5) always empty — per the user's
    # report, 2026-08-19.
    sign_off_row = outer.rows[9]
    header_row = outer.rows[8]
    # Multiple sections are routinely assigned to the same person — filling
    # slots section-by-section (previous approach) could burn a slot on a
    # repeat name while a genuinely distinct owner further down the list got
    # no slot at all (2026-08-19, per the user: a 6-task investigation with
    # only 3 distinct owners was showing a duplicate name in one Task Owner
    # slot and omitting a real owner entirely). Dedup by name, preserving
    # first-appearance order.
    unique_owners: List[str] = []
    for section in sections:
        name = section.assignee or "Unassigned"
        if name not in unique_owners:
            unique_owners.append(name)

    _set_cell_text(sign_off_row.cells[1], rci_owner or "N/A")
    # Every one of the 4 fixed Task Owner slots gets written, not just the
    # ones with a real name — otherwise a slot beyond len(unique_owners)
    # (e.g. only 2 distinct owners across all sections) is never touched at
    # all and stays truly blank, unlike every other cell here (per the user,
    # blank cells in this table should read "N/A").
    filled_owners = unique_owners[:MAX_SIGN_OFF_OWNERS]
    for i in range(MAX_SIGN_OFF_OWNERS):
        _set_cell_text(sign_off_row.cells[i + 2], filled_owners[i] if i < len(filled_owners) else "N/A")

    # The template's Sign-off row only has 4 fixed Task Owner slots, but an
    # investigation can have more distinct owners than that (2026-08-19, per
    # the user: 6 distinct owners still only showed the first 4). Rather
    # than add a separate table, extend this SAME table with more rows —
    # cloned from the header/value row pair (captured before either was
    # filled in, so the clones start pristine) — each holding up to 5 more
    # "Task Owner N" slots across its 5 non-label cells (cell 0 stays the
    # blank label column, matching row 8/9's own layout).
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
                    # Header stays blank — an unused column has no "Task
                    # Owner N" to label. The value cell still gets N/A, same
                    # as every other blank cell in this table.
                    _set_cell_text(new_header_row.cells[i + 1], "")
                    _set_cell_text(new_value_row.cells[i + 1], "N/A")
            next_owner_number += len(batch)

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