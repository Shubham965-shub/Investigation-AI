"""Fills the company's real RCI Report Word template (assets/rci_report_template.docx)
with a generated RCI report's data, for the RCI Report page's "Accept and Push to
TW" download.

Structure (confirmed via python-docx, 2026-08-25) — this template is almost
entirely guidance paragraphs with a handful of blank lines to type an answer
into, unlike RCI Plan's template which is built from fillable table cells
throughout:

  - Page header (doc.sections[0].header, appears on every page — a single
    un-linked section, confirmed): a 4x4 table — row 0 is the repeated
    title banner; rows 1-3 are label/value pairs (Product/Material Name,
    Product/material Code, Parent record number, RCI record number,
    Batch(es)/AR No. involved, Date of initiation). Parent record number is
    the deviation id (`record_id`), RCI record number is the genuine
    TrackWise RCI id (`trackwise_fields["RCI Number"]` — dim_rci.rci_key,
    confirmed distinct from the deviation id elsewhere in this app).
  - Table 0 (13x4): the INDEX/table-of-contents — left untouched (page
    numbers aren't tracked anywhere in this app).
  - Executive Summary (body paragraphs, no table): 6 named sub-headings
    (Problem Description / Immediate containment action / Determination of
    root cause / Root Cause-Probable Cause statement / Impact Assessment /
    Correction-CAPA), each followed by one or more blank paragraphs to fill.
    ExecutiveSummarySection has 8 fields (adds `summary` and
    `conclusion_statement`, neither of which has its own heading) — `summary`
    goes in the first blank before "Problem Description", and
    `conclusion_statement` shares the last sub-heading's blank block (there
    are 6 blank paragraphs there, more than enough for both fields).
  - Table 1 (7x2): Description of Event, one row per field — clean 1:1 map.
  - Table 2 / Table 3: Initial Impact Assessment's material/product and
    equipment impact lists.
  - Table 4: History Review's prior-events rows.
  - Table 5 (3x1): Root Cause conclusion — row 1 is the narrative, row 2 is
    "Category: / Subcategory:".
  - Correction/Remedial Action: `items`/`additional_notes` go in the blank
    paragraphs right after the heading (no table here — the template
    originally had a 2x1 table with grey-italic definitions of the two
    terms; removed entirely per the user, 2026-08-28, since it wasn't
    fillable and left dead space above the actual content).
  - Table 6/7/8: CAPA actions / interim controls / extrapolation.
  - Table 9: CAPA effectiveness check plan.
  - Table 10 (8x2): Annexures — always present (pass-through, never None).
  - Table 11 (6x5): Approval — fixed role rows (Prepared by/Investigator,
    Reviewed by/HOD, /QA, /SIT, Approved by/Head-QA); always present
    (pass-through, never None) — filled by matching `role` to these labels.

No slot exists anywhere in this template for RiskAssessmentSection (it's
absent from the INDEX table too — this template predates/doesn't cover the
Market-Complaint-only risk scoring workflow). Rather than inventing new
document structure the company hasn't approved, its content is appended
into the same blank paragraph as Impact Assessment's optional
MC/OOS-specific fields, clearly labeled, so it's still visible rather than
silently dropped.

Every section field on RciReportSections is Optional — ds skips a section
(leaving it None) when a required TrackWise field was blank or a dependency
section itself failed (2026-08-24 finding, `errors` dict explains why). Per
the user (2026-08-25): a null section must show up AS SUCH in the document,
not leave the reader guessing whether it was overlooked. One clear note is
written at that section's first slot (`errors[section_key]` if present,
else a generic line) — the rest of that section's slots are left at the
template's own default (blank/guidance), rather than repeating the note
everywhere, since one clear flag per section is enough.

We fill this exact template in place (matching rci_plan_export.py's own
convention) so all of its original borders/merges/styling survive untouched.
Unlike that template, this one's own runs already have no explicit font set
(theme default throughout, confirmed via every existing run's `font.name`
being None) — so a freshly created run reusing an existing run's formatting
never introduces a font mismatch here, and no Times-New-Roman forcing is
needed the way RCI Plan's export required.
"""
from __future__ import annotations

import copy
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from backend.schemas.rci_report import RciReportSections

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "rci_report_template.docx"

MISSING_NOTE_FALLBACK = "This section could not be generated — the related TrackWise field(s) aren't filled."

# The template's own headings/guidance/table text almost all explicitly set
# 11pt (confirmed run-by-run, 2026-08-25) even though the document's Normal
# style itself defaults to 12pt Times New Roman — a run we create fresh
# (cell.text=, add_run(), add_paragraph()) sets neither, so it would
# silently inherit that 12pt style default and read as a different size
# from every answer sitting right next to it, despite both resolving to the
# same font family. Forced explicitly on every run this file touches so
# every generated font/size/heading/in-table text matches the template's
# own convention exactly (2026-08-25, per the user). Table content is
# additionally locked to 10pt, one step down from body content's 11pt
# (2026-08-25, per the user), matching how a real Word table's contents
# commonly run a point smaller than the surrounding body text.
FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(11)
TABLE_FONT_SIZE = Pt(10)


def _apply_font(run, size=None) -> None:
    run.font.name = FONT_NAME
    run.font.size = size or FONT_SIZE


def _missing_note(errors: dict, key: str) -> str:
    return f"[{errors.get(key) or MISSING_NOTE_FALLBACK}]"


# C0/C1 control characters (except tab/LF/CR, which are legal XML text) — not
# legal in XML 1.0 text content. Found live (2026-09-01, record 505542): a
# generated CAPA action description contained a raw 0x13 control character
# sitting exactly where the source text's own en-dash ("33 – 64 Amps") was
# clearly intended, which python-docx/lxml raises ValueError on instead of
# silently dropping. This is a defensive backstop at the point text is
# actually written into the document — not a fix for wherever the stray
# character came from (LLM output has been observed to occasionally emit
# one; a copy-pasted source document could just as easily carry one) — so
# any current or future source of an invalid character degrades to
# "silently stripped" rather than crashing the export.
_INVALID_XML_CHARS_RE = re.compile("[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")


def _xml_safe(text: str) -> str:
    return _INVALID_XML_CHARS_RE.sub("", text) if text else text


def _set_cell_text(cell, text: str) -> None:
    """Always inside a table — locked to TABLE_FONT_SIZE (10pt), one step
    down from body content's 11pt."""
    cell.text = _xml_safe(text) or ""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            _apply_font(run, TABLE_FONT_SIZE)


