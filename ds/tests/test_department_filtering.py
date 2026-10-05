"""
Pure-logic tests for the department-aware filtering added this session:
- src.agents.shared.nodes._filter_archetypes_by_department (archetype-level,
  Assay Failure_Mfg/_Lab split for map_to_archetype's candidate list).
- src.agents.evidence_collection.nodes._department_relevant (evidence-item-level,
  fuzzy production/qc matching, including mixed "Production/QA" style tags).
Neither has any DB or LLM dependency, so both are testable directly.
"""

from src.agents.shared.nodes import _filter_archetypes_by_department
from src.agents.evidence_collection.nodes import _department_relevant


# ---------------------------------------------------------------------------
# _filter_archetypes_by_department
# ---------------------------------------------------------------------------


def _arch(name, archetype_id=None):
    return {"id": archetype_id or name, "name": name}


def test_no_op_when_investigation_type_unset():
    archetypes = [_arch("Assay Failure_Mfg"), _arch("Assay Failure_Lab"), _arch("Microbial Failure")]
    assert _filter_archetypes_by_department(archetypes, None) == archetypes
    assert _filter_archetypes_by_department(archetypes, "") == archetypes


def test_keeps_only_mfg_half_of_a_genuine_pair_for_manufacturing():
    archetypes = [_arch("Assay Failure_Mfg"), _arch("Assay Failure_Lab"), _arch("Microbial Failure")]
    result = _filter_archetypes_by_department(archetypes, "Manufacturing")
    names = [a["name"] for a in result]
    assert "Assay Failure_Mfg" in names
    assert "Assay Failure_Lab" not in names
    assert "Microbial Failure" in names  # untouched, no suffix


def test_keeps_only_lab_half_of_a_genuine_pair_for_qc():
    archetypes = [_arch("Assay Failure_Mfg"), _arch("Assay Failure_Lab"), _arch("Microbial Failure")]
    result = _filter_archetypes_by_department(archetypes, "QC")
    names = [a["name"] for a in result]
    assert "Assay Failure_Lab" in names
    assert "Assay Failure_Mfg" not in names


def test_investigation_type_matching_is_case_and_whitespace_insensitive():
    archetypes = [_arch("Assay Failure_Mfg"), _arch("Assay Failure_Lab")]
    result = _filter_archetypes_by_department(archetypes, "  manufacturing  ")
    assert [a["name"] for a in result] == ["Assay Failure_Mfg"]


def test_suffix_matching_is_case_insensitive_in_archetype_names():
    archetypes = [_arch("Assay Failure_MFG"), _arch("Assay Failure_LAB")]
    result = _filter_archetypes_by_department(archetypes, "QC")
    assert [a["name"] for a in result] == ["Assay Failure_LAB"]


def test_keeps_lone_variant_as_is_when_only_one_half_of_a_pair_exists():
    # Only the Mfg variant exists for this base name — not a genuine pair, so nothing is excluded.
    archetypes = [_arch("Rare Failure_Mfg"), _arch("Microbial Failure")]
    result = _filter_archetypes_by_department(archetypes, "QC")
    assert [a["name"] for a in result] == ["Rare Failure_Mfg", "Microbial Failure"]


def test_non_suffixed_archetypes_are_always_kept():
    archetypes = [_arch("Microbial Failure"), _arch("Sterility Failure")]
    result_mfg = _filter_archetypes_by_department(archetypes, "Manufacturing")
    result_qc = _filter_archetypes_by_department(archetypes, "QC")
    assert result_mfg == archetypes
    assert result_qc == archetypes


def test_preserves_archetype_dicts_unchanged():
    archetypes = [_arch("Assay Failure_Mfg", archetype_id=42)]
    result = _filter_archetypes_by_department(archetypes, "Manufacturing")
    assert result == [{"id": 42, "name": "Assay Failure_Mfg"}]


# ---------------------------------------------------------------------------
# _department_relevant
# ---------------------------------------------------------------------------


def test_always_relevant_when_investigation_type_unset():
    assert _department_relevant("Production", None) is True
    assert _department_relevant("QC", None) is True
    assert _department_relevant(None, None) is True


def test_always_relevant_when_department_is_none():
    assert _department_relevant(None, "Manufacturing") is True
    assert _department_relevant(None, "QC") is True


def test_production_tag_matches_manufacturing_only():
    assert _department_relevant("Production", "Manufacturing") is True
    assert _department_relevant("Production", "QC") is False


def test_qc_tag_matches_qc_only():
    assert _department_relevant("QC", "QC") is True
    assert _department_relevant("QC", "Manufacturing") is False


def test_departments_with_neither_tag_are_always_relevant():
    for dept in ["Packing", "Facility & Engineering", "Warehouse", "QA", "IT", "Qualification", "All areas", "All sections"]:
        assert _department_relevant(dept, "Manufacturing") is True
        assert _department_relevant(dept, "QC") is True


def test_mixed_tag_resolves_by_whichever_half_is_wanted():
    # "Production/QA" has no qc substring, only production — Manufacturing sees it, QC doesn't.
    assert _department_relevant("Production/QA", "Manufacturing") is True
    assert _department_relevant("Production/QA", "QC") is False


def test_mixed_tag_with_qc_half_resolves_the_other_way():
    assert _department_relevant("QC/Engineering", "QC") is True
    assert _department_relevant("QC/Engineering", "Manufacturing") is False


def test_tag_containing_both_production_and_qc_is_relevant_to_both():
    assert _department_relevant("Production/QC", "Manufacturing") is True
    assert _department_relevant("Production/QC", "QC") is True


def test_matching_is_case_insensitive():
    assert _department_relevant("PRODUCTION", "manufacturing") is True
    assert _department_relevant("production", "MANUFACTURING") is True
    assert _department_relevant("qc", "qc") is True
