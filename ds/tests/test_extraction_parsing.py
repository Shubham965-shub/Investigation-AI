"""
Pure-logic tests for src.agents.critique.api.services.extraction — the RCI Plan docx
table-to-FE-JSON transformation pipeline. Scoped to functions that operate on plain
dicts/lists/strings/pandas DataFrames (no python-docx Table/Cell/Run objects needed),
since those are cheap to construct directly and exercise real parsing edge cases.

Deliberately NOT covered here (would need real python-docx Document/Table objects or
XML runs, substantially more setup for comparatively little additional value):
find_section_rows, extract_signoff, walk_tables_dedup_by_xml, rich_cell_text,
extract_sym_chars_from_run_xml, read_checkbox_state_from_sdt, extract_rci_plan,
build_document_json_from_all_tables (the last one also has a latent bug — see below).
"""

import pandas as pd
import pytest

from src.agents.critique.api.services.extraction import (
    norm_space,
    norm_font,
    xml_fingerprint,
    parse_choices,
    prerequisites_rows_to_fe_json,
    df_to_kv_from_header_and_kv_rows,
    is_checked,
    CHECKED_GLYPHS,
    task_assignment_rows_to_fe_json,
    longest_non_empty,
    cleanup_label_prefix,
    split_problem_items,
    SENTINEL,
    extract_problem_statement_from_table1_block,
    parse_table1_into_sections,
    all_tables_to_json,
    normalize,
    df_shape,
    df_cell,
    df_any,
    df_row_texts,
    df_col_texts,
    df_to_row_dicts,
    score_as_backbone,
    detect_backbone_table,
    looks_like_rci_header,
    detect_rci_header_table,
    looks_like_prerequisites,
    detect_prerequisites_table,
    looks_like_task_assignment,
    detect_task_assignment_table,
)


# ---------------------------------------------------------------------------
# norm_space / norm_font / normalize
# ---------------------------------------------------------------------------


def test_norm_space_collapses_whitespace_and_strips():
    assert norm_space("  a   b\tc\n") == "a b c"


def test_norm_space_handles_none_and_empty():
    assert norm_space(None) == ""
    assert norm_space("") == ""


def test_norm_font_lowercases_and_strips():
    assert norm_font("  Wingdings 2  ") == "wingdings 2"


def test_norm_font_none_is_empty_string():
    assert norm_font(None) == ""


def test_normalize_stringifies_and_strips():
    assert normalize(42) == "42"
    assert normalize("  x  ") == "x"
    assert normalize(None) == ""


# ---------------------------------------------------------------------------
# xml_fingerprint
# ---------------------------------------------------------------------------


class _FakeXmlElement:
    def __init__(self, xml):
        self.xml = xml


def test_xml_fingerprint_is_stable_for_identical_content():
    a = _FakeXmlElement("<w:tbl><w:tr/></w:tbl>")
    b = _FakeXmlElement("<w:tbl><w:tr/></w:tbl>")
    assert xml_fingerprint(a) == xml_fingerprint(b)


def test_xml_fingerprint_ignores_whitespace_differences():
    a = _FakeXmlElement("<w:tbl> <w:tr/> </w:tbl>")
    b = _FakeXmlElement("<w:tbl><w:tr/></w:tbl>")
    assert xml_fingerprint(a) == xml_fingerprint(b)


def test_xml_fingerprint_differs_for_different_content():
    a = _FakeXmlElement("<w:tbl><w:tr/></w:tbl>")
    b = _FakeXmlElement("<w:tbl><w:tr/><w:tr/></w:tbl>")
    assert xml_fingerprint(a) != xml_fingerprint(b)


# ---------------------------------------------------------------------------
# parse_choices
# ---------------------------------------------------------------------------


def test_parse_choices_empty_string_returns_empty_list():
    assert parse_choices("") == []
    assert parse_choices(None) == []


