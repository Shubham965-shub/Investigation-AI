"""
Extract sections 8 (RC Conclusion) and 12 (CAPA) from a completed RCI report docx.

The RCI report is a free-form Word document structured with headings. This module
scans body elements in document order to locate and extract the relevant sections.
"""

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


def _detect_repeat_occurrence(tbl_elem) -> bool | None:
    """
    Scan a table element for the 'repeat occurrence' row.
    Tries Wingdings symbol detection first, falls back to plain text Yes/No.
    """
    for tr in tbl_elem.findall(f"{{{_W}}}tr"):
        row_text = _elem_text(tr).lower()
        if "repeat occurrence" not in row_text and "repeat" not in row_text:
            continue

        # Walk runs looking for symbol+label pairs
        checked_labels = []
        for r_elem in tr.findall(f".//{{{_W}}}r"):
            sym = r_elem.find(f"{{{_W}}}sym")
            is_checked = _sym_checked(sym) if sym is not None else None
            t_text = "".join(t.text or "" for t in r_elem.findall(f"{{{_W}}}t")).strip().lower()
            if t_text and is_checked is not None and is_checked:
                checked_labels.append(t_text)

        if "yes" in checked_labels:
            return True
        if "no" in checked_labels:
            return False

        # Plain-text fallback
        if re.search(r"no recurring|no recurrence|not.*repeat", row_text):
            return False
        if re.search(r"\byes\b", row_text) and "no" not in row_text.split("yes")[-1]:
            return True
        return False

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
        or ("correction" in tl and "remedial" in tl)   # "Correction and or Remedial action"
    )


def _is_problem_statement_heading(text: str) -> bool:
    tl = text.lower()
    return (
        "problem statement" in tl
        or "problem description" in tl
        or "event description" in tl
    )


def _is_exec_summary_heading(text: str) -> bool:
    return "executive summary" in text.lower()


def _is_post_rc_heading(text: str) -> bool:
    """H1 headings that signal we've moved past the RC conclusion section."""
    tl = text.lower()
    return any(k in tl for k in ("impact assessment", "risk assessment", "remedial action"))


def _is_post_capa_heading(text: str) -> bool:
    """H1 headings that signal we've moved past the CAPA section."""
    tl = text.lower()
    return any(k in tl for k in (
        "effectiveness check", "list of annexure", "approval",
        "conclusion statement", "description of event",
    ))


# ── Main extractor ─────────────────────────────────────────────────────────────

def extract_rci_report_sections(docx_path) -> dict:
    """
    Extract the following from an RCI report docx:
      - problem_statement       (from executive summary)
      - rc_conclusion_text      (section 8 table text)
      - is_repeat_occurrence    (section 8 checkbox)
      - investigation_summary   (contributory factors brief summary)
      - capa_overall_text       (free text before CAPA table in section 12)
      - capa_items              (rows from section 12 table)
    """
    doc = Document(str(docx_path))

    result = {
        "problem_statement": "",
        "rc_conclusion_text": "",
        "is_repeat_occurrence": None,
        "investigation_summary": "",
        "capa_overall_text": "",
        "capa_items": [],
    }

    current_section = None   # "exec" | "rc" | "capa" | None
    collecting_ps = False
    collecting_rc_in_exec = False   # RC text embedded as body text in exec summary
    collecting_summary = False

    for elem in doc.element.body:
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        # ── Paragraph ──────────────────────────────────────────────────────────
        if tag == "p":
            text = _elem_text(elem)
            is_h1 = _is_h1(elem)
            is_any_hdg = _is_any_heading(elem)

            # Only Heading 1 drives section transitions; Heading 2/3 treated as content
            if is_h1 and text:
                if _is_exec_summary_heading(text):
                    current_section = "exec"
                elif _is_problem_statement_heading(text):
                    # The PS text may be inline in the heading (e.g. "Problem statement: On …")
                    after = re.sub(
                        r".*?(?:problem\s+(?:statement|description)|event\s+description)[:\s]*",
                        "", text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["problem_statement"] = after
                    else:
                        collecting_ps = True
                elif _is_rc_heading(text):
                    current_section = "rc"
                    collecting_ps = False
                elif _is_capa_heading(text):
                    current_section = "capa"
                elif _is_post_rc_heading(text) and current_section == "rc":
                    current_section = None
                elif _is_post_capa_heading(text) and current_section == "capa":
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
                result["problem_statement"] = text
                collecting_ps = False
                continue

            # Detect "Problem statement:" as a plain body paragraph (task report format)
            if current_section is None and not result["problem_statement"]:
                tl = text.lower()
                if "problem statement" in tl or "problem description" in tl:
                    after = re.sub(
                        r".*?problem\s+(?:statement|description)[:\s]*",
                        "", text, flags=re.IGNORECASE
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
                        "", text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["problem_statement"] = after
                    else:
                        collecting_ps = True
                    continue
                if "event description" in tl and not result["problem_statement"]:
                    after = re.sub(
                        r".*?event\s+description[:\s]*", "", text, flags=re.IGNORECASE
                    ).strip()
                    if after:
                        result["problem_statement"] = after
                    else:
                        collecting_ps = True
                    continue
                if collecting_ps and not result["problem_statement"]:
                    result["problem_statement"] = text
                    collecting_ps = False
                    continue
                # RC conclusion embedded as body text in exec summary
                if re.search(r"determination of root cause|root cause\s*/\s*probable", tl):
                    collecting_rc_in_exec = True
                    continue
                if collecting_rc_in_exec:
                    result["rc_conclusion_text"] += text + "\n"
                    continue
                if "brief summary" in tl or "contributory factor" in tl:
                    collecting_summary = True
                    continue
                if collecting_summary:
                    result["investigation_summary"] += text + "\n"

            # RC conclusion content
            elif current_section == "rc":
                tl = text.lower()
                if "repeat occurrence" in tl:
                    result["is_repeat_occurrence"] = "yes" in tl and "no" not in tl.split("yes")[-1]
                else:
                    result["rc_conclusion_text"] += text + "\n"

            # CAPA content (including H2/H3 sub-heading text)
            elif current_section == "capa":
                result["capa_overall_text"] += text + "\n"

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

            elif current_section == "capa":
                items = _table_to_capa_items(elem)
                if items:
                    result["capa_items"].extend(items)

    # Tidy up
    result["rc_conclusion_text"] = result["rc_conclusion_text"].strip()
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