class _Cursor:
    """Wraps `doc` with a running paragraph-index offset.

    Every hardcoded body-paragraph index in this file (55, 59, 64, ...) is
    the position in the RAW TEMPLATE, before any content is filled in. That
    was always exactly right as long as every fill only ever REPLACED a
    paragraph's text in place — but bulleted multi-item content (Executive
    Summary's two fields, Initial Impact Assessment/Correction & Remedial's
    action lists) now expands one template slot into several real
    paragraphs (`_set_bulleted_paragraphs`), so that every bullet gets its
    own genuine hanging indent — the only way to have both a bullet's own
    line start flush AND its wrapped continuation line indent under the
    text at once (2026-08-28, per the user — Word's hanging indent only
    recognizes one "first line" per paragraph, so multiple bullets sharing
    one paragraph via soft breaks can never get this right for all of them
    simultaneously). Once a slot grows from 1 paragraph to N, every
    subsequent lookup in the ORIGINAL template's numbering is off by
    (N - 1) real paragraphs now sitting in the document ahead of it. This
    cursor is threaded through every _fill_* function instead of the bare
    `doc`, so `.paragraph(index)` always resolves against the template
    index PLUS whatever's been inserted so far, and `.doc` is still
    available for `.tables[N]` (tables aren't affected — inserting body
    paragraphs never shifts a table's own position in `doc.tables`)."""

    def __init__(self, doc):
        self.doc = doc
        self.offset = 0

    def paragraph(self, index: int) -> Paragraph:
        return Paragraph(self.doc.element.body[index + self.offset], self.doc)


# Left/hanging indent + matching custom tab stop used by every REAL
# multi-paragraph bulleted list this file builds (_set_bulleted_paragraphs)
# — the same value for all three, so a bullet's own "•" sits flush at the
# paragraph's un-hung position, the tab after it lands EXACTLY where the
# hanging indent pulls wrapped/continuation lines to, and every bulleted
# section in the document uses one consistent indent depth.
_BULLET_HANG = Pt(18)


def _set_paragraph_text(cursor: _Cursor, index: int, text: str, clear_italic: bool = False) -> None:
    """Reuses the first run's formatting (list-level, any other non-font
    properties) so this paragraph's existing style carries over, clearing
    any other runs so no template guidance text lingers alongside the real
    answer. Font/size are always forced (see FONT_NAME/FONT_SIZE above), not
    just carried over, since a genuinely blank paragraph's fresh run has
    neither set. `clear_italic` is for the couple of slots where the real
    answer replaces a paragraph that WAS the guidance text itself (e.g. Root
    Cause/Probable Cause statement) — per the user, 2026-08-25, the answer
    must read as real content, not still look like an italicized instruction.
    Also blackens the run's color — that same guidance styling is grey as
    well as italic, and clearing only italic left the real answer still
    grey (2026-08-28, per the user).

    left_indent/first_line_indent are normalized to 0 the same way
    _set_paragraph_lines already does — this template's blank slots for
    single-text answers carry the same kind of ad hoc, inconsistent indent
    values (e.g. left=709 on one slot, left=11 hanging=295 on another) that
    caused the earlier bulleted-content indentation bug, and it recurs here
    too: real generated text long enough to WORD-WRAP across multiple lines
    (not just multi-item lists joined by soft breaks) hits the exact same
    hanging-indent mismatch between a paragraph's first line and its wrapped
    continuation lines (2026-08-28, per the user: "it still indents
    improperly" — found in Problem Description's own wrapped text)."""
    text = _xml_safe(text)
    para = cursor.paragraph(index)
    para.paragraph_format.left_indent = 0
    para.paragraph_format.first_line_indent = 0
    if para.runs:
        run = para.runs[0]
        run.text = text
        if clear_italic:
            run.italic = False
            run.font.color.rgb = RGBColor(0, 0, 0)
        for extra in para.runs[1:]:
            extra.text = ""
    else:
        run = para.add_run(text)
        if clear_italic:
            run.italic = False
            run.font.color.rgb = RGBColor(0, 0, 0)
    _apply_font(run)


def _set_paragraph_lines(cursor: _Cursor, index: int, lines: List, clear_italic: bool = False) -> None:
    """Like _set_paragraph_text, but joins multiple lines with real line
    breaks (not just a delimiter) so multi-item narrative content (findings,
    history rows, checklists) actually reads as a list in the document.
    NOT used for real "•" bulleted lists any more — those need their own
    real paragraph per item so hanging indent works (_set_bulleted_paragraphs)
    — this stays for content that was never bulleted in any real report
    (History Review, Investigation Task, Impact Assessment, Risk Assessment;
    see each field's own call site) and already builds its own "" blank
    entries where a gap is wanted.

    A line is normally a plain string, but may instead be a `(text, bold)`
    tuple — e.g. the Investigation Task checklist's "N. <6M factor>" group
    headings (2026-08-26, per the user: "bold the 6M parameters so it is
    clear where each of those sections starts"). Bold is a run-level
    property, not something that can vary within one run's own text, so
    each line beyond the first gets its own new run instead of all sharing
    the paragraph's original single run via add_break()/add_text().

    left_indent/first_line_indent are normalized to 0 (2026-08-28, per the
    user) — this template's blank slots each carry their own unrelated ad
    hoc indent value (e.g. a 578-twip hanging indent here, a 142-twip left
    indent there), which caused the same hanging-indent-vs-wrapped-line
    mismatch _set_paragraph_text already documents, for content that was
    never bulleted in the first place — there's no caller here for whom
    leaving that stray indentation in place is correct."""
    def _split(line):
        text, bold = line if isinstance(line, tuple) else (line, False)
        return _xml_safe(text), bold

    lines = [line for line in lines if _split(line)[0]]
    para = cursor.paragraph(index)
    para.paragraph_format.left_indent = 0
    if len(lines) > 1:
        para.paragraph_format.first_line_indent = 0

    first_run = para.runs[0] if para.runs else para.add_run()
    # Clear any other pre-existing template runs (leftover guidance
    # fragments) before adding our own new runs below — otherwise the loop
    # below would end up appending to a paragraph whose later cleanup would
    # need to skip over its own freshly-added runs.
    for extra in list(para.runs[1:]):
        extra.text = ""

    text0, bold0 = _split(lines[0]) if lines else ("", False)
    first_run.text = text0
    first_run.bold = bold0
    if clear_italic:
        first_run.italic = False
    _apply_font(first_run)

    for line in lines[1:]:
        text, bold = _split(line)
        run = para.add_run()
        run.add_break()
        # NOT run.add_text(text) — see _set_bulleted_paragraphs' own comment
        # on the same issue: an embedded "\t" inserted this way is a literal
        # tab CHARACTER inside the <w:t> text node (a small fixed-width
        # space when Word renders it), not a real <w:tab/> tab-stop jump.
        # None of this function's own callers currently emit "\t" inside a
        # line, but splitting on it here anyway costs nothing and keeps this
        # function safe if one ever does.
        for i, part in enumerate(text.split("\t")):
            if i > 0:
                run.add_tab()
            if part:
                run.add_text(part)
        run.bold = bold
        if clear_italic:
            run.italic = False
        _apply_font(run)


