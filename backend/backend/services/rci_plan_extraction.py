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
rationale): outer table row 6 -> nested table -> header row + one row per
real RCI Plan section, contiguous (2026-08-19: rci_plan_export.py now
deletes every unused/leftover row outright — the block always used to be a
fixed 3 rows regardless of real section count, with unused slots left blank,
but that padding is gone, so this reader no longer needs to skip blank
slots or assume fixed 3-row spacing).
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

import docx


def _clean(text: Optional[str]) -> Optional[str]:
    """Empty string and the literal "Unassigned"/"N/A" placeholders all mean
    "nothing set" — normalize all three to None. "N/A" is rci_plan_export.py's
    fallback for an otherwise-blank objective/details/TCD cell (2026-08-19,
    per the user) — read back the same way, so a section with no due date
    doesn't come back as the literal string "N/A"."""
    text = (text or "").strip()
    if not text or text in ("Unassigned", "N/A"):
        return None
    return text


_SUBTASK_NUMBER_RE = re.compile(r"^\d+\.\d+\s*")


def extract_task_sections(docx_bytes: bytes) -> List[Dict[str, Any]]:
    """Returns one dict per task row, in document order:
    {"title": str, "correlation": str | None, "tasks": list[str],
    "due_date": str | None, "assignee": str | None}.
    """
    doc = docx.Document(io.BytesIO(docx_bytes))
    outer = doc.tables[0]
    tasks_table = outer.rows[6].cells[1].tables[0]

    sections: List[Dict[str, Any]] = []
    for row in tasks_table.rows[1:]:  # row 0 is the header
        objective = (row.cells[1].text or "").strip()
        if not objective:
            continue

        # rci_plan_export.py writes this as
        # f"{section.title}\n{section.correlation}" when correlation exists,
        # or just section.title otherwise — split back apart the same way.
        title, _, correlation = objective.partition("\n")

        # rci_plan_export.py numbers each subtask "<task>.<subtask> "
        # (e.g. "1.1 ") — strip that back off, same as the old "- " bullet
        # prefix this replaced. A cell with zero checked subtasks exports as
        # the literal "N/A" (2026-08-19, per the user) rather than being
        # blank — treat that the same as no lines at all, not a fake task.
        task_lines = [
            _SUBTASK_NUMBER_RE.sub("", line.strip())
            for line in (row.cells[2].text or "").split("\n")
            if line.strip() and line.strip() != "N/A"
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