import re
import zipfile
from datetime import date
from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

_LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z /()]{1,59}):\s*(.*)", re.DOTALL)
_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_CHECKED_SYMBOLS = {("Wingdings", "F0FE"), #filled ballot box
                    ("Wingdings 2", "F052")} #tick mark

_W = NS["w"]

#---------------------------------------------------------
# Low-level helpers
#---------------------------------------------------------

def _cell_text(cell):
    return "".join(r.text  or "" for r in cell.findall(".//w:t", NS)).strip()

def _para_text(para):
    return "".join(r.text or "" for r in para.findall(".//w:t", NS))

def _normalize(text):
    return text.strip().replace("\xa0"," ").replace("\u202f", " ").replace("\u202f", " ")

def _parse_date(raw):
    if not raw:
        return None
    m = _DATE_RE.match(raw.strip())
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            pass
    return None

def _section_type(label):
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")

def _sym_checked(sym_elem):
    """ Return True if this w:sym element represents a checked/ticked state."""
    font = sym_elem.get(f"{{{_W}}}font")
    char = sym_elem.get(f"{{{_W}}}char")
    return (font, char) in _CHECKED_SYMBOLS

def _parse_choices(cell):
    """
    Parse a Yes/No/N/A cell that uses Wingdings symbol checkboxes.
    Returns list of {"label": "Yes"|"No"|"N/A", "selected":bool}.
    """

    choices = []
    pending_checked = None
    for run in cell.findall(".//w:r", NS):
        sym = run.find(".//w:sym", NS)
        if sym is not None:
            pending_checked = _sym_checked(sym)
        label = _normalize("".join(t.text or "" for t in run.findall(".//w:t", NS)))
        if label and pending_checked is not None:
            choices.append({"label": label, "selected": pending_checked})
            pending_checked = None
    return choices

def _largest_nested_table(cell):
    """ Return the nested table with the most rows (skips single-row wrappers)"""
    tables = cell.findall(".//w:tbl", NS)
    if not tables:
        return None
    return max(tables, key=lambda t: len(t.findall("w:tr", NS)))

def _open_document(docx_path):
    with zipfile.ZipFile(docx_path) as docx_zip:
        with docx_zip.open("word/document.xml") as doc_xml:
            return etree.parse(doc_xml)
        
def _main_table(tree):
    body = tree.getroot().find("w:body", NS)
    table = next((e for e in body if e.tag.split("}")[-1] == "tbl"), None)
    if table is None:
        raise ValueError("No body-level table found in document")
    return table
    

#---------------------------------------------------------
# Section 1.1 - Event Description
#---------------------------------------------------------

def _parse_narrative_sections(paragraphs):
    sections = []
    current_label = None
    current_items = []

    def flush():
        if current_label is not None:
            items = [t for t in current_items if t]
            fields = [{"key": "text", "value":items if len(items) >1 else items[0]}] if items else []
            sections.append({"section_type": _section_type(current_label), "title": current_label, "fields": fields})

    for raw in paragraphs:
        text = _normalize(raw)
        if not text:
            continue
        m = _LABEL_RE.match(text)
        if m:
            flush()
            current_label = m.group(1).strip()
            current_items = [m.group(2).strip()] if m.group(2).strip() else []
        else:
            if current_label is None:
                current_label = "text"
                current_items = [text]
            else:
                current_items.append(text)

    flush()
    return sections
    
def _extract_rci_header(header_table):
    rows = header_table.findall("w:tr", NS)
    result = {
        "rci_number": None,
        "rci_owner": None,
        "initiated_on_raw": None,
        "initiated_on": None,
        "parent_record": None,
        "parent_record_date_raw": None,
        "parent_record_date": None
    }
    #Row 1: [rci_number, rci_owner, initiated_on]
    if  len(rows) >= 2:
        vals = rows[1].findall("w:tc", NS)
        if len(vals) >= 1:
            result["rci_number"] = _cell_text(vals[0]) or None
        if len(vals) >= 2:
            result["rci_owner"] = _cell_text(vals[1]) or None
        if len(vals) >= 3:
            raw = _cell_text(vals[2])
            result["initiated_on_raw"] = raw or None
            result["initiated_on"] = _parse_date(raw)
    
    #Row 2: [Parent record label, value, optional_extra]
    if len(rows) >= 3:
        parent_cells = rows[2].findall("w:tc", NS)
        if len(parent_cells) >= 2:
            result["parent_record"] = _cell_text(parent_cells[1]) or None
        if len(parent_cells) >= 3:
            raw = _cell_text(parent_cells[2])
            if raw and raw.upper() not in ("NA", "N/A"):
                result["parent_record_date_raw"] = raw
                result["parent_record_date"] = _parse_date(raw)
    return result