def _set_bulleted_paragraphs(cursor: _Cursor, index: int, lines: List[str], clear_italic: bool = False, hanging: bool = True) -> None:
    """One genuine paragraph per item, not one paragraph with soft-broken
    lines (2026-08-28, per the user: "for bullet point next line, should be
    indented like the first point/sentence"). Word's hanging indent only
    recognizes one "first line" per PARAGRAPH — with multiple items sharing
    one paragraph, every item after the first one is itself just "another
    line" of that same paragraph, so it either (a) gets pulled back to the
    bullet position too (misaligning it from the wrapped continuation of its
    own text — the bug fixed 2026-08-26 by flattening indent to 0), or (b)
    gets indented to the text position (fixing the wrap-alignment but
    re-breaking (a)). A real separate paragraph per item sidesteps the
    conflict entirely: EVERY item gets its own fresh "first line" and its
    own genuine wrapped-continuation lines, correctly indented — exactly
    like a real Word list, because this now IS one.

    `hanging=True` (the "•\t"-prefixed callers, from `_bullet_lines`/
    `_maybe_bullet`'s Deviation branch) applies the hanging indent + a
    matching tab stop, so the bullet sits pulled back and both its own text
    and any wrapped continuation land at the same indented position.
    `hanging=False` (the plain, unbulleted callers — OOS's own real reports
    render these sentences with no bullet AND no indent at all, confirmed at
    the raw-XML level, still as separate paragraphs) keeps everything flush
    left instead — this function is still the right one to call for that
    case too, since real OOS reports use separate paragraphs per sentence,
    not one paragraph with soft breaks.

    Clones the anchor paragraph's own XML per extra item (so template
    run/paragraph properties like font size carry over identically to every
    clone, then get overridden the same way _set_paragraph_text/_lines
    already do) and inserts each clone directly after the previous one —
    increments `cursor.offset` by (item count - 1) so every subsequent
    _fill_* call still resolves against the template's original numbering
    correctly (see _Cursor's own docstring)."""
    lines = [_xml_safe(line) for line in lines if line]
    para = cursor.paragraph(index)
    if hanging:
        para.paragraph_format.left_indent = _BULLET_HANG
        para.paragraph_format.first_line_indent = -_BULLET_HANG
        para.paragraph_format.tab_stops.clear_all()
        para.paragraph_format.tab_stops.add_tab_stop(_BULLET_HANG, WD_TAB_ALIGNMENT.LEFT)
    else:
        para.paragraph_format.left_indent = 0
        para.paragraph_format.first_line_indent = 0
    # Word's own default paragraph-to-paragraph spacing already reads as a
    # blank line between items once each is a real paragraph (no manual
    # double-break needed the way the shared-paragraph approach required).
    para.paragraph_format.space_after = Pt(10)

    def _fill_one(target_para: Paragraph, text: str) -> None:
        run = target_para.runs[0] if target_para.runs else target_para.add_run()
        for extra in list(target_para.runs[1:]):
            extra.text = ""
        # Splitting on "\t" and calling add_tab() explicitly, same reasoning
        # as _set_paragraph_lines — run.text=/add_run(text) do NOT translate
        # an embedded tab character into a real <w:tab/> element, only the
        # oxml-level run-content APIs used here do.
        run.text = ""
        for i, part in enumerate(text.split("\t")):
            if i > 0:
                run.add_tab()
            if part:
                run.add_text(part)
        if clear_italic:
            run.italic = False
            run.font.color.rgb = RGBColor(0, 0, 0)
        _apply_font(run)

    if not lines:
        _fill_one(para, "")
        return

    _fill_one(para, lines[0])
    prev_p = para._p
    for line in lines[1:]:
        new_p = copy.deepcopy(para._p)
        prev_p.addnext(new_p)
        prev_p = new_p
        _fill_one(Paragraph(new_p, cursor.doc), line)
    cursor.offset += len(lines) - 1


def _strip_guidance_runs(doc) -> None:
    """Removes every italic run from every top-level body paragraph — this
    template consistently styles pure guidance/instructional text as italic
    (confirmed run-by-run), including runs that trail directly after a
    heading within the SAME paragraph (e.g. "Determination of root cause/
    probable cause: Provide a brief summary..." — the heading label itself
    is plain, only the trailing instruction is italic). Per the user
    (2026-08-25): "remove the small italic guidance texts. they are to be
    replaced by the content" — the two slots this file overwrites in place
    (Root Cause/Probable Cause statement, Impact Assessment's Conclusion
    Statement — the guidance paragraph itself IS the answer slot there, no
    separate blank exists) already have their own run's italic cleared
    before this runs, via _set_paragraph_text's clear_italic, so the real
    content they now hold survives this pass untouched. A paragraph left
    with nothing in it once its only run(s) were guidance is removed
    entirely rather than leaving a stray empty line."""
    for child in list(doc.element.body):
        if child.tag != qn("w:p"):
            continue
        para = Paragraph(child, doc)
        for run in list(para.runs):
            if run.italic:
                run.element.getparent().remove(run.element)
        if not para.runs and not para.text.strip():
            child.getparent().remove(child)


