import re
import json
import pandas as pd

from pathlib import Path
from docx import Document
from docx.table import Table, _Cell
from typing import Dict, List, Tuple, Any, Optional
from hashlib import md5

# ----------------------
# 2.2 RCI Plan Sign-off
# ----------------------

def find_section_rows(table: Table, section_key: str, all_keys=("1.1", "1.2", "2.1", "2.2")) -> Tuple[Optional[int], Optional[int]]:
    """
    Find the [start, end) row indices for a given section label, e.g., '1.1'.
    We look for the label in the first cell of a row and stop at the next section label.
    """
    rows = table.rows
    start = end = None
    for i, row in enumerate(rows):
        first = norm_space(row.cells[0].text)
        if first.startswith(section_key):
            start = i
            break
    if start is None:
        return None, None

    # Find index of the next section marker
    other_keys = [k for k in all_keys if k != section_key]
    for j in range(start + 1, len(rows)):
        first_j = norm_space(rows[j].cells[0].text)
        if any(first_j.startswith(k) for k in other_keys):
            end = j
            break
    if end is None:
        end = len(rows)
    return start, end

def extract_signoff(main_table: Table) -> Dict[str, Optional[str]]:
    s, e = find_section_rows(main_table, "2.2")
    if s is None:
        raise RuntimeError("Section 2.2 not found.")

    signoff = {"Investigator": None, "Task Owner": None, "CFT": None, "SIT Lead": None, "QA": None}
    roles = ["investigator", "task owner", "cft", "sit lead", "qa"]

    for i in range(s, e):
        row = main_table.rows[i]
        headers = [norm_space(c.text) for c in row.cells]
        header_l = [h.lower() for h in headers]

        # Identify a row listing roles
        if any("investigator" in h for h in header_l) and any("qa" in h for h in header_l):
            # Next row should contain names
            if i + 1 < e:
                values = [norm_space(c.text) for c in main_table.rows[i + 1].cells]
                # Align by role names in headers
                # Use positional mapping (zip) + fuzzy role name detection
                for h, v in zip(headers, values):
                    hl = h.lower()
                    for r in roles:
                        if r in hl:
                            key = r.title() if r != "qa" else "QA"
                            signoff[key] = v or None
                            break
            break

    return signoff

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def xml_fingerprint(element) -> str:
    xml_text = "".join(str(element.xml).split())
    return md5(xml_text.encode("utf-8")).hexdigest()


# Normalize font names to a stable key (e.g., "wingdings 2")
def norm_font(name: str | None) -> str:
    return (name or "").strip().lower()


SYM_MAP = {
    ("wingdings",   "F0A8"): "☐",  # empty box (if used elsewhere)
    ("wingdings",   "F052"): "☑",  # checked box (earlier case)
    ("wingdings",   "F0FE"): "☑",  # plain check mark (seen in your snippet before "Yes")
    ("wingdings 2", "F054"): "☒",  # boxed cross
}

def extract_sym_chars_from_run_xml(run) -> list[str]:
    """
    Return a list of symbols found under this run by scanning run._r for <w:sym>.
    Uses (font, char) mapping with fallbacks.
    """
    syms = []
    r_el = run._r  # CT_R

    for el in r_el.iter():
        if el.tag.endswith('sym'):
            font = (
                el.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}font")
                or el.get("w:font") or ""
            )
            val = (
                el.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}char")
                or el.get("w:char") or ""
            )
            fkey = norm_font(font)
            vkey = val.strip().upper()

            if not vkey:
                continue

            # 1) Exact (font, char) match
            mapped = SYM_MAP.get((fkey, vkey))
            if mapped is not None:
                syms.append(mapped)
                continue

            try:
                syms.append(chr(int(vkey, 16)))
            except Exception:
                syms.append(f"[SYM:{font}:{vkey}]")
    return syms


# -------- CONTENT-CONTROL CHECKBOXES (w14:checkbox) --------
def read_checkbox_state_from_sdt(tc_element) -> list[str]:
    """
    Read content-control checkboxes (w14:checkbox). Emits '☑' or '☐'.
    No namespaces kwarg; python-docx registers them.
    """
    
    
    out_path = Path("tc_element.txt")

    # inside your loop:
    with out_path.open("a", encoding="utf-8") as f:   # "a" = append
        f.write(tc_element.xml)


    checks: list[str] = []
    for sdt in tc_element.xpath(".//w:sdt"):
        if not sdt.xpath(".//w:sdtPr/w14:checkbox"):
            continue
        checked_nodes = sdt.xpath(".//w:sdtPr/w14:checkbox/w14:checked")
        if checked_nodes:
            val = checked_nodes[0].get("{http://schemas.microsoft.com/office/word/2010/wordml}val")
            checks.append("☑" if str(val).lower() in ("1", "true", "on") else "☐")

    # Broader fallback (just in case)
    if not checks:
        for sdt in tc_element.xpath(".//*[local-name()='sdt']"):
            chk = sdt.xpath(".//*[local-name()='checkbox']/*[local-name()='checked']")
            if chk:
                val = chk[0].get("{http://schemas.microsoft.com/office/word/2010/wordml}val") or \
                      chk[0].get("w14:val") or chk[0].get("val")
                checks.append("☑" if str(val).lower() in ("1", "true", "on") else "☐")
    return checks