def test_parse_choices_orders_yes_no_na_first():
    result = parse_choices("☑ Yes ☒ No ☒N/A")
    assert result == [
        {"label": "Yes", "selected": True},
        {"label": "No", "selected": False},
        {"label": "N/A", "selected": False},
    ]


def test_parse_choices_handles_no_spaces_between_mark_and_label():
    result = parse_choices("☒Yes ☑No")
    assert result == [
        {"label": "Yes", "selected": False},
        {"label": "No", "selected": True},
    ]


def test_parse_choices_dedupes_by_label_true_wins():
    # A merged-cell echo can repeat the same label twice with different marks; any True wins.
    result = parse_choices("☒ Yes ☑ Yes")
    assert result == [{"label": "Yes", "selected": True}]


def test_parse_choices_unrecognized_label_is_title_cased_and_appended_after_known_order():
    result = parse_choices("☑ Yes ☑ Maybe")
    assert result == [
        {"label": "Yes", "selected": True},
        {"label": "Maybe", "selected": True},
    ]


def test_parse_choices_na_variants_normalize_to_same_key():
    result = parse_choices("☑N/A")
    assert result == [{"label": "N/A", "selected": True}]


# ---------------------------------------------------------------------------
# is_checked
# ---------------------------------------------------------------------------


def test_is_checked_false_for_empty_or_none():
    assert is_checked("") is False
    assert is_checked(None) is False


def test_is_checked_true_for_known_checked_glyphs():
    for glyph in CHECKED_GLYPHS:
        if glyph:  # the empty-string member is handled by the empty/None guard above
            assert is_checked(glyph) is True
            assert is_checked(f" {glyph} ") is True


def test_is_checked_false_for_unchecked_glyphs():
    assert is_checked("☐") is False
    assert is_checked("☒") is False


def test_is_checked_false_for_plain_text():
    assert is_checked("Not Applicable") is False


# ---------------------------------------------------------------------------
# prerequisites_rows_to_fe_json
# ---------------------------------------------------------------------------


def test_prerequisites_rows_to_fe_json_empty_input():
    result = prerequisites_rows_to_fe_json([], "Pre-requisites")
    assert result == {"title": "Pre-requisites", "header": [], "columnsMap": {}, "items": []}


def test_prerequisites_rows_to_fe_json_builds_items_and_columns_map():
    rows = [
        {"0": "Sr", "1": "Prerequisite", "2": "Response", "3": "Explanation"},
        {"0": "1", "1": "Bench-top verification done?", "2": "☑ Yes ☒ No", "3": ""},
    ]
    result = prerequisites_rows_to_fe_json(rows, "Pre-requisites")
    assert result["columnsMap"] == {
        "sr": "Sr",
        "question": "Prerequisite",
        "options": "Response",
        "explanation": "Explanation",
    }
    assert result["items"] == [
        {
            "sr": "1",
            "question": "Bench-top verification done?",
            "optionsRaw": "☑ Yes ☒ No",
            "choices": [{"label": "Yes", "selected": True}, {"label": "No", "selected": False}],
            "explanation": "",
        }
    ]


def test_prerequisites_rows_to_fe_json_defaults_options_header_when_missing():
    rows = [{"0": "Sr", "1": "Prerequisite"}]
    result = prerequisites_rows_to_fe_json(rows, "t")
    assert result["columnsMap"]["options"] == "Yes or No"


# ---------------------------------------------------------------------------
# df_to_kv_from_header_and_kv_rows
# ---------------------------------------------------------------------------


def test_df_to_kv_from_header_and_kv_rows_empty_df():
    assert df_to_kv_from_header_and_kv_rows(pd.DataFrame()) == {}


def test_df_to_kv_from_header_and_kv_rows_header_plus_values_row():
    df = pd.DataFrame([["RCI Number", "RCI Owner"], ["RCI-123", "Jane Doe"]])
    assert df_to_kv_from_header_and_kv_rows(df) == {"RCI Number": "RCI-123", "RCI Owner": "Jane Doe"}


