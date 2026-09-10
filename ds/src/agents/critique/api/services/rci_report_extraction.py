"""
Extract Root Cause Conclusion, Impact Assessment & Conclusion (Batch disposition),
Correction and/or Remedial Action, and CAPA from a completed RCI report docx.

The RCI report is a free-form Word document structured with headings. This module
scans body elements in document order to locate and extract the relevant sections.
"""

import difflib
import re
from pathlib import Path
from docx import Document
from markitdown import MarkItDown

_md = MarkItDown()
_BASE64_RE = re.compile(r"!\[.*?\]\(data:[^)]+\)", re.DOTALL)

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_CHECKED_SYMBOLS = {("Wingdings", "F0FE"), ("Wingdings 2", "F052")}


# ── Low-level helpers ──────────────────────────────────────────────────────────

def _elem_text(elem) -> str:
    return "".join(t.text or "" for t in elem.findall(f".//{{{_W}}}t")).strip()


def _run_is_italic(r_elem) -> bool:
    rPr = r_elem.find(f"{{{_W}}}rPr")
    if rPr is None:
        return False
    i_elem = rPr.find(f"{{{_W}}}i")
    if i_elem is None:
        return False
    return i_elem.get(f"{{{_W}}}val") not in ("0", "false")


def _elem_text_excluding_italic(elem) -> str:
    """Like _elem_text, but skips italic runs. This template family
    consistently styles pure guidance/instructional placeholder text (an
    unfilled answer prompt, e.g. "(write the final decision about
    product/batch disposition...)") as italic, distinct from the
    investigator's own real content -- confirmed run-by-run against a real
    uploaded document, 2026-09-01 -- exactly the same convention already
    handled on the *export* side by _strip_guidance_runs in
    rci_report_export.py. This extractor previously had no equivalent on
    the *input* side, so every "verbatim" field it produces (rc_conclusion_
    text, impact_assessment_text, impact_conclusion_text,
    correction_remedial_text, capa_overall_text, problem_statement,
    investigation_summary) could silently include unfilled template
    boilerplate as if it were the investigator's own drafted content."""
    parts = [
        t.text or ""
        for r_elem in elem.findall(f".//{{{_W}}}r")
        if not _run_is_italic(r_elem)
        for t in r_elem.findall(f"{{{_W}}}t")
    ]
    return "".join(parts).strip()


def _heading_level(p_elem) -> int | None:
    """Return heading level (1, 2, 3 …) or None if not a heading."""
    pPr = p_elem.find(f"{{{_W}}}pPr")
    if pPr is None:
        return None
    pStyle = pPr.find(f"{{{_W}}}pStyle")
    if pStyle is None:
        return None
    val = (pStyle.get(f"{{{_W}}}val") or "").lower()
    if "heading" not in val:
        return None
    # extract trailing digit, e.g. "heading1" → 1, "heading 2" → 2
    m = re.search(r"\d+", val)
    return int(m.group()) if m else 1


def _is_h1(p_elem) -> bool:
    """True only for Heading 1 — used for section-boundary detection."""
    return _heading_level(p_elem) == 1


def _is_any_heading(p_elem) -> bool:
    return _heading_level(p_elem) is not None


def _sym_checked(sym_elem) -> bool:
    font = sym_elem.get(f"{{{_W}}}font")
    char = sym_elem.get(f"{{{_W}}}char")
    return (font, char) in _CHECKED_SYMBOLS


_UNCHECKED_YES_NO_RE = re.compile(r"\byes\b\s*/?\s*\bno\b")


def _repeat_occurrence_from_text(text: str) -> bool | None:
    """Plain-text (no checkbox/symbol available) repeat-occurrence heuristic, shared
    between the table-row and paragraph extraction paths. Returns None (genuinely
    unknown) rather than guessing when the text is an unchecked "Yes No" template
    placeholder — found live (2026-08-25) against a real document whose text was
    literally "...is a repeat occurrence Yes No. If yes, Mention the details as:
    Not Applicable": the previous naive "'yes' in text and 'no' not in text.split
    ('yes')[-1]" check split on the WRONG "yes" occurrence (there are two — the
    unchecked option and the "if yes" clause) and misread this unmarked placeholder
    as a confirmed True."""
    tl = text.lower()
    if re.search(r"no recurring|no recurrence|not.*repeat", tl):
        return False
    if _UNCHECKED_YES_NO_RE.search(tl):
        return None
    if re.search(r"\byes\b", tl) and "no" not in tl.split("yes")[-1]:
        return True
    return None