def _ensure_row_count(table, first_data_row: int, count: int, template_row: Optional[int] = None) -> List[Any]:
    """Adjusts `table` so it has exactly `max(count, 1)` data rows starting
    at `first_data_row` — cloning `template_row` (defaults to
    `first_data_row`) to grow, or dropping trailing rows to shrink. Always
    keeps at least one row: a single blank/"N/A" row reads better than a
    headers-only table when a list is genuinely empty. Returns the data rows."""
    if template_row is None:
        template_row = first_data_row
    current = len(table.rows) - first_data_row
    target = max(count, 1)
    if target > current:
        template_tr = copy.deepcopy(table.rows[template_row]._tr)
        for _ in range(target - current):
            table._tbl.append(copy.deepcopy(template_tr))
    elif target < current:
        for row in list(table.rows)[first_data_row + target :]:
            row._tr.getparent().remove(row._tr)
    for row in list(table.rows)[first_data_row : first_data_row + target]:
        for cell in row.cells:
            _set_cell_text(cell, "")
    return list(table.rows)[first_data_row : first_data_row + target]


# Splits sentence-per-idea narrative text into bullet lines for the two Executive
# Summary fields (immediate_containment_action, determination_of_root_cause) whose own
# prompt already asks for "each its own sentence" / "every distinct action" — the
# underlying data is one string (shared with ds/frontend, not changed here), so the
# list rendering happens only at export time. Splits on sentence-ending punctuation
# followed by whitespace and a capital letter/open-paren, to avoid breaking on
# mid-sentence abbreviations like "No." or "kW." in the common case — best-effort, not
# used anywhere content is parsed back out, so an occasional over-split just reads as a
# shorter bullet rather than a wrong one.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def _bullet_lines(text: str) -> List[str]:
    if not text:
        return []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    return [f"•\t{s}" for s in sentences]


# OOS/OOT's own real reports render this same sentence-per-idea narrative
# WITHOUT a bullet character at all — each sentence its own plain paragraph,
# separated by blank spacing, confirmed across 3 real OOS reports at the raw
# XML level (2026-08-28, per the user: formatting only, sourced from the "50
# Historical Report" samples). Deviation/Market Complaint's own real reports
# use literal "•" bullets for this same narrative, so this is a genuine
# per-type formatting split, not a single shared convention.
def _plain_lines(text: str) -> List[str]:
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


# Initial Impact Assessment's Immediate Actions and Correction/Remedial
# Action both already arrive as a list of distinct action strings (not one
# blob needing sentence-splitting) — unlike the two Executive Summary
# fields above, so this just prefixes each existing item rather than
# reusing _bullet_lines/_plain_lines. Real reports show Deviation
# consistently bulleting both of these sections (2/2 samples each);
# OOS/OOT/Market Complaint stay plain (2026-08-28, per the user, sourced
# from the "50 Historical Report" samples — OOT's own 2 samples were split
# 1 bulleted/1 plain on each section, so it defaults to plain here rather
# than being forced either way on weak evidence).
def _maybe_bullet(lines: List[str], event_type: str) -> List[str]:
    if event_type != "Deviation":
        return lines
    return [f"•\t{line}" for line in lines]


def _sourced(item) -> str:
    return item.value if item else ""


def _yesno(value: bool) -> str:
    return "Yes" if value else "No"


# ── 1. Executive Summary ────────────────────────────────────────────────

def _fill_executive_summary(cursor: _Cursor, section, event_type: str, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(cursor, 55, _missing_note(errors, "executive_summary"))
        return
    # OOS specifically renders this narrative as plain unbulleted sentences
    # (0 real bullets across 3 real OOS reports checked at the raw-XML
    # level) — every other event type uses some form of bulleted formatting:
    # Deviation and OOT both use genuine Word bullets extensively (2 samples
    # each), Market Complaint uses literal "•" characters (1 sample
    # checked) — now rendered as a real bulleted paragraph list either way
    # (_set_bulleted_paragraphs). "OOS/OOT" (the combined literal) is
    # grouped with plain OOS here since OOS is the one confirmed exception
    # among four types and the combined value doesn't disambiguate which one
    # a given record actually is.
    is_plain = event_type in ("OOS", "OOS/OOT")
    lines_fn = _plain_lines if is_plain else _bullet_lines
    # Paragraph 55 (section.summary — the short lead-in blurb before the
    # "Problem Description" heading) is deliberately left unpopulated
    # (2026-08-28, per the user) — it's a blank slot in the raw template
    # with no runs of its own, so leaving it blank means
    # _strip_guidance_runs removes it entirely rather than leaving a stray
    # empty line.
    _set_paragraph_text(cursor, 59, section.problem_description)
    _set_bulleted_paragraphs(cursor, 64, lines_fn(section.immediate_containment_action), hanging=not is_plain)
    _set_bulleted_paragraphs(cursor, 71, lines_fn(section.determination_of_root_cause), hanging=not is_plain)
    _set_paragraph_text(cursor, 74, section.root_cause_probable_cause_statement, clear_italic=True)
    _set_paragraph_text(cursor, 80, section.impact_assessment)
    _set_paragraph_text(cursor, 86, section.correction_conclusion_preventive_actions)
    _set_paragraph_text(cursor, 87, f"Conclusion Statement: {section.conclusion_statement}")


# ── 2. Description of Event ─────────────────────────────────────────────

def _fill_description_of_event(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[1]
    if section is None:
        _set_cell_text(table.rows[1].cells[1], _missing_note(errors, "description_of_event"))
        return
    _set_cell_text(table.rows[1].cells[1], section.what_happened)
    _set_cell_text(table.rows[2].cells[1], section.when_happened)
    _set_cell_text(table.rows[3].cells[1], section.who_identified)
    _set_cell_text(table.rows[4].cells[1], section.where_it_happened)
    _set_cell_text(table.rows[5].cells[1], _sourced(section.nonconforming_reference))
    _set_cell_text(table.rows[6].cells[1], _sourced(section.how_detected))


# ── 3. Initial Impact Assessment & Immediate Actions ────────────────────

def _fill_initial_impact_assessment(cursor: _Cursor, section, event_type: str, errors: dict) -> None:
    material_table = cursor.doc.tables[2]
    equipment_table = cursor.doc.tables[3]
    if section is None:
        rows = _ensure_row_count(material_table, 1, 1)
        _set_cell_text(rows[0].cells[1], _missing_note(errors, "initial_impact_assessment"))
        _ensure_row_count(equipment_table, 1, 1)
        _set_paragraph_text(cursor, 107, "")
        return

    impacts = section.material_product_impacts
    rows = _ensure_row_count(material_table, 1, len(impacts))
    if not impacts:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, impacts)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.material_product_batch)
        # cells[2]'s template header is "Batch Number" — now a genuine
        # structured field (2026-09-03, per the user), not stage text filling
        # a column its header doesn't name.
        _set_cell_text(row.cells[2], item.batch_number)
        # cells[3]'s template header is "Action taken (Hold/Quarantined etc.)" — lead
        # with the actual hold/quarantine status rather than burying it after the
        # impact classification, which isn't a "Hold/Quarantined etc." action at all.
        hold_status = f"On hold: {_sourced(item.quantity_on_hold)}" if _sourced(item.quantity_on_hold) else "No hold/quarantine action recorded"
        action = f"{hold_status} (Qty involved: {item.quantity_involved}; Impact: {item.type_of_impact})"
        _set_cell_text(row.cells[3], action)

    equip = section.equipment_impacts
    rows = _ensure_row_count(equipment_table, 1, len(equip))
    if not equip:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, equip)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], _sourced(item.equipment_instrument))
        _set_cell_text(row.cells[2], _sourced(item.identification_number))
        actions = item.actions_initiated
        lines = []
        if actions.operation_suspended:
            lines.append("Operation suspended.")
        if actions.on_hold_label_affixed:
            lines.append("'On Hold' label affixed.")
        if actions.other_action_taken:
            spec = f" [Specify: {actions.other_action_specify}]" if actions.other_action_specify else ""
            lines.append(f"Other action taken{spec}.")
        _set_cell_text(row.cells[3], " ".join(lines) or "None")

    is_deviation = event_type == "Deviation"
    _set_bulleted_paragraphs(cursor, 107, _maybe_bullet(section.immediate_actions, event_type), hanging=is_deviation)