SENTINEL = "\u241E"

# -------- Rich cell text: text + <w:sym> + content control --------
def rich_cell_text(cell: _Cell, sentinel = SENTINEL) -> str:
    parts = []

    # 1) From runs: collect normal text and any <w:sym> symbols we find in run XML
    for p in cell.paragraphs:
        run_parts = []
        for run in p.runs:
            # Symbols from <w:sym> (can return multiple if present)
            syms = extract_sym_chars_from_run_xml(run)
            if syms:
                run_parts.extend(syms)

            # Normal run text
            if run.text:
                run_parts.append(run.text)

        if not run_parts and p.text:
            run_parts.append(p.text)

        if run_parts:
            parts.append(norm_space("".join(run_parts)))

    # 2) Content-control checkboxes (w14:checkbox)
    checks = read_checkbox_state_from_sdt(cell._tc)
    if checks:
        parts.extend(checks)

    return sentinel.join(filter(None, parts))

def table_to_df_rich(table: Table) -> pd.DataFrame:
    return pd.DataFrame([[rich_cell_text(c) for c in row.cells] for row in table.rows])

def xml_fingerprint(element) -> str:
    """
    Deterministic fingerprint for a python-docx XML element (e.g., CT_Tbl, CT_Tc).
    Uses an md5 hash of the element's XML string. Extremely low collision risk in practice.
    """
    # element.xml is a bytes/string representation of the element and all descendants
    # In python-docx it's a str (XML). Normalize whitespace just in case.
    xml_text = "".join(str(element.xml).split())
    return md5(xml_text.encode("utf-8")).hexdigest()

def all_tables_to_json(all_tables: dict) -> dict:
    """
    Convert dict[str, DataFrame] -> JSON-serializable dict
    """
    json_obj = {}
    for table_name, df in all_tables.items():
        json_obj[table_name] = df.fillna("").to_dict(orient="records")
    return json_obj






def walk_tables_dedup_by_xml(table: Table,
                             prefix: str = "Table",
                             seen_tbl=None,
                             seen_tc=None):
    """
    Recursively walk a table and its nested tables and collect DataFrames,
    while deduplicating by **XML content signature** (hash) of tables and cells.
    Returns: dict[name -> DataFrame]
    """
    if seen_tbl is None:
        seen_tbl = set()
    if seen_tc is None:
        seen_tc = set()

    out = {}

    # ---- Dedup the current table by its XML ----
    tbl_sig = xml_fingerprint(table._element)
    if tbl_sig in seen_tbl:
        return out
    seen_tbl.add(tbl_sig)

    # Store the current table
    out[prefix] = table_to_df_rich(table)

    # ---- Explore nested tables - dedup each cell by XML too ----
    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            tc_sig = xml_fingerprint(cell._tc)
            if tc_sig in seen_tc:
                continue
            seen_tc.add(tc_sig)

            # Recurse into nested tables within this cell
            if cell.tables:
                for i, nt in enumerate(cell.tables, start=1):
                    sub_name = f"{prefix}_r{r_idx}c{c_idx}_sub{i}"
                    out.update(
                        walk_tables_dedup_by_xml(
                            nt,
                            prefix=sub_name,
                            seen_tbl=seen_tbl,
                            seen_tc=seen_tc
                        )
                    )
    return out


def df_to_kv_from_header_and_kv_rows(df: pd.DataFrame) -> dict:
    """
    Assumes:
      - First row is header names
      - Second row is main values
      - Remaining rows are 'key in col0' + 'value in col1'
    Returns a single dict of fields.
    """
    if df.empty:
        return {}

    # Convert all to strings (so we can strip safely), preserve NaN as ""
    sdf = df.fillna("").astype(str)

    headers = sdf.iloc[0].tolist()
    values  = sdf.iloc[1].tolist() if len(sdf) >= 2 else []

    out = {}
    for h, v in zip(headers, values):
        h = h.strip()
        if h:
            out[h] = v.strip()

    # Remaining rows: col0 -> col1 pairs
    for i in range(2, len(sdf)):
        key = sdf.iat[i, 0].strip() if sdf.shape[1] >= 1 else ""
        val = sdf.iat[i, 1].strip() if sdf.shape[1] >= 2 else ""
        if key:
            if key not in out or val:
                out[key] = val

    return out




