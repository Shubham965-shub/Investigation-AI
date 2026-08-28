"""
Regression tests for the RC & CAPA Critique feature's deterministic docx parser
(src/agents/critique/api/services/rci_report_extraction.py). GAPS.md's
2026-08-25 entries document three real bugs found live against a genuine
completed RCI report (heading conflation between Correction/Remedial and CAPA,
CAPA-table over-capture pulling in Interim Control/Extrapolation rows, and a
repeat-occurrence text heuristic that misread an unchecked "Yes No" template
placeholder as a confirmed True) plus a fourth (checkbox symbol and its Yes/No
label living in adjacent runs, not the same run) — none of these had a
dedicated test before this file.
"""

import tempfile
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from lxml import etree

from src.agents.critique.api.services.rci_report_extraction import (
    _detect_repeat_occurrence,
    _is_capa_action_table,
    _is_capa_heading,
    _is_correction_remedial_heading,
    _is_exec_summary_heading,
    _is_impact_assessment_heading,
    _is_problem_statement_heading,
    _is_rc_heading,
    _repeat_occurrence_from_text,
    _table_to_capa_items,
    _table_to_text,
    extract_rci_report_sections,
)


# ---------------------------------------------------------------------------
# _repeat_occurrence_from_text
# ---------------------------------------------------------------------------


def test_repeat_occurrence_unchecked_yes_no_placeholder_is_unknown():
    """The bug this fixes: a literal, real-report text — 'Determine if the root
    cause is a repeat occurrence Yes No. If yes, Mention the details as: Not
    Applicable' — was misread as a confirmed True by the old '"yes" in text and
    "no" not in text.split("yes")[-1]' heuristic, which split on the wrong of
    the two 'yes' occurrences."""
    text = (
        "determine if the root cause is a repeat occurrence yes no. "
        "if yes, mention the details as: not applicable"
    )
    assert _repeat_occurrence_from_text(text) is None


def test_repeat_occurrence_explicit_negative_phrasing_is_false():
    assert _repeat_occurrence_from_text("no recurring event was identified") is False
    assert _repeat_occurrence_from_text("this is not a repeat occurrence") is False


def test_repeat_occurrence_confirmed_yes_with_no_trailing_no_is_true():
    assert _repeat_occurrence_from_text("this is a repeat occurrence: yes, same root cause as event 12345") is True


def test_repeat_occurrence_no_yes_no_keywords_at_all_is_unknown():
    assert _repeat_occurrence_from_text("root cause traced to a torque wrench calibration lapse") is None


# ---------------------------------------------------------------------------
# _detect_repeat_occurrence — checkbox symbol + adjacent text run pairing
# ---------------------------------------------------------------------------


def _table_with_checkbox_row(font: str, char: str, label: str):
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Repeat occurrence"
    cell = table.cell(0, 1)
    p = cell.paragraphs[0]
    p.text = ""
    sym_run = p.add_run()
    sym = etree.SubElement(sym_run._r, qn("w:sym"))
    sym.set(qn("w:font"), font)
    sym.set(qn("w:char"), char)
    p.add_run(label)  # label lives in a SEPARATE run from the symbol
    return table._tbl


def test_detect_repeat_occurrence_checked_no_symbol_adjacent_run():
    """The bug this fixes: symbol and label previously had to be in the SAME
    run to match — a real Word checkbox never does that (symbol-only run,
    immediately followed by a separate text run). Confirmed live (2026-08-25)
    against record 505542: checked Wingdings 'No' (char F0FE)."""
    tbl = _table_with_checkbox_row("Wingdings", "F0FE", "No")
    assert _detect_repeat_occurrence(tbl) is False


def test_detect_repeat_occurrence_checked_yes_symbol_adjacent_run():
    tbl = _table_with_checkbox_row("Wingdings", "F0FE", "Yes")
    assert _detect_repeat_occurrence(tbl) is True


def test_detect_repeat_occurrence_unchecked_symbol_falls_back_to_text_heuristic():
    """An unrecognized (unchecked) symbol/char pair must not be treated as a
    checked box — falls through to the plain-text fallback."""
    tbl = _table_with_checkbox_row("Wingdings", "F0A2", "No")
    assert _detect_repeat_occurrence(tbl) is None