# ── 4. Summary of Historical Review ─────────────────────────────────────

def _fill_history_review(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[4]
    if section is None:
        rows = _ensure_row_count(table, 1, 1)
        _set_cell_text(rows[0].cells[2], _missing_note(errors, "history_review"))
        _set_paragraph_text(cursor, 117, "")
        return

    rows = _ensure_row_count(table, 1, len(section.rows))
    if not section.rows:
        _set_cell_text(rows[0].cells[2], "N/A")
    for i, (row, item) in enumerate(zip(rows, section.rows)):
        _set_cell_text(row.cells[0], f"{i + 1}.")
        _set_cell_text(row.cells[1], item.event_number)
        _set_cell_text(row.cells[2], item.event_title)
        _set_cell_text(row.cells[3], item.capa_description)
        _set_cell_text(row.cells[4], item.capa_implementation_date)

    lines = [
        section.search_scope_note,
        f"Lookback period: {section.lookback_months} months.",
        # Trust the table's own row data over ds's no_similar_events_found
        # flag — the two have been observed to disagree (flag true while
        # rows is non-empty), which would otherwise show this line right
        # next to a table full of actual historical events (2026-09-02,
        # per the user).
        "No similar events found in the lookback window." if section.no_similar_events_found and not section.rows else "",
        section.closing_narrative,
        f"Batches manufactured: {section.batches_manufactured_note}" if section.batches_manufactured_note else "",
    ]
    _set_paragraph_lines(cursor, 117, lines)


# ── 5. Investigation Task ───────────────────────────────────────────────

def _fill_investigation_task(cursor: _Cursor, section, errors: dict):
    """Section 5 (Investigation Task) — three explicit parts, in display
    order (2026-09-01, per the user): task_summary, why_why_analysis, then
    root_cause_identification. Fishbone/Fault Tree/Flowchart were dropped
    entirely this same date — Why-Why Analysis is now the only RCA method
    this section ever demonstrates.

    Only task_summary and the why_why_analysis header line are written into
    paragraph 132 here; the Why-Why chain itself (a real Word table) and
    root_cause_identification (a new trailing paragraph) are appended by
    _insert_why_why_table_and_grounding, which must run after every other
    _fill_* call since it inserts new top-level body elements. Returns the
    paragraph-132 element captured at THIS point in the pipeline (while
    cursor.offset reflects only what earlier sections have already
    inserted), so that later call can anchor off it correctly regardless of
    how much cursor.offset grows from sections filled afterward.

    Paragraph 132's own style in the template is "Heading 1" — inherited
    from the "Investigation tasks:" heading and its italic guidance
    paragraphs right above it (confirmed via python-docx), unlike every
    other section's blank (e.g. Executive Summary's, "Normal"/"List
    Paragraph"). Left as-is, real content here renders as an oversized bold
    heading instead of body text — reset explicitly so this reads like the
    rest of the document.
    """
    cursor.paragraph(132).style = "Normal"

    if section is None:
        _set_paragraph_text(cursor, 132, _missing_note(errors, "investigation_task"))
        return None

    # Grouped under a numbered "N. <6M factor>" heading (per the reference
    # export, 2026-08-26) whenever `task.six_m_factor` changes — every
    # task's own `tick` is already "<group>.<item>" (e.g. "1.1", "1.2",
    # "2.1"), so the group number is read straight off it rather than
    # tracked separately, guaranteeing they can't drift apart. A blank line
    # precedes every task line (including the first one under a new
    # heading) but not the heading itself, which follows the previous
    # group's last task directly — matches the reference exactly.
    lines = [section.task_summary.overview, ""]
    last_group: Optional[str] = None
    for task in section.task_summary.tasks:
        group = task.tick.split(".", 1)[0]
        if group != last_group:
            lines.append((f"{group}.\t{task.six_m_factor}", True))
            last_group = group
        lines.append("")
        lines.append(f"{task.tick}\t{task.title} ({task.six_m_factor}): {task.outcome}")

    lines.append("")
    demo = section.why_why_analysis
    lines.append(f"Why-Why Analysis (6M Factor: {demo.six_m_factor}): {demo.method_rationale}")
    lines.append("  See table below.")

    _set_paragraph_lines(cursor, 132, lines)
    return cursor.paragraph(132)._p


def _insert_why_why_table_and_grounding(doc, section, anchor) -> None:
    """Inserts the Why-Why Analysis table right after the Investigation Task
    paragraph, then a new paragraph holding root_cause_identification's
    grounding evidence right after that table (2026-09-01, per the user —
    root_cause_identification now comes AFTER the why-why analysis, not
    before it, and Fishbone/Fault Tree/Flowchart demonstrations are gone).

    MUST run after every other _fill_* call in build_rci_report_docx: this is
    the first place in this file that inserts a brand-new top-level element
    into doc.element.body rather than mutating an existing paragraph/table/
    row in place, or growing a table's own bulleted-paragraph run via
    cursor.offset (which every later _fill_* call already accounts for).
    `anchor` is the actual paragraph-132 element _fill_investigation_task
    captured at the point that section ran, not re-derived from a fixed
    index here, so it stays valid no matter how much cursor.offset grew from
    sections filled afterward.
    """
    if section is None or anchor is None:
        return
    reference_style = doc.tables[1].style  # Description of Event — a plain 2-column table

    demo = section.why_why_analysis
    table = doc.add_table(rows=1 + len(demo.why_why_chain), cols=2)
    table.style = reference_style
    header_cells = table.rows[0].cells
    _set_cell_text(header_cells[0], "Question")
    _set_cell_text(header_cells[1], "Answer")
    for cell in header_cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for row, step in zip(table.rows[1:], demo.why_why_chain):
        _set_cell_text(row.cells[0], step.question)
        _set_cell_text(row.cells[1], step.answer)
    anchor.addnext(table._tbl)
    anchor = table._tbl

    grounding_lines = [
        "Root cause identification:",
        section.root_cause_identification.grounding_evidence,
    ]
    for link in section.root_cause_identification.applicable_tasks:
        grounding_lines.append(f"  {link.tick}\t{link.title} ({link.six_m_factor}): {link.explanation}")
    grounding_lines = [_xml_safe(line) for line in grounding_lines]

    new_para = doc.add_paragraph()
    run = new_para.add_run(grounding_lines[0])
    for line in grounding_lines[1:]:
        run.add_break()
        run.add_text(line)
    _apply_font(run)
    anchor.addnext(new_para._p)


# ── 6. Root Cause conclusion ─────────────────────────────────────────────

def _fill_root_cause_conclusion(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[5]
    if section is None:
        _set_cell_text(table.rows[1].cells[0], _missing_note(errors, "root_cause_conclusion"))
        return
    _set_cell_text(table.rows[1].cells[0], section.conclusion)
    repeat_para = table.rows[1].cells[0].add_paragraph(
        _xml_safe(f"Repeat occurrence: {_yesno(section.is_repeat_occurrence)} — {section.repeat_occurrence_evidence}")
    )
    for run in repeat_para.runs:
        _apply_font(run, TABLE_FONT_SIZE)
    _set_cell_text(table.rows[2].cells[0], f"Category: {section.taxonomy.category}   Subcategory: {section.taxonomy.sub_category}")


# ── 7. Impact Assessment & Conclusion (Batch disposition) ──────────────

_IMPACT_SUBSECTION_LABELS = [
    ("impact_on_affected_batches", "Impact on Affected Batches"),
    ("impact_on_marketed_released_batches", "Impact on Marketed/Released Batches"),
    ("impact_on_other_product_material_area_process", "Impact on Other Product/Material/Area/Process"),
    ("impact_on_regulatory_filing", "Impact on Regulatory Filing"),
    ("impact_on_facility_equipment_instrument", "Impact on Facility/Equipment/Instrument"),
    ("impact_on_manufacturing_process_analytical_method", "Impact on Manufacturing Process/Analytical Method"),
    ("business_continuity", "Business Continuity"),
    ("impact_on_data_integrity", "Impact on Data Integrity"),
    ("stability_repackaging_requirement", "Stability/Repackaging Requirement"),
    ("patient_safety", "Patient Safety"),
    ("others_as_applicable", "Others, as applicable"),
]


def _fill_impact_assessment_batch_disposition(cursor: _Cursor, section, risk_section, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(cursor, 165, _missing_note(errors, "impact_assessment_batch_disposition"))
    else:
        lines = []
        for field_name, label in _IMPACT_SUBSECTION_LABELS:
            sub = getattr(section, field_name)
            # Every subsection renders, applicable or not (2026-09-01, per the
            # user) — a subsection marked not applicable was still considered
            # and ruled out, with its own narrative saying why; silently
            # omitting it left a reader unable to tell "considered, ruled
            # out" apart from "never considered at all."
            lines.append(f"{label}: {sub.narrative}")
            if field_name == "impact_on_affected_batches" and sub.batch_shipper_table:
                for row in sub.batch_shipper_table:
                    lines.append(f"  - Batch {row.batch_number}: {row.number_of_shippers} shipper(s), defects: {row.defects}")
        _set_paragraph_lines(cursor, 165, lines)
        _set_paragraph_text(cursor, 170, f"Conclusion Statement: {section.conclusion}", clear_italic=True)

    extra_lines = []
    if section is not None:
        if section.medical_investigation_summary:
            extra_lines.append(f"Medical Investigation Summary: {section.medical_investigation_summary}")
        if section.health_hazard_evaluation:
            extra_lines.append(f"Health Hazard Evaluation: {section.health_hazard_evaluation}")
        if section.impact_justification:
            extra_lines.append(f"Impact Justification: {section.impact_justification}")

    # No slot exists anywhere in this template for Risk Assessment (see
    # module docstring) — appended here, clearly labeled, rather than
    # silently dropped.
    if risk_section is None:
        extra_lines.append(f"Risk Assessment: {_missing_note(errors, 'risk_assessment')}")
    else:
        extra_lines.append(f"Risk Assessment applicability: {risk_section.applicable} — {risk_section.applicability_reason}")
        for c in risk_section.candidates:
            extra_lines.append(
                f"  - {c.cause_label}: Severity {c.factors.severity.tier} ({c.severity_score}), "
                f"Repeatability {c.factors.repeatability.tier} ({c.repeatability_score}), "
                f"Detectability {c.factors.detectability.tier} ({c.detectability_score}), "
                f"RPN {c.rpn}, Risk level {c.risk_level}"
            )
    _set_paragraph_lines(cursor, 171, extra_lines)


# ── 8. Correction and/or Remedial Action ────────────────────────────────

def _fill_correction_remedial_action(cursor: _Cursor, section, event_type: str, errors: dict) -> None:
    if section is None:
        _set_paragraph_text(cursor, 173, _missing_note(errors, "correction_remedial_action"))
        _set_paragraph_text(cursor, 174, "")
        return
    lines = [f"{item.observation} — Status: {item.status}" + (f" [Ref: {item.reference_number}]" if item.reference_number else "") for item in section.items]
    is_deviation = event_type == "Deviation"
    _set_bulleted_paragraphs(cursor, 173, _maybe_bullet(lines or ["N/A"], event_type), hanging=is_deviation)
    _set_bulleted_paragraphs(cursor, 174, _maybe_bullet(section.additional_notes, event_type), hanging=is_deviation)


# ── 9/10/11. CAPA (actions / interim controls / extrapolation) ─────────

def _fill_capa(cursor: _Cursor, section, errors: dict) -> None:
    actions_table = cursor.doc.tables[6]
    interim_table = cursor.doc.tables[7]
    extrapolation_table = cursor.doc.tables[8]

    if section is None:
        _set_paragraph_text(cursor, 180, _missing_note(errors, "capa"))
        rows = _ensure_row_count(actions_table, 1, 1)
        _set_cell_text(rows[0].cells[1], _missing_note(errors, "capa"))
        _ensure_row_count(interim_table, 1, 1)
        _ensure_row_count(extrapolation_table, 1, 1)
        return

    _set_paragraph_text(cursor, 180, section.capa_not_applicable_justification or "")

    rows = _ensure_row_count(actions_table, 1, len(section.capa_actions))
    if not section.capa_actions:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, section.capa_actions)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.description)
        _set_cell_text(row.cells[2], item.responsibility or "")
        _set_cell_text(row.cells[3], item.due_date)

    rows = _ensure_row_count(interim_table, 1, len(section.interim_controls))
    if not section.interim_controls:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, section.interim_controls)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.description)
        _set_cell_text(row.cells[2], item.responsibility)
        _set_cell_text(row.cells[3], item.due_date)

    rows = _ensure_row_count(extrapolation_table, 1, 1)
    extrapolation = section.extrapolation
    if not extrapolation.applicable:
        _set_cell_text(rows[0].cells[1], f"Not applicable — {extrapolation.justification}")
    else:
        details = [extrapolation.justification, extrapolation.scope_description]
        for label, values in (
            ("Customers", extrapolation.related_customers),
            ("Markets", extrapolation.related_markets),
            ("CAPA numbers", extrapolation.capa_numbers),
            ("Change controls", extrapolation.related_change_controls),
        ):
            if values:
                details.append(f"{label}: {', '.join(values)}")
        _set_cell_text(rows[0].cells[1], " | ".join(d for d in details if d))
    _set_cell_text(rows[0].cells[0], "1.")
    _set_cell_text(rows[0].cells[2], extrapolation.responsibility)
    _set_cell_text(rows[0].cells[3], extrapolation.due_date)


