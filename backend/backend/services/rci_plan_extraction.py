"""Extracts Task Critique's task list from our real RCI Plan Word template's structure — the reverse of rci_plan_export.py's cell-write navigation.
Built here rather than calling ds's POST /critique/extract, whose parser expects a differently-structured document and fails against our template.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

import docx


def _clean(text: Optional[str]) -> Optional[str]:
    """Empty string and the literal "Unassigned"/"N/A" placeholders all mean "nothing set" — normalize all to None."""
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

        # Mirrors rci_plan_export.py's f"{title}\n{correlation}" write — split back apart the same way.
        title, _, correlation = objective.partition("\n")

        # Mirrors rci_plan_export.py's "<task>.<subtask> " numbering — strip it back off. Zero checked subtasks exports as literal "N/A", not blank.
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