def _detect_repeat_occurrence(tbl_elem) -> bool | None:
    """
    Scan a table element for the 'repeat occurrence' row.
    Tries Wingdings symbol detection first, falls back to plain text Yes/No.
    """
    for tr in tbl_elem.findall(f"{{{_W}}}tr"):
        row_text = _elem_text(tr).lower()
        if "repeat occurrence" not in row_text and "repeat" not in row_text:
            continue

        # A checkbox symbol and its label word live in ADJACENT runs, not the same run
        # (confirmed live, 2026-08-25, against a real report: a Wingdings <w:sym> run
        # with no text, immediately followed by a separate text run carrying "Yes"/
        # "No") — the previous same-run pairing could never match this real structure,
        # so it always fell through to the plain-text fallback even when a genuine
        # checked checkbox was present. Track the most recently seen symbol and pair
        # it with the next run that actually carries a "yes"/"no" word.
        pending_checked: bool | None = None
        for r_elem in tr.findall(f".//{{{_W}}}r"):
            sym = r_elem.find(f"{{{_W}}}sym")
            if sym is not None:
                pending_checked = _sym_checked(sym)
                continue
            t_text = "".join(t.text or "" for t in r_elem.findall(f"{{{_W}}}t")).strip().lower()
            if not t_text or pending_checked is None:
                continue
            if t_text.startswith("yes"):
                if pending_checked:
                    return True
                pending_checked = None
            elif t_text.startswith("no"):
                if pending_checked:
                    return False
                pending_checked = None

        return _repeat_occurrence_from_text(row_text)

    return None


def _table_to_text(tbl_elem) -> str:
    """Flatten table rows to a readable string, skipping blank rows."""
    lines = []
    for tr in tbl_elem.findall(f"{{{_W}}}tr"):
        cells = [_elem_text(tc) for tc in tr.findall(f"{{{_W}}}tc")]
        line = " | ".join(c for c in cells if c)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _is_capa_action_table(tbl_elem) -> bool:
    """Distinguishes the real CAPA action table from other tables that also appear
    inside the CAPA section (Interim Control Plan, CAPA Extrapolation, signature
    block) — all of which previously got misparsed into capa_items indiscriminately,
    since every table encountered while current_section == "capa" was parsed as a
    CAPA action row regardless of its own header."""
    rows = tbl_elem.findall(f"{{{_W}}}tr")
    if not rows:
        return False
    header = _elem_text(rows[0]).lower()
    return (
        "capa description" in header
        or ("corrective action" in header and "preventive action" in header)
        or "capa action" in header
    )


def _table_to_capa_items(tbl_elem) -> list[dict]:
    """
    Parse the CAPA action table.
    Expected columns: Sr.No. | CAPA Description | Responsibility | Due Date
    Skips the header row.
    """
    rows = tbl_elem.findall(f"{{{_W}}}tr")
    items = []
    for tr in rows[1:]:
        cells = [_elem_text(tc) for tc in tr.findall(f"{{{_W}}}tc")]
        if len(cells) >= 2 and cells[1]:
            items.append({
                "description": cells[1],
                "responsibility": cells[2] if len(cells) > 2 else None,
                "due_date": cells[3] if len(cells) > 3 else None,
            })
    return items


# ── Section keyword matchers ───────────────────────────────────────────────────

def _is_rc_heading(text: str) -> bool:
    tl = text.lower()
    # Exclude investigation-findings headings that contain "root cause" but are not the conclusion
    if any(k in tl for k in ("investigation finding", "lead to determination", "determination of root")):
        return False
    return "root cause" in tl and any(k in tl for k in ("conclusion", "probable", "statement"))


def _is_capa_heading(text: str) -> bool:
    tl = text.lower()
    return (
        ("corrective" in tl and ("preventive" in tl or "capa" in tl))
        or ("remedial" in tl and "capa" in tl)
    )


def _is_impact_assessment_heading(text: str) -> bool:
    """Matches both the template's 'Impact Assessment & Conclusion (Batch disposition)'
    and a real completed report's shorter '8 Impact Assessment:' heading (confirmed live,
    2026-08-25 — the "conclusion"/"batch disposition" suffix isn't always present) — must
    NOT match Section 2's earlier 'Initial Impact Assessment & Immediate Actions' heading."""
    tl = text.lower()
    if "initial" in tl or "immediate action" in tl:
        return False
    return "impact assessment" in tl