def parse_choices(cell_text: str):
    """
    Turn strings like '☑ Yes ☒ No', '☒Yes ☑No', '☑ Yes ☒ No ☒N/A'
    into [{label, selected}, ...] with normalized labels.
    """
    if not cell_text:
        return []

    s = cell_text.strip()
    # capture variants with and without spaces: ('☑','Yes'), ('☒','N/A'), etc.
    tokens = re.findall(r'(☑|☒)\s*([A-Za-z]+(?:/?[A-Za-z]+)?)', s)
    # Deduplicate by label; True wins if seen multiple times
    norm_map = {}
    for mark, label in tokens:
        raw = label.strip()
        upper = raw.upper().replace(" ", "")
        if upper in ("YES",):
            key = "Yes"
        elif upper in ("NO",):
            key = "No"
        elif upper in ("NA", "N/A", "N\\A"):
            key = "N/A"
        else:
            key = raw.title()
        selected = (mark == "☑")
        norm_map[key] = norm_map.get(key, False) or selected

    # order common labels first; append any extras
    order = ["Yes", "No", "N/A"]
    out = []
    seen = set()
    for k in order:
        if k in norm_map:
            out.append({"label": k, "selected": norm_map[k]})
            seen.add(k)
    for k, v in norm_map.items():
        if k not in seen:
            out.append({"label": k, "selected": v})
    return out

def prerequisites_rows_to_fe_json(table_rows: List[Dict[str, Any]], title: str):
    """
    Convert the DOCX-derived rows (string-indexed columns '0','1','2','3')
    into FE-friendly JSON that preserves header and provides a header->key mapping.
    """
    if not table_rows:
        return {"title": title, "header": [], "columnsMap": {}, "items": []}

    # Header row (exactly as in the doc)
    header_row = table_rows[0]
    # maintain order by column index
    header = [header_row.get(str(i), "") for i in range(len(header_row))]

    # Build a stable mapping of logical keys to exact header captions
    # We assume column positions: 0->sr, 1->question, 2->options, 3->explanation

    columns_map = {
        "sr": header[0] if len(header) > 0 else "",
        "question": header[1] if len(header) > 1 else "",
        "options": header[2] if len(header) > 2 else "Yes or No",
        "explanation": header[3] if len(header) > 3 else "",
    }

    items = []
    for row in table_rows[1:]:
        sr   = (row.get("0") or "").strip()
        ques = (row.get("1") or "").strip()
        raw  = (row.get("2") or "").strip()
        expl = (row.get("3") or "").strip()

        choices = parse_choices(raw)

        items.append({
            "sr": sr,
            "question": ques,
            "optionsRaw": raw,
            "choices": choices,
            "explanation": expl
        })

    return {
        "title": title,
        "header": header,
        "columnsMap": columns_map,
        "items": items
    }


# Glyphs that we consider "checked"
CHECKED_GLYPHS = {"☑", "✓", "\uf052", ""}  # include the Wingdings PUA '' (U+F052)
# Glyphs that we consider "unchecked" (for reference)
UNCHECKED_GLYPHS = {"☐", "☒"}

def is_checked(mark: str) -> bool:
    """Return True if the cell contains any recognized 'checked' glyph."""
    if not mark:
        return False
    # Sometimes the cell could contain multiple characters/spaces
    for ch in mark:
        if ch in CHECKED_GLYPHS:
            return True
    # Fallback: if the whole string equals a checked glyph
    return mark.strip() in CHECKED_GLYPHS

