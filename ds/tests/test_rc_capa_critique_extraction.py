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

import io
import json
import tempfile
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from fastapi.testclient import TestClient
from lxml import etree

from src.agents.app import create_app
from src.agents.critique.api.schemas import CAPACritiqueResponse, RCConclusionCritiqueResponse
from src.agents.critique.api.services.relevance_validation import DocumentRelevanceResult
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


def test_extract_sections_impact_conclusion_captured_additively():
    """2026-09-01: the 'Conclusion Statement:' line onward within Impact
    Assessment is captured into its own field, additively — it must still
    also appear in impact_assessment_text (not removed from the broader
    blob), same principle as reference_number alongside status in the
    correction/remedial prompt."""
    doc = Document()
    _add_heading(doc, "Impact Assessment & Conclusion (Batch disposition)")
    doc.add_paragraph("Impact on affected batches: Batch#7263940 was verified with no defects.")
    doc.add_paragraph("Conclusion Statement: Batch#7263940 is released. No further action required.")
    _add_heading(doc, "Correction and or Remedial action")
    doc.add_paragraph("Not Applicable.")

    path = _save_docx(doc)
    try:
        result = extract_rci_report_sections(path)
    finally:
        path.unlink()

    assert result["impact_conclusion_text"].strip() == (
        "Batch#7263940 is released. No further action required."
    )
    assert "batch#7263940 was verified" in result["impact_assessment_text"].lower()
    assert "released" in result["impact_assessment_text"].lower()


def test_extract_sections_impact_conclusion_absent_when_no_label_present():
    doc = Document()
    _add_heading(doc, "Impact Assessment & Conclusion (Batch disposition)")
    doc.add_paragraph("No patient safety impact identified.")
    _add_heading(doc, "Correction and or Remedial action")
    doc.add_paragraph("Not Applicable.")

    path = _save_docx(doc)
    try:
        result = extract_rci_report_sections(path)
    finally:
        path.unlink()

    assert result["impact_conclusion_text"] == ""


# ---------------------------------------------------------------------------
# Endpoint-level tests — POST /critique/critique-rc-conclusion and
# POST /critique/critique-capa. extract_full_document_text/
# extract_rci_report_sections are imported directly into critique_route.py's
# own namespace (already covered by the unit tests above against the real
# functions), so they're monkeypatched here at the route-module level —
# same pattern test_capa_depth_effectiveness.py uses for its own save/extract
# helpers — to isolate this from real docx parsing and focus on the route's
# own orchestration (relevance gate, previous_recommendations grounding, the
# recurrence-without-citation guardrail, capa_status=="missing" handling).
# ---------------------------------------------------------------------------


ROUTE_MODULE = "src.agents.critique.api.routes.critique_route"
client = TestClient(create_app())

_FAKE_SECTIONS = {
    "problem_statement": "Foreign object found embedded in a tablet during packing.",
    "rc_conclusion_text": "Root cause: a deficient line-clearance checkpoint allowed a foreign object to enter the packing line.",
    "is_repeat_occurrence": False,
    "investigation_summary": "No similar prior events were found.",
    "impact_assessment_text": "No patient safety impact identified.",
    "impact_conclusion_text": "Batch released — no patient safety impact identified.",
    "correction_remedial_text": "The affected batch was placed on hold and line clearance was re-verified.",
    "capa_overall_text": "Revise line-clearance SOP F1/PR/003.",
    "capa_items": [{"description": "Revise SOP F1/PR/003 and retrain operators.", "responsibility": "QA", "due_date": "30/09/2026"}],
}