# ── 12. CAPA Effectiveness Check Plan ────────────────────────────────────

def _fill_capa_effectiveness_check_plan(cursor: _Cursor, section, errors: dict) -> None:
    table = cursor.doc.tables[9]
    if section is None:
        _set_paragraph_text(cursor, 188, _missing_note(errors, "capa_effectiveness_check_plan"), clear_italic=True)
        _ensure_row_count(table, 1, 1)
        return

    _set_paragraph_text(cursor, 188, section.capa_not_applicable_justification or "", clear_italic=True)

    plans = section.generated_plans
    rows = _ensure_row_count(table, 1, len(plans))
    if not plans:
        _set_cell_text(rows[0].cells[1], "N/A")
    for i, (row, item) in enumerate(zip(rows, plans)):
        _set_cell_text(row.cells[0], str(i + 1))
        _set_cell_text(row.cells[1], item.capa_description)
        _set_cell_text(row.cells[2], "; ".join(item.effectiveness_check))
        criteria = "; ".join(item.effectiveness_criteria)
        extra = f" (Duration: {item.monitoring_duration} — {item.duration_tier})"
        _set_cell_text(row.cells[3], criteria + extra)
        _set_cell_text(row.cells[4], item.responsibility)


# Body-paragraph indices of every major heading in the real template — a
# page break is forced immediately before each one so every section starts
# on its own page (2026-08-25, per the user), matching how a real printed/
# reviewed investigation report is organized. In heading order: Executive
# Summary, Description of Event, Initial Impact Assessment, Summary of
# Historical Review, Investigation Task, Root Cause conclusion, Impact
# Assessment & Conclusion, Correction and/or Remedial Action, Corrective &
# Preventive Action (CAPA), CAPA Effectiveness Check Plan, List of
# Annexures, Report Approval. Risk Assessment has no heading of its own
# (see module docstring) so it isn't included. Indices are fixed at the
# TEMPLATE's own layout, not affected by _strip_guidance_runs (which only
# ever removes pure-guidance paragraphs, never a heading).
_SECTION_HEADING_INDICES = [53, 92, 95, 110, 128, 133, 163, 172, 176, 185, 192, 195]