def test_detect_repeat_occurrence_no_repeat_row_returns_none():
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Root cause conclusion"
    table.cell(0, 1).text = "Deficient calibration procedure."
    assert _detect_repeat_occurrence(table._tbl) is None


# ---------------------------------------------------------------------------
# Heading matchers
# ---------------------------------------------------------------------------


def test_is_capa_heading_no_longer_conflated_with_correction_remedial():
    """The bug this fixes: _is_capa_heading's old clause matched 'Correction
    and or Remedial action' too (both contain 'correction' + were tested for
    overlap with 'remedial'/'capa'), flipping into CAPA state 4 paragraphs
    before the real CAPA heading."""
    assert _is_capa_heading("Correction and or Remedial action") is False
    assert _is_capa_heading("Corrective Action & Preventive Action") is True
    assert _is_capa_heading("11. Remedial Action / CAPA Proposal") is True


def test_is_correction_remedial_heading_excludes_capa_and_corrective():
    assert _is_correction_remedial_heading("Corrective Action & Preventive Action") is False
    assert _is_correction_remedial_heading("Correction and or Remedial action") is True
    assert _is_correction_remedial_heading("REMEDIAL ACTION: Not Applicable.") is True


def test_is_impact_assessment_heading_matches_short_real_report_phrasing():
    """See GAPS.md 2026-08-25 #2: real reports use shorter headings than the
    blank template ('8 Impact Assessment:' with no 'conclusion'/'batch
    disposition' suffix) — must still match, but never match Section 2's
    earlier 'Initial Impact Assessment & Immediate Actions' heading."""
    assert _is_impact_assessment_heading("8 Impact Assessment:") is True
    assert _is_impact_assessment_heading("Impact Assessment & Conclusion (Batch disposition)") is True
    assert _is_impact_assessment_heading("Initial Impact Assessment & Immediate Actions") is False


def test_is_rc_heading_excludes_investigation_findings_headings():
    assert _is_rc_heading("Root Cause Conclusion / Probable Cause Statement") is True
    assert _is_rc_heading("Investigation findings leading to determination of root cause") is False


def test_is_problem_statement_heading_matches_synonyms():
    assert _is_problem_statement_heading("1. Problem Statement") is True
    assert _is_problem_statement_heading("Event Description") is True
    assert _is_problem_statement_heading("Executive Summary") is False


def test_is_exec_summary_heading_matches_only_exec_summary():
    assert _is_exec_summary_heading("Executive Summary") is True
    assert _is_exec_summary_heading("Problem Statement") is False


# ---------------------------------------------------------------------------
# _is_capa_action_table / _table_to_capa_items — table over-capture fix
# ---------------------------------------------------------------------------


def _build_table(doc, header_row, data_rows):
    table = doc.add_table(rows=1 + len(data_rows), cols=len(header_row))
    for c, val in enumerate(header_row):
        table.cell(0, c).text = val
    for r, row in enumerate(data_rows, start=1):
        for c, val in enumerate(row):
            table.cell(r, c).text = val
    return table


def test_is_capa_action_table_accepts_real_capa_headers():
    doc = Document()
    assert _is_capa_action_table(_build_table(doc, ["Sr.No.", "CAPA Description", "Responsibility", "Due Date"], [])._tbl) is True
    assert _is_capa_action_table(_build_table(doc, ["Sr.No.", "Corrective Action", "Preventive Action"], [])._tbl) is True


def test_is_capa_action_table_rejects_interim_control_and_extrapolation_tables():
    """See GAPS.md 2026-08-25 #2: before this classifier existed, every table
    seen while in the CAPA section was parsed as CAPA action rows regardless
    of its own header — pulling in the Interim Control Plan's and CAPA
    Extrapolation's "Not Applicable" rows as fake CAPA items."""
    doc = Document()
    interim = _build_table(doc, ["Sr.No.", "Interim Control", "Responsibility", "Due Date"], [["1", "Not Applicable", "QA", "NA"]])
    extrapolation = _build_table(doc, ["Applicable", "Scope", "Responsibility", "Due Date"], [["No", "Not Applicable", "QA", "NA"]])
    assert _is_capa_action_table(interim._tbl) is False
    assert _is_capa_action_table(extrapolation._tbl) is False