def _is_correction_remedial_heading(text: str) -> bool:
    """Matches both the template's 'Correction and or Remedial action' and a real
    completed report's bare 'Remedial Action:' heading (confirmed live, 2026-08-25 — the
    "Correction" half isn't always present) — distinct from the CAPA heading (previously
    conflated: this heading also matched _is_capa_heading's old third clause, causing
    Correction/Remedial content to be misattributed as CAPA content)."""
    tl = text.lower()
    if "capa" in tl or "corrective" in tl:
        return False
    return ("correction" in tl and "remedial" in tl) or "remedial action" in tl


def _is_problem_statement_heading(text: str) -> bool:
    tl = text.lower()
    return (
        "problem statement" in tl
        or "problem description" in tl
        or "event description" in tl
    )


def _is_exec_summary_heading(text: str) -> bool:
    return "executive summary" in text.lower()


# Matches the batch-disposition/conclusion line within the Impact Assessment
# section (item 12 of that section — see impact_batch_disposition_system.txt)
# — best-effort guess (2026-09-01, unverified against a real uploaded
# document) based on how the generated RCI report itself renders this exact
# field verbatim as "Conclusion Statement: {conclusion}" (see
# rci_report_export.py's _fill_impact_assessment_batch_disposition), since
# the uploaded RC & CAPA document shares the same template lineage.
#
# CONFIRMED BUG, now tested against a real document (2026-09-10, per the
# user — record 507944's exported RCI report showed the same disposition
# sentence twice in a row): this regex deliberately matches BOTH "Conclusion:"
# and "Disposition:"/"Batch Disposition:" labels, since real templates use
# either wording. A document that has BOTH a "Disposition:" line AND a
# separate "Conclusion:" line restating the same decision — a real,
# plausible authoring pattern, not a malformed document — trips this: the
# FIRST label found sets collecting_impact_conclusion=True and strips its
# own label; the SECOND label line then matches the "already collecting"
# branch below instead (since that only checks the flag, not whether this
# line is itself a fresh label match), which appends it WITHOUT stripping
# the label — producing two near-duplicate sentences back to back.
# _dedupe_near_duplicate_lines below is the fix: applied once at the end,
# it drops any line that's a near-duplicate of one already kept, rather than
# redesigning the "capture everything after the first label" collection
# behavior itself (which real documents may still need, for a conclusion
# that spans more than one paragraph).
_IMPACT_CONCLUSION_LABEL_RE = re.compile(
    r"^\s*(?:conclusion(?:\s+statement)?|(?:batch\s+|product\s+)?disposition(?:\s+statement)?)\s*[:\-]",
    re.IGNORECASE,
)

_NEAR_DUPLICATE_THRESHOLD = 0.82


