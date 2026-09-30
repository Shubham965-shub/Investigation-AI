import docx

from backend.services.rci_report_export import (
    MISSING_NOTE_FALLBACK,
    _ensure_row_count,
    _maybe_bullet,
    _missing_note,
    _normalize_for_search,
    _tw_text,
    _xml_safe,
)


def test_xml_safe_strips_control_characters():
    assert _xml_safe("a\x13b\x00c") == "abc"
    assert _xml_safe("tab\tand\nnewline") == "tab\tand\nnewline"
    assert _xml_safe("") == ""
    assert _xml_safe(None) is None


def test_maybe_bullet_only_bullets_deviations():
    assert _maybe_bullet(["one", "two"], "Deviation") == ["•\tone", "•\ttwo"]
    assert _maybe_bullet(["one"], "OOS") == ["one"]


def test_missing_note_prefers_specific_error():
    assert _missing_note({"capa": "No CAPA data"}, "capa") == "[No CAPA data]"
    assert _missing_note({}, "capa") == f"[{MISSING_NOTE_FALLBACK}]"


def test_normalize_for_search_collapses_whitespace_and_case():
    assert _normalize_for_search("  Root   Cause\nConclusion ") == "root cause conclusion"


def test_tw_text_returns_first_non_empty_field():
    fields = {"a": "", "b": ["x", "y"], "c": 42}
    assert _tw_text(fields, "a", "b") == "x, y"
    assert _tw_text(fields, "a", "c") == "42"
    assert _tw_text(fields, "missing", "a") == ""


def _table(data_rows):
    table = docx.Document().add_table(rows=1 + data_rows, cols=2)
    for row in table.rows[1:]:
        row.cells[0].text = "old"
    return table


def test_ensure_row_count_grows_and_clears():
    table = _table(1)
    rows = _ensure_row_count(table, 1, 3)
    assert len(rows) == 3 and len(table.rows) == 4
    assert all(cell.text == "" for row in rows for cell in row.cells)


def test_ensure_row_count_shrinks():
    table = _table(4)
    assert len(_ensure_row_count(table, 1, 2)) == 2
    assert len(table.rows) == 3


def test_ensure_row_count_keeps_at_least_one_row():
    table = _table(3)
    assert len(_ensure_row_count(table, 1, 0)) == 1
    assert len(table.rows) == 2
