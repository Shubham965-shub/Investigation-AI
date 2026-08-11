"""Extracts Task Critique's task list directly from OUR real RCI Plan Word
template's structure (the same template services/rci_plan_export.py fills) —
the reverse of that file's cell-write navigation.

Built here, in this backend, rather than calling ds's own POST /critique/extract
— that endpoint's parser (ds/src/agents/critique/api/services/xml_extraction.py)
is written for a differently-structured document (Event Description/
Prerequisites/Task Assignments/SignOff sections) and fails outright against
our real template (confirmed live, 2026-08-06, against both the raw template
and a genuine investigation_rci_plan_exports row) — it isn't a fit here.

Template structure (see rci_plan_export.py's module docstring for the full
rationale): outer table row 6 -> nested 19x5 table -> 6 fixed 3-row blocks,
one per RCI Plan section. Confirmed directly against the raw template AND a
real export (deviation_id 496712, export id 11): unused blocks still have
their static "1".."6" S.No. pre-printed by the template itself, but their
objective cell (index 1) is blank — that's the real "is this block used"
signal, not the S.No. cell.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

import docx


def _clean(text: Optional[str]) -> Optional[str]:
    """Empty string and the literal "Unassigned"/"" placeholders both mean
    "nothing set" — normalize both to None."""
    text = (text or "").strip()
    if not text or text == "Unassigned":
        return None
    return text


def extract_task_sections(docx_bytes: bytes) -> List[Dict[str, Any]]:
    """Returns one dict per filled task-block, in document order:
    {"title": str, "correlation": str | None, "tasks": list[str],
    "due_date": str | None, "assignee": str | None}. Unused template slots
    (fewer than 6 real sections) are skipped, not returned as empty entries.
    """
    doc = docx.Document(io.BytesIO(docx_bytes))
    outer = doc.tables[0]
    tasks_table = outer.rows[6].cells[1].tables[0]

    sections: List[Dict[str, Any]] = []
    for block in range(6):
        block_start = 1 + block * 3
        if block_start >= len(tasks_table.rows):
            break
        row = tasks_table.rows[block_start]
        objective = (row.cells[1].text or "").strip()
        if not objective:
            continue  # unused template slot — S.No. is pre-printed regardless

        # rci_plan_export.py writes this as
        # f"{section.title}\n{section.correlation}" when correlation exists,
        # or just section.title otherwise — split back apart the same way.
        title, _, correlation = objective.partition("\n")

        task_lines = [
            line.strip().lstrip("- ").strip()
            for line in (row.cells[2].text or "").split("\n")
            if line.strip()
        ]

        sections.append(
            {
                "title": title.strip(),
                "correlation": correlation.strip() or None,
                "tasks": task_lines,
                "due_date": _clean(row.cells[4].text),
                "assignee": _clean(row.cells[3].text),
            }
        )

    return sections