def _dedupe_near_duplicate_lines(text: str) -> str:
    """Drops any line that's a near-duplicate (fuzzy match, not just exact)
    of a line already kept — e.g. "...safety , batch shall be released..."
    vs "...safety and the batch shall be released..." are worded slightly
    differently but say the same thing. Keeps the FIRST occurrence (already
    label-stripped by the caller) and the original line order otherwise."""
    lines = [line for line in text.split("\n") if line.strip()]
    kept: list[str] = []
    for line in lines:
        normalized = line.strip().lower()
        if any(
            difflib.SequenceMatcher(None, normalized, kept_line.strip().lower()).ratio() >= _NEAR_DUPLICATE_THRESHOLD
            for kept_line in kept
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


# ── Main extractor ─────────────────────────────────────────────────────────────

def extract_rci_report_sections(docx_path) -> dict:
    """
    Extract the following from an RCI report docx:
      - problem_statement       (from executive summary)
      - rc_conclusion_text      (section 8 table text)
      - is_repeat_occurrence    (section 8 checkbox)
      - investigation_summary   (contributory factors brief summary)
      - impact_assessment_text  (section 7 "Impact Assessment & Conclusion (Batch disposition)")
      - impact_conclusion_text  (the "Conclusion:"/"Disposition:" line onward within section 7 —
                                  an additive subset of impact_assessment_text, not a replacement)
      - correction_remedial_text (section 9/10 "Correction and or Remedial action")
      - capa_overall_text       (free text before CAPA table in section 12, real CAPA-action table only)
      - capa_items              (rows from the real CAPA-action table only — see _is_capa_action_table)
    """
    doc = Document(str(docx_path))

    result = {
        "problem_statement": "",
        "rc_conclusion_text": "",
        "is_repeat_occurrence": None,
        "investigation_summary": "",
        "impact_assessment_text": "",
        "impact_conclusion_text": "",
        "correction_remedial_text": "",
        "capa_overall_text": "",
        "capa_items": [],
    }

    current_section = None   # "exec" | "rc" | "impact" | "correction_remedial" | "capa" | None
    collecting_ps = False
    collecting_rc_in_exec = False   # RC text embedded as body text in exec summary
    collecting_summary = False
    collecting_impact_conclusion = False   # from the "Conclusion:"/"Disposition:" line onward, within "impact"

    for elem in doc.element.body:
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        # ── Paragraph ──────────────────────────────────────────────────────────
        if tag == "p":
            text = _elem_text(elem)
            # Used for actually STORING content (never for heading/keyword matching
            # above, which stays on the full `text` including any italic runs) --
            # see _elem_text_excluding_italic's own docstring.
            content_text = _elem_text_excluding_italic(elem)
            is_h1 = _is_h1(elem)
            is_any_hdg = _is_any_heading(elem)

            # Only Heading 1 drives section transitions; Heading 2/3 treated as content
            if is_h1 and text:
                collecting_impact_conclusion = False
                if _is_exec_summary_heading(text):
                    current_section = "exec"
                elif _is_problem_statement_heading(text):
                    # The PS text may be inline in the heading (e.g. "Problem statement: On …")
                    after = re.sub(
                        r".*?(?:problem\s+(?:statement|description)|event\s+description)[:\s]*",
                        "", content_text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["problem_statement"] = after
                    else:
                        collecting_ps = True
                elif _is_rc_heading(text):
                    current_section = "rc"
                    collecting_ps = False
                elif _is_impact_assessment_heading(text):
                    current_section = "impact"
                elif _is_correction_remedial_heading(text):
                    current_section = "correction_remedial"
                    # The answer is sometimes embedded directly in the heading line itself
                    # with no separate body paragraph following (confirmed live, 2026-08-25:
                    # a real report's heading was literally "REMEDIAL ACTION: Not
                    # Applicable." with the very next paragraph already being the CAPA
                    # heading) — capture that inline content now, since it would otherwise
                    # be silently lost (H1 heading text is never collected as content).
                    after = re.sub(
                        r".*?(?:correction\s+and\s*/?\s*or\s+)?remedial\s+action[:\s]*",
                        "", content_text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["correction_remedial_text"] += after + "\n"
                elif _is_capa_heading(text):
                    current_section = "capa"
                elif current_section in ("rc", "impact", "correction_remedial", "capa"):
                    # Any other H1 heading (Risk Assessment, CAPA Effectiveness Check Plan,
                    # List of Annexures, Approval, etc.) signals we've moved past whichever
                    # of these four sections we were collecting.
                    current_section = None
                continue   # never collect H1 text as content

            # Sub-headings (H2/H3) inside a section — treat as plain text content
            if is_any_hdg and not is_h1:
                if not text:
                    continue
                # fall through to content collection below (no `continue` here)

            if not text:
                continue

            # Collect problem statement from the paragraph after a PS heading
            if collecting_ps and not result["problem_statement"]:
                result["problem_statement"] = content_text
                collecting_ps = False
                continue

            # Detect "Problem statement:" as a plain body paragraph (task report format)
            if current_section is None and not result["problem_statement"]:
                tl = text.lower()
                if "problem statement" in tl or "problem description" in tl:
                    after = re.sub(
                        r".*?problem\s+(?:statement|description)[:\s]*",
                        "", content_text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["problem_statement"] = after
                    else:
                        collecting_ps = True
                    continue

            # Executive summary content
            if current_section == "exec":
                tl = text.lower()

                # Sub-section labels that reset collection state
                exec_sublabels = (
                    "immediate containment", "impact assessment",
                    "conclusion statement", "scope",
                )
                if any(k in tl for k in exec_sublabels):
                    collecting_rc_in_exec = False
                    collecting_summary = False

                if "problem statement" in tl or "problem description" in tl:
                    after = re.sub(
                        r".*?problem\s+(?:statement|description)[:\s*\d.]*",
                        "", content_text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["problem_statement"] = after
                    else:
                        collecting_ps = True
                    continue
                if "event description" in tl and not result["problem_statement"]:
                    after = re.sub(
                        r".*?event\s+description[:\s]*", "", content_text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["problem_statement"] = after
                    else:
                        collecting_ps = True
                    continue
                if collecting_ps and not result["problem_statement"]:
                    result["problem_statement"] = content_text
                    collecting_ps = False
                    continue
                # RC conclusion embedded as body text in exec summary
                if re.search(r"determination of root cause|root cause\s*/\s*probable", tl):
                    collecting_rc_in_exec = True
                    continue
                if collecting_rc_in_exec:
                    if content_text:
                        result["rc_conclusion_text"] += content_text + "\n"
                    continue
                if "brief summary" in tl or "contributory factor" in tl:
                    collecting_summary = True
                    continue
                if collecting_summary and content_text:
                    result["investigation_summary"] += content_text + "\n"

            # RC conclusion content
            elif current_section == "rc":
                tl = text.lower()
                if "repeat occurrence" in tl:
                    ri = _repeat_occurrence_from_text(tl)
                    if ri is not None:
                        result["is_repeat_occurrence"] = ri
                elif content_text:
                    result["rc_conclusion_text"] += content_text + "\n"

            # Impact Assessment content (including H2/H3 sub-heading text)
            elif current_section == "impact":
                if content_text:
                    result["impact_assessment_text"] += content_text + "\n"
                # The conclusion/batch-disposition line onward — captured ADDITIVELY
                # into its own field (not removed from impact_assessment_text above),
                # same principle as reference_number alongside status in the
                # correction/remedial prompt: a duplicate for structured use, not an
                # extraction that empties the broader blob.
                if not collecting_impact_conclusion and _IMPACT_CONCLUSION_LABEL_RE.match(content_text):
                    collecting_impact_conclusion = True
                    after = _IMPACT_CONCLUSION_LABEL_RE.sub("", content_text, count=1).strip()
                    if after:
                        result["impact_conclusion_text"] += after + "\n"
                elif collecting_impact_conclusion and content_text:
                    result["impact_conclusion_text"] += content_text + "\n"

            # Correction/Remedial Action content (including H2/H3 sub-heading text)
            elif current_section == "correction_remedial":
                if content_text:
                    result["correction_remedial_text"] += content_text + "\n"

            # CAPA content (including H2/H3 sub-heading text)
            elif current_section == "capa":
                if content_text:
                    result["capa_overall_text"] += content_text + "\n"

        # ── Table ──────────────────────────────────────────────────────────────
        elif tag == "tbl":
            if current_section == "rc":
                for tr in elem.findall(f"{{{_W}}}tr"):
                    row_text = _elem_text(tr)
                    tl = row_text.lower()
                    if "repeat occurrence" in tl:
                        ri = _detect_repeat_occurrence(elem)
                        if ri is not None:
                            result["is_repeat_occurrence"] = ri
                    elif "root cause" in tl and "conclusion" in tl:
                        continue  # skip header row
                    elif re.search(r"^no recurring|^no recurrence", tl):
                        continue  # skip recurrence verdict row
                    elif row_text:
                        result["rc_conclusion_text"] += row_text + "\n"

            elif current_section == "exec" and collecting_summary:
                result["investigation_summary"] += _table_to_text(elem) + "\n"

            elif current_section == "impact":
                table_text = _table_to_text(elem)
                result["impact_assessment_text"] += table_text + "\n"
                if not collecting_impact_conclusion and _IMPACT_CONCLUSION_LABEL_RE.match(table_text):
                    collecting_impact_conclusion = True
                    after = _IMPACT_CONCLUSION_LABEL_RE.sub("", table_text, count=1).strip()
                    if after:
                        result["impact_conclusion_text"] += after + "\n"
                elif collecting_impact_conclusion:
                    result["impact_conclusion_text"] += table_text + "\n"

            elif current_section == "correction_remedial":
                result["correction_remedial_text"] += _table_to_text(elem) + "\n"

            elif current_section == "capa":
                if _is_capa_action_table(elem):
                    items = _table_to_capa_items(elem)
                    if items:
                        result["capa_items"].extend(items)
                else:
                    # Interim Control / Extrapolation / signature tables — keep as
                    # supplementary text rather than misparsing into capa_items.
                    result["capa_overall_text"] += _table_to_text(elem) + "\n"

    # Tidy up
    result["rc_conclusion_text"] = result["rc_conclusion_text"].strip()
    result["impact_assessment_text"] = result["impact_assessment_text"].strip()
    result["impact_conclusion_text"] = _dedupe_near_duplicate_lines(result["impact_conclusion_text"].strip())
    result["correction_remedial_text"] = result["correction_remedial_text"].strip()
    result["capa_overall_text"] = result["capa_overall_text"].strip()
    result["investigation_summary"] = result["investigation_summary"].strip()
    result["problem_statement"] = result["problem_statement"].strip()

    return result


def extract_full_document_text(docx_path) -> str:
    """
    Convert a docx to clean markdown text for full-document LLM critique.
    Strips base64-encoded images to keep the payload lean.
    """
    raw = _md.convert(str(docx_path)).text_content
    text = _BASE64_RE.sub("", raw)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