def test_table_to_capa_items_skips_header_and_blank_description_rows():
    doc = Document()
    table = _build_table(
        doc,
        ["Sr.No.", "CAPA Description", "Responsibility", "Due Date"],
        [
            ["1", "Revise SOP F1/PR/003.", "QA", "30/09/2026"],
            ["2", "", "QA", "NA"],  # blank description — must be skipped
        ],
    )
    items = _table_to_capa_items(table._tbl)
    assert len(items) == 1
    assert items[0] == {"description": "Revise SOP F1/PR/003.", "responsibility": "QA", "due_date": "30/09/2026"}


def test_table_to_text_flattens_rows_and_skips_blank_rows():
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Sr.No."
    table.cell(0, 1).text = "Detail"
    table.cell(1, 0).text = ""
    table.cell(1, 1).text = ""
    assert _table_to_text(table._tbl) == "Sr.No. | Detail"


# ---------------------------------------------------------------------------
# extract_rci_report_sections — end-to-end state-machine wiring
# ---------------------------------------------------------------------------


def _save_docx(doc: Document) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".docx")[1])
    doc.save(tmp)
    return tmp


def _add_heading(doc, text, level=1):
    p = doc.add_paragraph(text)
    p.style = doc.styles[f"Heading {level}"]
    return p


def test_extract_sections_correction_remedial_not_conflated_with_capa(tmp_path):
    """End-to-end reproduction of the exact heading-conflation bug: a
    'Correction and or Remedial action' heading immediately followed by the
    real CAPA heading and its action table must land in the right buckets,
    not have CAPA content bleed into correction_remedial or vice versa."""
    doc = Document()
    _add_heading(doc, "Executive Summary")
    doc.add_paragraph("Problem statement: Foreign object found in tablet during packing.")
    _add_heading(doc, "Correction and or Remedial action")
    doc.add_paragraph("Batch was placed on hold and line clearance re-verified.")
    _add_heading(doc, "Corrective Action & Preventive Action")
    _build_table(doc, ["Sr.No.", "CAPA Description", "Responsibility", "Due Date"], [["1", "Revise SOP F1/PR/003.", "QA", "30/09/2026"]])
    _add_heading(doc, "List of Annexures")
    doc.add_paragraph("Annexure 1 - Investigation plan")

    path = _save_docx(doc)
    try:
        result = extract_rci_report_sections(path)
    finally:
        path.unlink()

    assert "line clearance" in result["correction_remedial_text"].lower()
    assert "revise sop" not in result["correction_remedial_text"].lower()
    assert len(result["capa_items"]) == 1
    assert result["capa_items"][0]["description"] == "Revise SOP F1/PR/003."


def test_extract_sections_capa_table_excludes_interim_control_rows():
    """End-to-end reproduction of the table-over-capture bug: an Interim
    Control table appearing inside the CAPA section must not contribute fake
    capa_items — it should fold into capa_overall_text instead."""
    doc = Document()
    _add_heading(doc, "Corrective Action & Preventive Action")
    _build_table(doc, ["Sr.No.", "CAPA Description", "Responsibility", "Due Date"], [["1", "Replace with scratch-proof containers.", "QA", "Completed"]])
    _add_heading(doc, "Interim Control Plan", level=2)
    _build_table(doc, ["Sr.No.", "Interim Control", "Responsibility", "Due Date"], [["1", "Not Applicable", "QA", "NA"]])

    path = _save_docx(doc)
    try:
        result = extract_rci_report_sections(path)
    finally:
        path.unlink()

    assert len(result["capa_items"]) == 1
    assert result["capa_items"][0]["description"] == "Replace with scratch-proof containers."
    assert "not applicable" in result["capa_overall_text"].lower()


def test_extract_sections_inline_remedial_action_heading_content_captured():
    """See GAPS.md 2026-08-25 #2: a real report's whole answer sometimes sits
    directly in the heading line ('REMEDIAL ACTION: Not Applicable.') with no
    body paragraph following — this is otherwise silently lost since H1
    heading text is never collected as content."""
    doc = Document()
    _add_heading(doc, "REMEDIAL ACTION: Not Applicable.")
    _add_heading(doc, "Corrective Action & Preventive Action")
    doc.add_paragraph("No CAPA action is warranted for this event.")

    path = _save_docx(doc)
    try:
        result = extract_rci_report_sections(path)
    finally:
        path.unlink()

    assert result["correction_remedial_text"].strip() == "Not Applicable."