def _docx_bytes():
    doc = Document()
    doc.add_paragraph("Investigation report body text.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def _patch_extraction(monkeypatch, sections=None):
    monkeypatch.setattr(f"{ROUTE_MODULE}.extract_full_document_text", lambda temp_path: "Full report text body.")
    monkeypatch.setattr(f"{ROUTE_MODULE}.extract_rci_report_sections", lambda temp_path: dict(sections or _FAKE_SECTIONS))


def _patch_llm(monkeypatch, *, is_relevant=True, structured_response=None, chat_return="Condensed summary."):
    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        if structure is DocumentRelevanceResult:
            return DocumentRelevanceResult(is_relevant=is_relevant, reason="Matches the problem statement." if is_relevant else "Unrelated document.")
        return structured_response

    async def fake_chat(self, prompt, system=None):
        return chat_return

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr("src.llm.client.LLMClient.chat", fake_chat)


def test_critique_rc_conclusion_returns_grounded_result(monkeypatch):
    _patch_extraction(monkeypatch)
    _patch_llm(
        monkeypatch,
        structured_response=RCConclusionCritiqueResponse(
            rc_conclusion_text="placeholder",
            rc_recommendations=["Cite the specific line-clearance checkpoint that failed."],
            impact_recommendations=["Confirm no other batches share the same root cause."],
        ),
    )

    response = client.post(
        "/critique/critique-rc-conclusion",
        params={"event_type": "Deviation", "problem_statement": "Foreign object found in tablet."},
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["rc_conclusion_text_raw"] == _FAKE_SECTIONS["rc_conclusion_text"]
    assert data["is_repeat_occurrence"] is False
    assert data["impact_assessment_text"] == _FAKE_SECTIONS["impact_assessment_text"]
    assert data["impact_conclusion_text"] == _FAKE_SECTIONS["impact_conclusion_text"]
    assert data["rc_recommendations"] == ["Cite the specific line-clearance checkpoint that failed."]


def test_critique_rc_conclusion_suppresses_uncited_recurrence_claims(monkeypatch):
    """The _suppress_recurrence_claims_without_citation guardrail (route.py:110)
    firing for real: a recommendation asserting a "previous event" was ignored,
    with no concrete deviation/event reference, must be dropped — even though
    the LLM itself returned it."""
    _patch_extraction(monkeypatch)
    _patch_llm(
        monkeypatch,
        structured_response=RCConclusionCritiqueResponse(
            rc_conclusion_text="placeholder",
            rc_recommendations=[
                "A previous deviation with the same root cause was not addressed by this investigation.",
                "Cite the specific line-clearance checkpoint that failed.",
            ],
            impact_recommendations=[],
        ),
    )

    response = client.post(
        "/critique/critique-rc-conclusion",
        params={"event_type": "Deviation", "problem_statement": "Foreign object found in tablet."},
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    recommendations = response.json()["rc_recommendations"]
    # The uncited recurrence claim must be dropped entirely, not just
    # "not present verbatim under different wording" — assert the surviving
    # list is exactly the one recommendation the guardrail has no reason to
    # touch (confirmed against the real regexes: "previous deviation" with no
    # ODF/DR-style reference matches _RECURRENCE_CLAIM_RE and fails
    # _DEVIATION_REF_RE, so it is dropped).
    assert recommendations == ["Cite the specific line-clearance checkpoint that failed."]


def test_critique_rc_conclusion_with_citation_survives_the_recurrence_guardrail(monkeypatch):
    """The guardrail only drops UNCITED recurrence claims — one naming a real
    deviation/event reference (e.g. a DR number) must survive. The wording
    must actually match _RECURRENCE_CLAIM_RE's "previous <noun>" adjacency
    (confirmed directly against the regex) — inserting a word between
    "previous" and "deviation" (e.g. "previous similar deviation") breaks
    that match entirely, which would make this test pass for the wrong
    reason (the claim was never flagged as recurrence-like in the first
    place, so the citation-exemption path is never exercised)."""
    _patch_extraction(monkeypatch)
    _patch_llm(
        monkeypatch,
        structured_response=RCConclusionCritiqueResponse(
            rc_conclusion_text="placeholder",
            rc_recommendations=["A previous deviation (ODF/DR/2025/1123) was not addressed by this investigation."],
            impact_recommendations=[],
        ),
    )

    response = client.post(
        "/critique/critique-rc-conclusion",
        params={"event_type": "Deviation", "problem_statement": "Foreign object found in tablet."},
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    assert response.json()["rc_recommendations"] == [
        "A previous deviation (ODF/DR/2025/1123) was not addressed by this investigation."
    ]


def test_critique_rc_conclusion_grounds_prompt_with_previous_recommendations(monkeypatch):
    """previous_recommendations (a JSON-encoded list) must reach the system
    prompt via _with_previous_recommendations — verified by inspecting the
    actual system_prompt the mocked LLM call received."""
    _patch_extraction(monkeypatch)
    captured = {}

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        if structure is DocumentRelevanceResult:
            return DocumentRelevanceResult(is_relevant=True, reason="Matches.")
        captured["system_prompt"] = system_prompt
        return RCConclusionCritiqueResponse(rc_conclusion_text="x", rc_recommendations=[], impact_recommendations=[])

    async def fake_chat(self, prompt, system=None):
        return "Condensed."

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr("src.llm.client.LLMClient.chat", fake_chat)

    previous = ["Attach the batch record for the affected lot."]
    response = client.post(
        "/critique/critique-rc-conclusion",
        params={
            "event_type": "Deviation",
            "problem_statement": "Foreign object found in tablet.",
            "previous_recommendations": json.dumps(previous),
        },
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    assert "Attach the batch record for the affected lot." in captured["system_prompt"]


def test_critique_rc_conclusion_rejects_irrelevant_document(monkeypatch):
    _patch_extraction(monkeypatch)
    _patch_llm(monkeypatch, is_relevant=False)

    response = client.post(
        "/critique/critique-rc-conclusion",
        params={"event_type": "Deviation", "problem_statement": "Foreign object found in tablet."},
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 422


def test_critique_rc_conclusion_rejects_non_docx_file():
    response = client.post(
        "/critique/critique-rc-conclusion",
        params={"event_type": "Deviation", "problem_statement": "Test"},
        files={"file": ("report.txt", b"not a docx", "text/plain")},
    )
    assert response.status_code == 415


def test_critique_capa_returns_grounded_result(monkeypatch):
    _patch_extraction(monkeypatch)
    _patch_llm(
        monkeypatch,
        structured_response=CAPACritiqueResponse(
            capa_status="evaluated",
            recommendations=["State a concrete effectiveness-check monitoring window."],
        ),
    )

    response = client.post(
        "/critique/critique-capa",
        params={"event_type": "Deviation", "problem_statement": "Foreign object found in tablet."},
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["capa_text_raw"] == _FAKE_SECTIONS["capa_overall_text"]
    assert data["capa_items"][0]["description"] == "Revise SOP F1/PR/003 and retrain operators."
    assert data["correction_remedial_text"] == _FAKE_SECTIONS["correction_remedial_text"]
    assert data["recommendations"] == ["State a concrete effectiveness-check monitoring window."]


def test_critique_capa_missing_returns_422_and_clears_recommendations(monkeypatch):
    """capa_status == "missing" is a hard 422 (route.py:422-429) — the code-side
    backstop that empties recommendations for missing/not_required CAPA
    (_cap_recommendations) is never even reached in this case since the route
    raises before calling it, confirmed by asserting the 422 itself fires."""
    _patch_extraction(monkeypatch)
    _patch_llm(
        monkeypatch,
        structured_response=CAPACritiqueResponse(
            capa_status="missing",
            recommendations=["This recommendation must never reach the response."],
        ),
    )

    response = client.post(
        "/critique/critique-capa",
        params={"event_type": "Deviation", "problem_statement": "Foreign object found in tablet."},
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 422
    assert "No CAPA" in response.json()["detail"]


def test_critique_capa_not_required_clears_recommendations(monkeypatch):
    """_cap_recommendations (route.py:122-134) forces recommendations empty
    for capa_status == "not_required" even if the LLM returned some anyway."""
    _patch_extraction(monkeypatch)
    _patch_llm(
        monkeypatch,
        structured_response=CAPACritiqueResponse(
            capa_status="not_required",
            recommendations=["This should be cleared by the code-side backstop."],
        ),
    )

    response = client.post(
        "/critique/critique-capa",
        params={"event_type": "Deviation", "problem_statement": "Foreign object found in tablet."},
        files={"file": ("report.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    assert response.json()["recommendations"] == []


def test_critique_capa_rejects_non_docx_file():
    response = client.post(
        "/critique/critique-capa",
        params={"event_type": "Deviation", "problem_statement": "Test"},
        files={"file": ("report.txt", b"not a docx", "text/plain")},
    )
    assert response.status_code == 415