def task_assignment_rows_to_fe_json(
    table_rows: List[Dict[str, Any]],
    title: str = "Identification of Investigation Team Members & Task Assignment"
) -> Dict[str, Any]:
    """
    Convert the DOCX-derived rows (columns '0','1','2','3') into a JSON structure that:
      - preserves the original header (headerRaw)
      - offers a 'displayHeader' with the first column name mapped to 'Select'
      - provides columnsMap (semantic key -> original header)
      - returns items with selection + mandatory flags
    Expected column positions:
      col0 -> Select mark (☐ / ☑ / )
      col1 -> Task (may start with '$' for mandatory)
      col2 -> Status (e.g., 'Verified', 'Not Applicable', 'Shall be verified')
      col3 -> Responsible Person
    """
    if not table_rows:
        return {
            "title": title,
            "headerRaw": [],
            "displayHeader": [],
            "columnsMap": {},
            "items": [],
            "mandatorySummary": {"totalMandatory": 0, "selectedMandatory": 0, "allMandatorySelected": True}
        }

    # --- Preserve original header as-is
    header_row = table_rows[0]
    # Keep original order 0..n
    header_raw = [header_row.get(str(i), "") for i in range(len(header_row))]

    # --- Provide a "displayHeader" where the first header becomes 'Select'
    display_header = header_raw[:]  # shallow copy
    if display_header:
        display_header[0] = "Select"  # map the first “Tick √ (as applicable)” to 'Select'

    # --- Provide a mapping from semantic keys -> original header captions
    # We keep original header text (even if it's odd) so FE can show tooltips or source captions.
    columns_map = {
        "select": header_raw[0] if len(header_raw) > 0 else "",
        "task": header_raw[1] if len(header_raw) > 1 else "",
        "status": header_raw[2] if len(header_raw) > 2 else "",
        "responsible": header_raw[3] if len(header_raw) > 3 else "",
    }

    # --- Build items
    items = []
    total_mandatory = 0
    selected_mandatory = 0

    for row in table_rows[1:]:
        # Raw fields
        raw_select = (row.get("0") or "").strip()
        raw_task   = (row.get("1") or "").strip()
        status     = (row.get("2") or "").strip()
        responsible= (row.get("3") or "").strip()

        # Selection
        selected = is_checked(raw_select)

        # Mandatory detection: leading '$'
        mandatory = raw_task.lstrip().startswith("$")
        # Clean the leading '$' for display
        task = raw_task.lstrip().removeprefix("$").strip()

        item = {
            "select": selected,
            "task": task,
            "status": status,
            "responsible": responsible,
            "mandatory": mandatory
        }

        # Only include the mandatorySelected flag for mandatory rows
        if mandatory:
            item["mandatorySelected"] = selected
            total_mandatory += 1
            if selected:
                selected_mandatory += 1

        items.append(item)

    summary = {
        "totalMandatory": total_mandatory,
        "selectedMandatory": selected_mandatory,
        "allMandatorySelected": (selected_mandatory == total_mandatory)
    }

    return {
        "title": title,
        "headerRaw": header_raw,        # original header texts (unaltered)
        "displayHeader": display_header,# first header mapped to "Select" for UI
        "columnsMap": columns_map,      # semantic key -> original header
        "items": items,                 # parsed rows with selection/mandatory flags
        "mandatorySummary": summary     # optional aggregate to quickly validate
    }



# -----------------------------
# Configuration & Regexes
# -----------------------------

# Matches simple section codes in col 0 like "1.1", "2.1", etc.
SECTION_ID_RE = re.compile(r"^\s*\d+\.\d+\s*$", re.I)

# Problem-statement labels that might appear at different sites
PROBLEM_LABELS = [
    "Problem statement",
    # Add site variants as needed:
    "Problem description",
    "Issue statement",
    "Event narrative",
]

# -----------------------------
# Small Utilities
# -----------------------------

def longest_non_empty(values: List[str]) -> str:
    """
    Return the longest non-empty string from a list.
    Helps choose a single representative narrative among repeated merged cells.
    """
    clean = [v.strip() for v in values if isinstance(v, str) and v and v.strip()]
    return max(clean, key=len) if clean else ""

def cleanup_label_prefix(text: str, label: str) -> (str, str):
    """
    If text starts with '<label>:' or '<label> /', strip it and return (label, cleaned_text).
    Otherwise return ("", trimmed_text).
    """
    if not text:
        return "", ""
    # e.g., "Problem statement: <content>"
    m = re.match(rf"^\s*{re.escape(label)}\s*[:：/~-]?\s*", text, flags=re.I)
    if m:
        return label, text[m.end():].strip()
    return "", text.strip()

def split_problem_items(text: str) -> List[str]:
    """
    Split narrative into discrete items.
    Handles:
      - earlier ' / ' joiner,
      - common bullet glyphs ( • ▪ ‣),
      - explicit line breaks,
      - trailing punctuation (ensures . ! ?).
    """
    if not text:
        return []

    s = text
    # Normalize obvious separators to newlines
    s = s.replace(SENTINEL, "\n")
    s = s.replace("", "\n").replace("•", "\n").replace("▪", "\n").replace("‣", "\n")
    # Collapse whitespace around newlines
    s = re.sub(r"\s*\n\s*", "\n", s)

    parts = [p.strip(" \t-–—") for p in s.split("\n")]
    out, seen = [], set()

    for p in parts:
        if not p:
            continue
        # Avoid duplicates (merged-cell echoes)
        if p in seen:
            continue
        seen.add(p)
        # Ensure terminal punctuation for nicer FE rendering
        if p and p[-1] not in ".!?":
            p = p + "."
        out.append(p)

    return out

