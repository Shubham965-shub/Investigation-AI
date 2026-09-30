from backend.db.module_stage import MODULE_LABELS, next_module_label, stage_for


def test_known_statuses_map_to_stage():
    assert stage_for("Interview Questionnaire") == 3
    assert stage_for("RCI Plan") == 4
    assert stage_for("RC & CAPA Critique") == 5
    assert stage_for("RCI Report") == 6


def test_both_rci_report_spellings_map_to_same_stage():
    assert stage_for("rci report generation") == stage_for("RCI Report") == 6


def test_status_is_case_and_whitespace_insensitive():
    assert stage_for("  rci PLAN \n") == 4


def test_unknown_or_non_string_status_is_zero():
    assert stage_for("Something new") == 0
    assert stage_for("") == 0
    assert stage_for(None) == 0
    assert stage_for(4) == 0


def test_next_module_label():
    assert next_module_label(0) == "Problem Statement"
    assert next_module_label(3) == "RCI Plan Creation"
    assert next_module_label(len(MODULE_LABELS)) == "Complete"
    assert next_module_label(99) == "Complete"