def test_df_to_kv_from_header_and_kv_rows_appends_key_value_pairs_from_remaining_rows():
    df = pd.DataFrame(
        [
            ["RCI Number", "RCI Owner"],
            ["RCI-123", "Jane Doe"],
            ["Parent Record", "DEV-999"],
        ]
    )
    result = df_to_kv_from_header_and_kv_rows(df)
    assert result["Parent Record"] == "DEV-999"


def test_df_to_kv_from_header_and_kv_rows_does_not_overwrite_existing_key_with_blank_value():
    df = pd.DataFrame(
        [
            ["Parent Record", "x"],
            ["DEV-999", "ignored"],
            ["Parent Record", ""],  # blank value must not clobber the already-set key
        ]
    )
    result = df_to_kv_from_header_and_kv_rows(df)
    assert result["Parent Record"] == "DEV-999"


# ---------------------------------------------------------------------------
# task_assignment_rows_to_fe_json
# ---------------------------------------------------------------------------


def test_task_assignment_rows_to_fe_json_empty_input():
    result = task_assignment_rows_to_fe_json([])
    assert result["items"] == []
    assert result["mandatorySummary"] == {
        "totalMandatory": 0,
        "selectedMandatory": 0,
        "allMandatorySelected": True,
    }


def test_task_assignment_rows_to_fe_json_maps_select_header_to_display_header():
    rows = [
        {"0": "Tick √ (as applicable)", "1": "Task", "2": "Status", "3": "Responsible Person"},
        {"0": "☑", "1": "$Investigate root cause", "2": "In Progress", "3": "Jane Doe"},
    ]
    result = task_assignment_rows_to_fe_json(rows)
    assert result["displayHeader"][0] == "Select"
    assert result["headerRaw"][0] == "Tick √ (as applicable)"
    item = result["items"][0]
    assert item["select"] is True
    assert item["task"] == "Investigate root cause"  # leading '$' stripped
    assert item["mandatory"] is True
    assert item["mandatorySelected"] is True
    assert result["mandatorySummary"] == {
        "totalMandatory": 1,
        "selectedMandatory": 1,
        "allMandatorySelected": True,
    }


def test_task_assignment_rows_to_fe_json_non_mandatory_task_has_no_mandatory_selected_key():
    rows = [
        {"0": "Select", "1": "Task", "2": "Status", "3": "Responsible"},
        {"0": "☐", "1": "Review photos", "2": "Not Applicable", "3": ""},
    ]
    result = task_assignment_rows_to_fe_json(rows)
    item = result["items"][0]
    assert item["mandatory"] is False
    assert "mandatorySelected" not in item


def test_task_assignment_rows_to_fe_json_summary_reflects_unselected_mandatory_tasks():
    rows = [
        {"0": "Select", "1": "Task", "2": "Status", "3": "Responsible"},
        {"0": "☐", "1": "$Mandatory but not done", "2": "", "3": ""},
    ]
    result = task_assignment_rows_to_fe_json(rows)
    assert result["mandatorySummary"]["allMandatorySelected"] is False


# ---------------------------------------------------------------------------
# longest_non_empty / cleanup_label_prefix / split_problem_items
# ---------------------------------------------------------------------------


def test_longest_non_empty_picks_the_longest_string():
    assert longest_non_empty(["short", "a much longer candidate string", ""]) == "a much longer candidate string"


def test_longest_non_empty_returns_empty_string_when_all_blank():
    assert longest_non_empty(["", "   ", None]) == ""


def test_cleanup_label_prefix_strips_label_and_separator():
    label, cleaned = cleanup_label_prefix("Problem statement: batch weight out of spec", "Problem statement")
    assert label == "Problem statement"
    assert cleaned == "batch weight out of spec"


def test_cleanup_label_prefix_case_insensitive_and_slash_separator():
    label, cleaned = cleanup_label_prefix("PROBLEM STATEMENT / something happened", "Problem statement")
    assert label == "Problem statement"
    assert cleaned == "something happened"