# -----------------------------
# Label-first Problem Extractor
# -----------------------------

def extract_problem_statement_from_table1_block(
    table1_rows: List[Dict[str, Any]],
    row_vals_fn,
    start_index: int,
    ncols: int = 6,
    labels: List[str] = PROBLEM_LABELS,
    lookahead: int = 10
) -> Optional[Dict[str, Any]]:
    """
    Starting from the section '1.1' row index, scan a small window of rows.
    Prefer a cell that *starts* with one of the provided labels (label-first).
    If none is found, fall back to the longest non-empty text among cols 1..(ncols-1).

    Returns a dict or None:
      {
        "label": <label_used>,
        "cleaned": <text with label removed>,
        "raw": <original cell text>,
        "sourceRow": <row_index>
      }
    """

    end = min(len(table1_rows), start_index + lookahead + 1)

    # 1) Label-first scan
    for k in range(start_index, end):
        vals = row_vals_fn(table1_rows[k])
        c0 = (vals[0] or "").strip()
        # Stop if a new section starts (but allow k == start_index)
        if k > start_index and SECTION_ID_RE.match(c0):
            break

        for txt in vals[1:]:  # scan only columns 1..n-1
            if not txt:
                continue
            for lab in labels:
                found_label, cleaned = cleanup_label_prefix(txt, label=lab)
                if found_label:
                    return {
                        "label": found_label,
                        "cleaned": cleaned,
                        "raw": txt,
                        "sourceRow": k
                    }

    # 2) Fallback: choose the longest non-empty candidate among cols 1..(ncols-1)
    for k in range(start_index, end):
        vals = row_vals_fn(table1_rows[k])
        c0 = (vals[0] or "").strip()
        if k > start_index and SECTION_ID_RE.match(c0):
            break
        candidate = longest_non_empty(vals[1:])
        if candidate:
            # Try to remove label if included without punctuation; else keep as-is
            for lab in labels:
                _, cleaned = cleanup_label_prefix(candidate, label=lab)
                if cleaned and cleaned != candidate:
                    return {
                        "label": lab,
                        "cleaned": cleaned,
                        "raw": candidate,
                        "sourceRow": k
                    }
            return {
                "label": labels[0],  # default label name
                "cleaned": candidate.strip(),
                "raw": candidate,
                "sourceRow": k
            }

    return None

# -----------------------------
# Main Transformer
# -----------------------------

def parse_table1_into_sections(
    table1_rows: List[Dict[str, Any]],
    *,
    rci_details: Optional[Dict[str, str]] = None,
    prerequisites_json: Optional[Dict[str, Any]] = None,
    task_assignment_json: Optional[Dict[str, Any]] = None,
    signoff_kv: Optional[Dict[str, str]] = None,
    ncols: int = 6
) -> Dict[str, Any]:
    """
    Convert the raw 'Table1' rows (list of dicts like {"0": "...", "1": "...", ...})
    into a structured payload that FE can render section-by-section.

    Output structure:
    {
      "sections": [
        {
          "number": "1.1",
          "title": "Event Description",
          "instructions": [...],
          "problemStatement": { "label": "...", "items": [...] },
          "rciDetails": {...}
        },
        {
          "number": "1.2",
          "title": "...",
          "instructions": [...],
          "prerequisites": {...}
        },
        {
          "number": "2.1",
          "title": "...",
          "instructions": [...],
          "taskAssignment": {...}
        },
        {
          "number": "2.2",
          "title": "...",
          "signoff": {...}
        }
      ]
    }
    """

    sections: List[Dict[str, Any]] = []
    i = 0

    def row_vals(row: Dict[str, Any]) -> List[str]:
        # Return a fixed-width list of col texts; missing columns become ""
        return [(row.get(str(c)) or "").strip() for c in range(ncols)]

    while i < len(table1_rows):
        current = table1_rows[i]
        cells = row_vals(current)
        c0 = cells[0]

        # Detect a section header row like '1.1'
        if SECTION_ID_RE.match(c0):
            number = c0
            title = cells[1]  # section title is in col 1 in your docs
            section: Dict[str, Any] = {"number": number, "title": title}

            # Collect instruction rows between this section and the next section
            instr: List[str] = []
            j = i + 1
            while j < len(table1_rows):
                nxt = row_vals(table1_rows[j])
                nxt0 = nxt[0]

                # Stop when the next section begins
                if SECTION_ID_RE.match(nxt0):
                    break

                # If the entire row is empty, skip it
                if not any(nxt):
                    j += 1
                    continue

                # Take meaningful text primarily from col 0 for instructions
                if nxt0:
                    # For lines like "A / B / C", split to separate bullets
                    parts = [p.strip() for p in nxt0.split("/") if p.strip()]
                    for p in parts:
                        if p not in instr:
                            instr.append(p)

                j += 1

            if instr:
                section["instructions"] = instr

            # SPECIAL: Section 1.1 — extract Problem statement (label-first with fallback)
            if number == "1.1":
                found = extract_problem_statement_from_table1_block(
                    table1_rows=table1_rows,
                    row_vals_fn=row_vals,
                    start_index=i,
                    ncols=ncols,
                    labels=PROBLEM_LABELS,
                    lookahead=10
                )
                if found and (found["cleaned"] or found["raw"]):
                    items = split_problem_items(found["cleaned"] or found["raw"])
                    section["problemStatement"] = {
                        "label": found["label"],
                        "items": items
                    }

                # Attach RCI header details if provided
                if rci_details:
                    section["rciDetails"] = rci_details

            # Section 1.2 — attach prerequisites JSON if provided
            if number == "1.2" and prerequisites_json:
                section["prerequisites"] = prerequisites_json

            # Section 2.1 — attach task assignment JSON if provided
            if number == "2.1" and task_assignment_json:
                section["taskAssignment"] = task_assignment_json

            # Section 2.2 — attach sign-off KV if provided
            if number == "2.2" and signoff_kv:
                section["signoff"] = signoff_kv

            sections.append(section)
            i = j
            continue

        # Not a section header row → move on
        i += 1

    return {"sections": sections}