def extract_section_1_1(docx_path):
    tree = _open_document(docx_path)
    rows = _main_table(tree).findall("w:tr", NS)

    rci_header = None
    if len(rows) > 2:
        cells = rows[2].findall("w:tc", NS)
        if len(cells) >1:
            nested = cells[1].find(".//w:tbl", NS)
            if nested is not None:
                rci_header = _extract_rci_header(nested)
    sections = []
    if len(rows) >4:
        cells = rows[4].findall("w:tc", NS)
        if len(cells) > 1:
            raw_paras = [_para_text(p) for p in cells[1].findall("w:p", NS)]
            sections = _parse_narrative_sections(raw_paras)
    return {
        "section_number": "1.1",
        "title": "Event Description",
        "rci_header": rci_header,
        "sections": sections

    }

#---------------------------------------------------------
# Section 1.2 - Prerequisites
#---------------------------------------------------------

def extract_section_1_2(docx_path):
    tree = _open_document(docx_path)
    rows = _main_table(tree).findall("w:tr",NS)

    items = []
    if len(rows) > 6:
        prereq_cell = rows[6].findall("w:tc", NS)
        if len(prereq_cell) > 1:
            prereq_table = prereq_cell[1].find(".//w:tbl", NS)
            if prereq_table is not None:
                table_rows = prereq_table.findall("w:tr", NS)
                for row in table_rows[1:]:
                    cells = row.findall("w:tc", NS)
                    if len(cells) < 3:
                        continue
                    sr = _cell_text(cells[0]) or None
                    prerequisite = _normalize(_cell_text(cells[1]))
                    if not prerequisite:
                        continue
                    choices = _parse_choices(cells[2])
                    explanation = _normalize(_cell_text(cells[3]) )if len(cells) > 3 else None
                    items.append({
                        "sr": sr,
                        "prerequisite": prerequisite,
                        "choices": choices,
                        "explanation": explanation or None
                    })
    return {
        "section_number": "1.2",
        "title": "Pre-requisite of Investigation Plan",
        "items": items
    }

#---------------------------------------------------------
# Section 2.1 - Task Assignments
#---------------------------------------------------------

def extract_section_2_1(docx_path):
    tree = _open_document(docx_path)
    rows = _main_table(tree).findall("w:tr", NS)

    items = []
    if len(rows) > 8:
        task_cell = rows[8].findall("w:tc", NS)
        if len(task_cell) > 1:
            task_table = _largest_nested_table(task_cell[1])
            if task_table is not None:
                table_rows = task_table.findall("w:tr", NS)
                for row in table_rows[1:]:
                    cells = row.findall("w:tc", NS)
                    if len(cells)<2:
                        continue

                    tick_sym = cells[0].find(".//w:sym", NS)
                    selected = _sym_checked(tick_sym) if tick_sym is not None else None

                
                    raw_task = _normalize(_cell_text(cells[1]))
                    if not raw_task:
                        continue
                    # mandatory = raw_task.startswith("$")
                    # task = raw_task.lstrip("$").strip()
                    mandatory = raw_task.startswith(("$", "*"))
                    # task = raw_task[1:].strip() if mandatory else raw_task
                    task = raw_task
                    status = _normalize(_cell_text(cells[2])) if len(cells) > 2 else None

                    responsible_person = _normalize(_cell_text(cells[3])) if len(cells) > 3 else None
                    items.append({

                        "selected": selected,
                        "task": task,
                        "status": status or None,
                        "responsible_person": responsible_person or None,
                        "mandatory": mandatory
                    })
    return {
        "section_number": "2.1",
        "title": "Identification of investigation Team members & Task Assignment",
        "items": items
    }


#---------------------------------------------------------
# Section 2.2 - Sign - off
#---------------------------------------------------------

def extract_section_2_2(docx_path):
    tree = _open_document(docx_path)
    rows = _main_table(tree).findall("w:tr", NS)

    signatories = []
    if len(rows) >= 12:
        header_cells = rows[10].findall("w:tc", NS)
        value_cells = rows[11].findall("w:tc", NS)
        roles = [_cell_text(c) for c in header_cells[1:]]
        values = [_cell_text(c) for c in value_cells[1:]]
        for role, val in zip(roles, values):
            if role:
                signatories.append({"role": role, "name": val or None})
   
    return {
        "section_number": "2.2",
        "title": "RCI Plan Sign-off",
        "signatories": signatories
    }


#---------------------------------------------------------
# Combined extractor
#---------------------------------------------------------

def extract_all_sections(docx_path):
    return {
        "EventDescription": extract_section_1_1(docx_path),
        "prerequisites": extract_section_1_2(docx_path),
        "taskassignments": extract_section_2_1(docx_path),
        "signoff": extract_section_2_2(docx_path)
    }

if __name__ == "__main__":
    import json, sys, pathlib,os
    targets = sys.argv[1:] or sorted(pathlib.Path("samples/documents").glob("*.docx"))
    print(os.listdir())
    for path in targets:
        print(f"\n{'='*60}")
        print(f"File: {path}")
        result = extract_all_sections(str(path))
        print(json.dumps(result, indent=2, default=str))