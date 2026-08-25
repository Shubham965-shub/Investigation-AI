"""Validates an uploaded task report against the real Task Report Template
(/Users/114862/Desktop/Task Report Template.docx, 2026-08-12, per the user) —
before a report is sent to ds for critique, not after. The template's actual
structure (confirmed via python-docx): a "Problem statement:" label, an
"Investigation tasks" heading, and per-task blocks each labelled "Title of
the task:", "Objective:", "Findings:", "Inference". The company logo/location
live in the header, not the body, so ignoring them is automatic — this only
ever scans body paragraphs/tables, never the header.

"Title of the task:" is deliberately NOT in REQUIRED_MARKERS — confirmed
against a real, already-successfully-critiqued report (Desktop/"Deviation
Task report - 1 task.docx") that it's a blank-template-only instructional
label; once filled in, the task's title becomes a plain heading line with no
literal "Title of the task" prefix at all. Requiring it would reject
genuinely well-formed, real reports.

This is a structural check (are the expected section labels present at all),
not a content/quality check — that's what ds's critique does. A report
missing these labels almost certainly isn't the right template at all, and
ds's critique would have nothing real to parse from it anyway.
"""
from __future__ import annotations

import io
from typing import List

import docx
from docx.oxml.ns import qn

REQUIRED_MARKERS = [
    "problem statement",
    "investigation tasks",
    "objective",
    "findings",
    "inference",
]


def missing_task_report_markers(file_bytes: bytes) -> List[str]:
    """Returns the subset of REQUIRED_MARKERS not found anywhere in the
    document body (case-insensitive) — empty list means the format checks out.

    Walks every <w:t> text node under the body via the raw XML tree rather
    than doc.paragraphs/doc.tables (2026-08-25, found live: a genuinely
    correct .docx was intermittently rejected as "wrong format"). Those two
    python-docx properties only see paragraphs/tables that are DIRECT
    children of the body — text inside a nested table-within-a-table, or
    inside a content control (a <w:sdt> block, which Word can wrap a
    section in depending on how the template was filled/edited), sits one
    or more levels deeper in the XML and is invisible to them even though
    the text is genuinely there and Word renders it normally. Iterating
    every <w:t> under the body finds it regardless of nesting depth."""
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
    except Exception:
        return list(REQUIRED_MARKERS)

    body_text = "".join(node.text or "" for node in doc.element.body.iter(qn("w:t")))
    body_text_lower = body_text.lower()

    return [marker for marker in REQUIRED_MARKERS if marker not in body_text_lower]


def is_valid_task_report_format(file_bytes: bytes) -> bool:
    return not missing_task_report_markers(file_bytes)