# =========================
# Common helpers
# =========================

CHECKED_GLYPHS = {"☑", "✓", "\uf052", ""}  # Wingdings tick
UNCHECKED_GLYPHS = {"☐", "☒"}

def normalize(s: Any) -> str:
    return (str(s) if s is not None else "").strip()

def df_shape(df: pd.DataFrame) -> Tuple[int, int]:
    return df.shape[0], df.shape[1]

def df_cell(df: pd.DataFrame, r: int, c: int) -> str:
    try:
        return normalize(df.iat[r, c])
    except Exception:
        return ""

def df_any(df: pd.DataFrame, predicate) -> bool:
    for r in range(df.shape[0]):
        for c in range(df.shape[1]):
            if predicate(df_cell(df, r, c), r, c):
                return True
    return False

def df_row_texts(df: pd.DataFrame, r: int) -> List[str]:
    return [normalize(x) for x in df.iloc[r].tolist()]

def df_col_texts(df: pd.DataFrame, c: int) -> List[str]:
    return [normalize(df.iat[r, c]) for r in range(df.shape[0])]

def df_to_row_dicts(df: pd.DataFrame) -> List[Dict[str, str]]:
    rows = []
    for i in range(len(df)):
        row = {str(j): ("" if pd.isna(df.iat[i, j]) else str(df.iat[i, j])) for j in range(df.shape[1])}
        rows.append(row)
    return rows

# =========================
# Content-driven detectors
# =========================

SECTION_ID_RE = re.compile(r"^\s*\d+\.\d+\s*$", re.I)

def score_as_backbone(df: pd.DataFrame) -> int:
    """Score a table as likely 'backbone' if col0 contains section ids like 1.1,1.2,2.1,2.2."""
    if df.shape[1] < 2:
        return -10
    col0 = df_col_texts(df, 0)
    hits = [t for t in col0 if SECTION_ID_RE.match(t)]
    uniq = set(hits)
    # extra boost if 1.1 present and next col has 'Event Description'
    bonus = 0
    for r, t in enumerate(col0):
        if t == "1.1":
            title = df_cell(df, r, 1)
            if "event" in title.lower():
                bonus += 2
    return len(uniq) * 5 + bonus  # simple heuristic

def detect_backbone_table(all_tables: Dict[str, pd.DataFrame]) -> Optional[Tuple[str, pd.DataFrame]]:
    best = None
    best_score = -1
    for name, df in all_tables.items():
        try:
            s = score_as_backbone(df)
            if s > best_score:
                best = (name, df)
                best_score = s
        except Exception:
            continue
    return best