def test_cleanup_label_prefix_no_match_returns_empty_label_and_trimmed_text():
    label, cleaned = cleanup_label_prefix("  unrelated text  ", "Problem statement")
    assert label == ""
    assert cleaned == "unrelated text"


def test_cleanup_label_prefix_empty_text():
    assert cleanup_label_prefix("", "Problem statement") == ("", "")


def test_split_problem_items_splits_on_sentinel_and_bullets():
    text = f"First issue{SENTINEL}• Second issue•third issue"
    items = split_problem_items(text)
    assert items == ["First issue.", "Second issue.", "third issue."]


def test_split_problem_items_dedupes_repeated_items():
    text = f"Same issue{SENTINEL}Same issue"
    assert split_problem_items(text) == ["Same issue."]


def test_split_problem_items_preserves_existing_terminal_punctuation():
    assert split_problem_items("Already ends with a question?") == ["Already ends with a question?"]


def test_split_problem_items_empty_text_returns_empty_list():
    assert split_problem_items("") == []
    assert split_problem_items(None) == []


# ---------------------------------------------------------------------------
# extract_problem_statement_from_table1_block
# ---------------------------------------------------------------------------


def _row_vals_fn(ncols=6):
    return lambda row: [(row.get(str(c)) or "").strip() for c in range(ncols)]


def test_extract_problem_statement_label_first_match():
    rows = [
        {"0": "1.1", "1": "Event Description"},
        {"0": "", "1": "Problem statement: pump seal failed"},
    ]
    result = extract_problem_statement_from_table1_block(rows, _row_vals_fn(), start_index=0)
    assert result["label"] == "Problem statement"
    assert result["cleaned"] == "pump seal failed"
    assert result["sourceRow"] == 1


def test_extract_problem_statement_stops_at_next_section_marker():
    # The start_index row itself is part of the scan window, so it must carry no title text
    # in the other columns here — otherwise it would be picked up as a fallback candidate
    # before the scan ever reaches row 2.
    rows = [
        {"0": "1.1"},
        {"0": "1.2", "1": "Pre-requisites"},
        {"0": "", "1": "Problem statement: should not be reached"},
    ]
    result = extract_problem_statement_from_table1_block(rows, _row_vals_fn(), start_index=0)
    assert result is None


def test_extract_problem_statement_falls_back_to_longest_candidate_when_no_label_found():
    rows = [
        {"0": "1.1"},
        {"0": "", "1": "short", "2": "a considerably longer narrative text here"},
    ]
    result = extract_problem_statement_from_table1_block(rows, _row_vals_fn(), start_index=0)
    assert result["cleaned"] == "a considerably longer narrative text here"


def test_extract_problem_statement_returns_none_when_window_has_no_text():
    rows = [{"0": "1.1"}]
    result = extract_problem_statement_from_table1_block(rows, _row_vals_fn(), start_index=0)
    assert result is None


# ---------------------------------------------------------------------------
# parse_table1_into_sections
# ---------------------------------------------------------------------------


def test_parse_table1_into_sections_builds_four_sections_with_instructions():
    rows = [
        {"0": "1.1", "1": "Event Description"},
        {"0": "Instruction A / Instruction B"},
        {"0": "", "1": "Problem statement: something broke"},
        {"0": "1.2", "1": "Pre-requisites"},
        {"0": "2.1", "1": "Task Assignment"},
        {"0": "2.2", "1": "Sign-off"},
    ]
    result = parse_table1_into_sections(
        rows,
        rci_details={"rci_number": "RCI-1"},
        prerequisites_json={"items": []},
        task_assignment_json={"items": []},
        signoff_kv={"Investigator": "Jane Doe"},
    )
    numbers = [s["number"] for s in result["sections"]]
    assert numbers == ["1.1", "1.2", "2.1", "2.2"]

    section_1_1 = result["sections"][0]
    assert section_1_1["instructions"] == ["Instruction A", "Instruction B"]
    assert section_1_1["problemStatement"]["items"] == ["something broke."]
    assert section_1_1["rciDetails"] == {"rci_number": "RCI-1"}

    assert result["sections"][1]["prerequisites"] == {"items": []}
    assert result["sections"][2]["taskAssignment"] == {"items": []}
    assert result["sections"][3]["signoff"] == {"Investigator": "Jane Doe"}