# One bookmark name per heading above, same order — lets the Index table's
# "Page No." column (table 0, rows 1-12) reference each section's real
# on-page location via a PAGEREF field, rather than staying blank forever
# (2026-09-02, per the user: page numbers "aren't tracked anywhere in this
# app" was a known, deliberate gap until now — python-docx itself can't
# compute a page number since it never paginates the document, but Word
# can and does, once it opens the file and recalculates fields).
_SECTION_BOOKMARK_NAMES = [
    "sec_executive_summary",
    "sec_description_of_event",
    "sec_initial_impact_assessment",
    "sec_historical_review",
    "sec_investigation_tasks",
    "sec_root_cause_conclusion",
    "sec_impact_assessment_conclusion",
    "sec_correction_remedial_action",
    "sec_capa",
    "sec_effectiveness_check_plan",
    "sec_annexures",
    "sec_approval",
]


def _insert_bookmark(paragraph: Paragraph, bookmark_id: int, name: str) -> None:
    p = paragraph._p
    pPr = p.find(qn("w:pPr"))
    index = list(p).index(pPr) + 1 if pPr is not None else 0

    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))

    p.insert(index, start)
    p.insert(index + 1, end)


def _add_page_breaks(cursor: _Cursor) -> None:
    # Always called first, before any bulleted-paragraph expansion, so
    # cursor.offset is still 0 here — kept cursor-based anyway (rather than
    # taking `doc` directly) purely for signature consistency with every
    # other function in this file. Also plants each section's bookmark
    # here, at the same paragraph, for the same reason (offset is still 0).
    for bookmark_id, (index, name) in enumerate(zip(_SECTION_HEADING_INDICES, _SECTION_BOOKMARK_NAMES)):
        heading = cursor.paragraph(index)
        heading.paragraph_format.page_break_before = True
        _insert_bookmark(heading, bookmark_id, name)