def looks_like_rci_header(df: pd.DataFrame) -> bool:
    """Top row has RCI labels, next row has values; somewhere a 'Parent record' row exists."""
    if df.shape[0] < 2:
        return False
    header = [normalize(x).lower() for x in df_row_texts(df, 0)]
    header_ok = ("rci number" in " ".join(header) and "rci owner" in " ".join(header) and "initiated" in " ".join(header))
    if not header_ok:
        return False
    # Find 'Parent record' in first col of any row
    for r in range(1, df.shape[0]):
        if "parent record" in normalize(df.iat[r, 0]).lower():
            return True
    return False

def detect_rci_header_table(all_tables: Dict[str, pd.DataFrame]) -> Optional[Tuple[str, pd.DataFrame]]:
    candidates = []
    for name, df in all_tables.items():
        try:
            if looks_like_rci_header(df):
                # prefer small tables 2-5 rows, 2-4 cols
                rows, cols = df_shape(df)
                size_score = 10 - abs(rows - 3) - abs(cols - 3)
                candidates.append((size_score, name, df))
        except Exception:
            pass
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, name, df = candidates[0]
    return name, df

def looks_like_prerequisites(df: pd.DataFrame) -> bool:
    if df.shape[0] < 2:
        return False
    hdr = [normalize(x).lower() for x in df_row_texts(df, 0)]
    has_sr = any("sr" in h for h in hdr)
    has_pre = any("prereq" in h for h in hdr)
    has_expl = any("explanation" in h or "if no" in h for h in hdr)
    if not (has_sr and has_pre and has_expl):
        return False
    # check presence of checkbox text "☑" or "Yes"/"No" tokens in any cell of col 2
    col2 = [normalize(df.iat[r, 2]) if df.shape[1] > 2 else "" for r in range(df.shape[0])]
    if any(("☑" in x or "Yes" in x or "No" in x) for x in col2):
        return True
    return False

def detect_prerequisites_table(all_tables: Dict[str, pd.DataFrame]) -> Optional[Tuple[str, pd.DataFrame]]:
    for name, df in all_tables.items():
        try:
            if looks_like_prerequisites(df):
                return name, df
        except Exception:
            continue
    return None

def looks_like_task_assignment(df: pd.DataFrame) -> bool:
    if df.shape[0] < 2 or df.shape[1] < 3:
        return False
    hdr = [normalize(x).lower() for x in df_row_texts(df, 0)]
    has_task = any("task" in h for h in hdr)
    has_resp = any("responsible" in h for h in hdr)
    has_tick = any("tick" in h or "√" in h for h in hdr)
    if not (has_task and has_resp):
        return False
    # On data rows, col-0 should contain check glyphs frequently
    col0 = [normalize(df.iat[r, 0]) for r in range(1, df.shape[0])]
    tick_ratio = sum(any(ch in CHECKED_GLYPHS.union(UNCHECKED_GLYPHS) for ch in s) for s in col0) / max(1, len(col0))
    return tick_ratio >= 0.3  # at least 30% rows show a tick box

def detect_task_assignment_table(all_tables: Dict[str, pd.DataFrame]) -> Optional[Tuple[str, pd.DataFrame]]:
    best = None
    best_rows = 0
    for name, df in all_tables.items():
        try:
            if looks_like_task_assignment(df):
                rows = df.shape[0]
                if rows > best_rows:
                    best = (name, df)
                    best_rows = rows
        except Exception:
            pass
    return best



def build_document_json_from_all_tables(
    all_tables: Dict[str, pd.DataFrame],
    main_table
) -> Dict[str, Any]:
    """
    Auto-detects the key tables by content and returns the final FE-ready JSON.
    """

    # 1) Backbone
    bb = detect_backbone_table(all_tables)
    if not bb:
        raise RuntimeError("Could not auto-detect backbone table (sections).")
    backbone_name, backbone_df = bb

    # 2) RCI header table
    id, rci = detect_rci_header_table(all_tables)
    rci_kv = {}
    if not rci.empty:
        rci_kv = df_to_kv_from_header_and_kv_rows(rci)

    # 3) Prerequisites table
    pre = detect_prerequisites_table(all_tables)
    prereq_json = None
    if pre:
        pre_name, pre_df = pre
        pre_rows = df_to_row_dicts(pre_df)
        prereq_json = prerequisites_rows_to_fe_json(pre_rows, "")

    # 4) Task Assignment table
    task = detect_task_assignment_table(all_tables)
    tasks_json = None
    if task:
        task_name, task_df = task
        task_rows = df_to_row_dicts(task_df)
        tasks_json = task_assignment_rows_to_fe_json(task_rows, "")

    # 5) Sign-off (prefer backbone scan)
    signoff = extract_signoff(main_table)

    # 6) Sections JSON from backbone
    table1_rows = df_to_row_dicts(backbone_df)
    sections = parse_table1_into_sections(
        table1_rows,
        rci_details=rci_kv or None,
        prerequisites_json=prereq_json,
        task_assignment_json=tasks_json,
        signoff_kv=signoff or None
    )
    return sections