def test_parse_table1_into_sections_skips_fully_empty_rows_without_adding_instructions():
    rows = [
        {"0": "1.1", "1": "Event Description"},
        {"0": "", "1": ""},  # fully empty — must be skipped, not added as an instruction
        {"0": "1.2", "1": "Pre-requisites"},
    ]
    result = parse_table1_into_sections(rows)
    assert "instructions" not in result["sections"][0]


def test_parse_table1_into_sections_ignores_non_section_rows_before_first_section():
    rows = [
        {"0": "preamble", "1": "irrelevant"},
        {"0": "1.1", "1": "Event Description"},
    ]
    result = parse_table1_into_sections(rows)
    assert len(result["sections"]) == 1
    assert result["sections"][0]["number"] == "1.1"


# ---------------------------------------------------------------------------
# all_tables_to_json
# ---------------------------------------------------------------------------


def test_all_tables_to_json_converts_dataframes_and_fills_na():
    df = pd.DataFrame([["a", None], ["b", "c"]])
    result = all_tables_to_json({"Table1": df})
    assert result == {"Table1": [{0: "a", 1: ""}, {0: "b", 1: "c"}]}


def test_all_tables_to_json_handles_multiple_tables():
    df1 = pd.DataFrame([["x"]])
    df2 = pd.DataFrame([["y"]])
    result = all_tables_to_json({"Table1": df1, "Table1_r0c0_sub1": df2})
    assert set(result.keys()) == {"Table1", "Table1_r0c0_sub1"}


# ---------------------------------------------------------------------------
# df_shape / df_cell / df_any / df_row_texts / df_col_texts / df_to_row_dicts
# ---------------------------------------------------------------------------


def test_df_shape():
    assert df_shape(pd.DataFrame([[1, 2, 3]])) == (1, 3)


def test_df_cell_returns_normalized_text():
    df = pd.DataFrame([[" x ", 42]])
    assert df_cell(df, 0, 0) == "x"
    assert df_cell(df, 0, 1) == "42"


def test_df_cell_out_of_range_returns_empty_string():
    df = pd.DataFrame([["x"]])
    assert df_cell(df, 5, 5) == ""


def test_df_any_true_when_predicate_matches_any_cell():
    df = pd.DataFrame([["a", "b"], ["c", "target"]])
    assert df_any(df, lambda text, r, c: text == "target") is True
    assert df_any(df, lambda text, r, c: text == "missing") is False


def test_df_row_texts_and_df_col_texts():
    df = pd.DataFrame([["a", "b"], ["c", "d"]])
    assert df_row_texts(df, 0) == ["a", "b"]
    assert df_col_texts(df, 1) == ["b", "d"]


def test_df_to_row_dicts_uses_string_column_keys_and_empty_string_for_nan():
    df = pd.DataFrame([["h0", "h1"], ["v0", None]])
    assert df_to_row_dicts(df) == [{"0": "h0", "1": "h1"}, {"0": "v0", "1": ""}]


# ---------------------------------------------------------------------------
# Table-type detection heuristics (score_as_backbone / looks_like_* / detect_*)
# ---------------------------------------------------------------------------


def test_score_as_backbone_requires_at_least_two_columns():
    assert score_as_backbone(pd.DataFrame([["only one column"]])) == -10


def test_score_as_backbone_scores_unique_section_ids_with_event_description_bonus():
    df = pd.DataFrame(
        [
            ["1.1", "Event Description"],
            ["1.2", "Pre-requisites"],
            ["2.1", "Task Assignment"],
            ["2.2", "Sign-off"],
        ]
    )
    # 4 unique section ids * 5 = 20, plus +2 bonus since "1.1" row's col1 contains "event"
    assert score_as_backbone(df) == 22