def _set_cell_pageref(cell, bookmark_name: str) -> None:
    """Replaces a table cell's content with a Word PAGEREF field pointing at
    `bookmark_name`. Word (not python-docx, which never paginates a
    document) computes and fills in the real page number the moment it
    opens the file, since _enable_field_auto_update below forces every
    field to recalculate on open — "1" here is only ever the unresolved
    placeholder python-docx itself leaves behind."""
    cell.text = ""
    paragraph = cell.paragraphs[0]
    p = paragraph._p
    for old_run in list(paragraph.runs):
        p.remove(old_run._element)

    def _field_char(fld_type: str, dirty: bool = False):
        run_el = OxmlElement("w:r")
        fld = OxmlElement("w:fldChar")
        fld.set(qn("w:fldCharType"), fld_type)
        if dirty:
            fld.set(qn("w:dirty"), "true")
        run_el.append(fld)
        return run_el

    begin_run = _field_char("begin", dirty=True)

    instr_run = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" PAGEREF {bookmark_name} \\h "
    instr_run.append(instr)

    separate_run = _field_char("separate")

    result_run = OxmlElement("w:r")
    result_text = OxmlElement("w:t")
    result_text.text = "1"
    result_run.append(result_text)

    end_run = _field_char("end")

    for run_el in (begin_run, instr_run, separate_run, result_run, end_run):
        p.append(run_el)
        _apply_font(Run(run_el, paragraph), TABLE_FONT_SIZE)


def _fill_index_page_numbers(cursor: _Cursor) -> None:
    table = cursor.doc.tables[0]
    for row_offset, name in enumerate(_SECTION_BOOKMARK_NAMES):
        _set_cell_pageref(table.rows[row_offset + 1].cells[3], name)


def _enable_field_auto_update(doc) -> None:
    settings = doc.settings.element
    update_fields = OxmlElement("w:updateFields")
    update_fields.set(qn("w:val"), "true")
    settings.append(update_fields)


# ── 13. Annexures & Approval (pure pass-through, never None) ────────────

def _fill_annexures(cursor: _Cursor, section) -> None:
    table = cursor.doc.tables[10]
    rows = _ensure_row_count(table, 1, len(section.items))
    for row, item in zip(rows, section.items):
        _set_cell_text(row.cells[0], item.annexure_no)
        _set_cell_text(row.cells[1], item.title)


_APPROVAL_ROLE_LABELS = {
    "investigator": 1,
    "hod": 2,
    "qa": 3,
    "sit": 4,
    "head-qa": 5,
    "head qa": 5,
}


def _fill_approval(cursor: _Cursor, section) -> None:
    table = cursor.doc.tables[11]
    for row in section.rows:
        row_idx = _APPROVAL_ROLE_LABELS.get(row.role.strip().lower())
        if row_idx is None:
            continue
        target = table.rows[row_idx]
        _set_cell_text(target.cells[1], row.name or "")
        _set_cell_text(target.cells[2], row.title or "")
        _set_cell_text(target.cells[3], row.department or "")
        _set_cell_text(target.cells[4], row.signature_date or "")


def _tw_text(trackwise_fields: Dict[str, Any], *keys: str) -> str:
    """First non-empty TrackWise field among `keys`, stringified — values
    here can be a plain string, a list (joined), or a number
    (dim_rci.rci_key, unlike every other TrackWise field, is an int)."""
    for key in keys:
        value = trackwise_fields.get(key)
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if value:
            return str(value)
    return ""


def _fill_header_table(doc, record_id: str, trackwise_fields: Dict[str, Any]) -> None:
    table = doc.sections[0].header.tables[0]
    _set_cell_text(table.rows[1].cells[1], _tw_text(trackwise_fields, "Product Name / Material Name", "Products Information"))
    _set_cell_text(table.rows[1].cells[3], _tw_text(trackwise_fields, "Product / Material Code"))
    _set_cell_text(table.rows[2].cells[1], record_id)
    _set_cell_text(table.rows[2].cells[3], _tw_text(trackwise_fields, "RCI Number"))
    _set_cell_text(table.rows[3].cells[1], _tw_text(trackwise_fields, "Batch Number / AR Number"))
    _set_cell_text(table.rows[3].cells[3], _tw_text(trackwise_fields, "Date Opened", "Date Complaint Received"))


def build_rci_report_docx(record_id: str, trackwise_fields: Dict[str, Any], report: RciReportSections, event_type: str) -> bytes:
    doc = docx.Document(str(TEMPLATE_PATH))
    errors = report.errors or {}
    # Threaded through every _fill_* call below instead of the bare `doc` —
    # see _Cursor's own docstring. Sections run in the SAME top-to-bottom
    # order they appear in the document, which is required: each section
    # that expands a bulleted list into several real paragraphs
    # (_set_bulleted_paragraphs) grows cursor.offset immediately, so every
    # later call already sees the correct shift; a call running out of
    # order would resolve against the wrong paragraph.
    cursor = _Cursor(doc)

    _add_page_breaks(cursor)
    _fill_index_page_numbers(cursor)
    _fill_header_table(doc, record_id, trackwise_fields)
    _fill_executive_summary(cursor, report.executive_summary, event_type, errors)
    _fill_description_of_event(cursor, report.description_of_event, errors)
    _fill_initial_impact_assessment(cursor, report.initial_impact_assessment, event_type, errors)
    _fill_history_review(cursor, report.history_review, errors)
    investigation_task_anchor = _fill_investigation_task(cursor, report.investigation_task, errors)
    _fill_root_cause_conclusion(cursor, report.root_cause_conclusion, errors)
    _fill_impact_assessment_batch_disposition(cursor, report.impact_assessment_batch_disposition, report.risk_assessment, errors)
    _fill_correction_remedial_action(cursor, report.correction_remedial_action, event_type, errors)
    _fill_capa(cursor, report.capa, errors)
    _fill_capa_effectiveness_check_plan(cursor, report.capa_effectiveness_check_plan, errors)
    _fill_annexures(cursor, report.annexures)
    _fill_approval(cursor, report.approval)

    # Must run after every _fill_* call above — inserts new body elements,
    # which would shift every later fixed body-paragraph/table index still
    # relied on above (see _insert_why_why_table_and_grounding's own
    # docstring).
    _insert_why_why_table_and_grounding(doc, report.investigation_task, investigation_task_anchor)

    # Must run last — reads the document's final paragraph structure
    # directly (not by index), so it's unaffected by however much
    # cursor.offset grew, but every _fill_* call above still needs its own
    # target paragraph to exist with its original guidance runs intact
    # until it's actually written.
    _strip_guidance_runs(doc)
    _enable_field_auto_update(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