# --------------
# Main extractor
# --------------


def extract_rci_plan(docx_path: Path) -> Dict[str, Any]:
    doc = Document(docx_path)
    if not doc.tables:
        raise RuntimeError("No tables found in document.")
    
    
    all_tables = {}
    for i, t in enumerate(doc.tables, start=1):
        all_tables.update(walk_tables_dedup_by_xml(t, prefix=f"Table{i}"))

    result = build_document_json_from_all_tables(all_tables, doc.tables[0])
    return result

def _cleanup_label_prefix(text: str, label: str) -> (str, str):
    if not text:
        return "", ""
    m = re.match(rf"^\s*{re.escape(label)}\s*[:：/~-]?\s*", text, flags=re.I)
    if m:
        return label, text[m.end():].strip()
    return "", text.strip()

def _split_on_sentinel(text: str, sentinel: str = SENTINEL) -> List[str]:
    if not text:
        return []
    placeholder = f"{sentinel}_ESC_"
    text = text.replace(sentinel + sentinel, placeholder)
    parts = text.split(sentinel)
    return [p.replace(placeholder, sentinel).strip() for p in parts if p.strip()]

def _split_problem_items(text: str, paragraph_sep: str = SENTINEL) -> List[str]:
    """Split narrative into bullet items using the sentinel + common bullet glyphs."""
    if not text:
        return []
    parts = _split_on_sentinel(text, paragraph_sep)

    bullets = ("", "•", "▪", "‣")
    norm_parts: List[str] = []
    for p in parts:
        for b in bullets:
            p = p.replace(b, "\n")
        for sub in p.split("\n"):
            sub = sub.strip(" \t-–—")
            if sub:
                norm_parts.append(sub)

    out, seen = [], set()
    for p in norm_parts:
        if p in seen:
            continue
        seen.add(p)
        if p and p[-1] not in ".!?":
            p = p + "."
        out.append(p)
    return out

def extract_problem_from_backbone_rows(
    table1_rows: List[Dict[str, Any]],
    ncols: int = 6,
    lookahead: int = 10,
    labels: List[str] = PROBLEM_LABELS,
    paragraph_sep: str = SENTINEL
) -> Dict[str, Any]:
    """
    Given the 'Table1' (backbone) as list of row-dicts {"0": "...", ...},
    find section '1.1', then label-first scan for the problem statement; fallback to longest.
    Return {label, items, meta} (items may be []).
    """

    def row_vals(row: Dict[str, Any]) -> List[str]:
        return [(row.get(str(c)) or "").strip() for c in range(ncols)]

    # 1) Locate the '1.1' row
    start_idx = None
    for idx, row in enumerate(table1_rows):
        if (row.get("0") or "").strip() == "1.1":
            start_idx = idx
            break

    result = {"label": "Problem statement", "items": [], "meta": {}}
    if start_idx is None:
        return result

    end = min(len(table1_rows), start_idx + lookahead + 1)

    # 2) Label-first scan
    for k in range(start_idx, end):
        vals = row_vals(table1_rows[k])
        c0 = vals[0]
        if k > start_idx and SECTION_ID_RE.match(c0):
            break
        for txt in vals[1:]:
            if not txt:
                continue
            for lab in labels:
                found, cleaned = _cleanup_label_prefix(txt, lab)
                if found:
                    items = _split_problem_items(cleaned, paragraph_sep=paragraph_sep)
                    return {"label": found, "items": items, "meta": {"sourceRow": k}}

    # 3) Fallback: choose the longest non-empty among cols 1..(ncols-1)
    for k in range(start_idx, end):
        vals = row_vals(table1_rows[k])
        c0 = vals[0]
        if k > start_idx and SECTION_ID_RE.match(c0):
            break
        candidate = max((t for t in vals[1:] if t.strip()), key=len, default="")
        if candidate:
            # Try to strip any label prefix; else keep as-is
            for lab in labels:
                _, cleaned = _cleanup_label_prefix(candidate, lab)
                if cleaned and cleaned != candidate:
                    items = _split_problem_items(cleaned, paragraph_sep=paragraph_sep)
                    return {"label": lab, "items": items, "meta": {"sourceRow": k}}
            items = _split_problem_items(candidate.strip(), paragraph_sep=paragraph_sep)
            return {"label": labels[0], "items": items, "meta": {"sourceRow": k}}

    return result