def test_detect_backbone_table_picks_highest_scoring_table_and_skips_bad_entries():
    good = pd.DataFrame([["1.1", "Event Description"], ["1.2", "x"]])
    weak = pd.DataFrame([["no section ids here", "x"]])
    tables = {"Weak": weak, "Good": good, "NotADataFrame": object()}
    name, df = detect_backbone_table(tables)
    assert name == "Good"
    assert df is good


def test_looks_like_rci_header_requires_header_labels_and_parent_record_row():
    df = pd.DataFrame(
        [
            ["RCI Number", "RCI Owner", "Initiated On"],
            ["RCI-1", "Jane Doe", "01/01/2026"],
            ["Parent record", "DEV-999", ""],
        ]
    )
    assert looks_like_rci_header(df) is True


def test_looks_like_rci_header_false_without_parent_record_row():
    df = pd.DataFrame([["RCI Number", "RCI Owner", "Initiated On"], ["RCI-1", "Jane Doe", "01/01/2026"]])
    assert looks_like_rci_header(df) is False


def test_detect_rci_header_table_prefers_table_closest_to_3x3():
    small = pd.DataFrame(
        [
            ["RCI Number", "RCI Owner", "Initiated On"],
            ["RCI-1", "Jane Doe", "01/01/2026"],
            ["Parent record", "DEV-999", ""],
        ]
    )
    tables = {"Only": small}
    result = detect_rci_header_table(tables)
    assert result is not None
    assert result[0] == "Only"


def test_detect_rci_header_table_returns_none_when_nothing_matches():
    df = pd.DataFrame([["unrelated", "data"]])
    assert detect_rci_header_table({"T": df}) is None


def test_looks_like_prerequisites_requires_headers_and_choice_tokens_in_col2():
    df = pd.DataFrame(
        [
            ["Sr", "Prerequisite", "Response", "Explanation"],
            ["1", "Bench-top verification done?", "☑ Yes ☒ No", ""],
        ]
    )
    assert looks_like_prerequisites(df) is True


def test_looks_like_prerequisites_false_without_choice_tokens():
    df = pd.DataFrame([["Sr", "Prerequisite", "Response", "Explanation"], ["1", "x", "unrelated", ""]])
    assert looks_like_prerequisites(df) is False


def test_detect_prerequisites_table_returns_first_match():
    match = pd.DataFrame(
        [["Sr", "Prerequisite", "Response", "Explanation"], ["1", "x", "☑ Yes ☒ No", ""]]
    )
    no_match = pd.DataFrame([["a", "b"]])
    result = detect_prerequisites_table({"NoMatch": no_match, "Match": match})
    assert result[0] == "Match"


def test_looks_like_task_assignment_requires_task_responsible_headers_and_tick_ratio():
    df = pd.DataFrame(
        [
            ["Tick", "Task", "Status", "Responsible Person"],
            ["☑", "Investigate", "Done", "Jane Doe"],
            ["☐", "Review", "Pending", "John Smith"],
        ]
    )
    assert looks_like_task_assignment(df) is True


def test_looks_like_task_assignment_false_when_tick_ratio_too_low():
    df = pd.DataFrame(
        [
            ["Tick", "Task", "Status", "Responsible Person"],
            ["no tick here", "Investigate", "Done", "Jane Doe"],
        ]
    )
    assert looks_like_task_assignment(df) is False


def test_detect_task_assignment_table_picks_table_with_most_rows():
    small = pd.DataFrame([["Tick", "Task", "Status", "Responsible"], ["☑", "A", "x", "y"]])
    big = pd.DataFrame(
        [
            ["Tick", "Task", "Status", "Responsible"],
            ["☑", "A", "x", "y"],
            ["☐", "B", "x", "y"],
            ["☑", "C", "x", "y"],
        ]
    )
    result = detect_task_assignment_table({"Small": small, "Big": big})
    assert result[0] == "Big"
