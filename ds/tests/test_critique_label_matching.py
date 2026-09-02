"""
Regression tests for the critique module's fuzzy image/section label matching
(src/agents/critique/graph/nodes.py). This is the deterministic matching layer
that decides which extracted images belong to which task's evidence — the
fuzzy-match rule, the digit-token guard, and the whole-word containment check
were all added to fix real live bugs (dropped images due to exact-match
whitespace/punctuation drift, and distinct numbered stages/tables being
conflated by character-level similarity alone) but had no dedicated test
coverage.
"""

from src.agents.critique.graph.nodes import (
    _build_visual_obs_for_task,
    _contains_as_words,
    _labels_match,
    _normalize_label,
)


# ---------------------------------------------------------------------------
# _normalize_label
# ---------------------------------------------------------------------------


def test_normalize_label_strips_punctuation_and_lowercases():
    assert _normalize_label("Stage-1: Yield  Table.") == "stage 1 yield table"


def test_normalize_label_collapses_whitespace():
    assert _normalize_label("  Dispensing   Area   SOP  ") == "dispensing area sop"


# ---------------------------------------------------------------------------
# _contains_as_words
# ---------------------------------------------------------------------------


def test_contains_as_words_matches_whole_word():
    assert _contains_as_words("table", "stage 1 yield table") is True


def test_contains_as_words_does_not_match_substring_inside_longer_word():
    """The exact case documented in nodes.py's own docstring: 'table' must not
    match inside 'tablets'."""
    assert _contains_as_words("table", "tablets dispensed") is False


# ---------------------------------------------------------------------------
# _labels_match
# ---------------------------------------------------------------------------


def test_labels_match_exact_after_normalization():
    assert _labels_match("Dispensing Area SOP", "dispensing area sop") is True


def test_labels_match_whitespace_and_punctuation_drift():
    """The bug this fixes: exact string equality silently dropped images whose
    label picked up different whitespace/punctuation between the two
    independent extractions (docx paragraph text vs. the extraction LLM's
    best-effort copy)."""
    assert _labels_match("Stage 1 - Yield Table", "Stage 1 Yield Table.") is True


def test_labels_match_one_label_contained_in_the_other():
    assert _labels_match("Yield Table", "Stage 1 Yield Table") is True


def test_labels_match_rejects_different_numbered_stages():
    """The bug this guards against: 'Stage 1 Yield' vs 'Stage 2 Yield' has a
    SequenceMatcher ratio of 0.92 (well above the fuzzy threshold), so digit
    tokens must match exactly before the fuzzy ratio is trusted at all."""
    assert _labels_match("Stage 1 Yield", "Stage 2 Yield") is False


def test_labels_match_same_digits_still_allows_fuzzy_match():
    assert _labels_match("Stage 1 Yield Table", "Stage 1 - Yield Tables") is True


def test_labels_match_empty_label_never_matches():
    assert _labels_match("", "Dispensing Area SOP") is False
    assert _labels_match("Dispensing Area SOP", "") is False


def test_labels_match_rejects_unrelated_labels():
    assert _labels_match("Material Verification Checklist", "Equipment Calibration Log") is False


# ---------------------------------------------------------------------------
# _build_visual_obs_for_task
# ---------------------------------------------------------------------------


def _image(context_label, observation="Line clearance photo shows cleared area.", **overrides):
    defaults = {
        "context_label": context_label,
        "observation": observation,
        "is_evidence_photo": True,
        "supports_written_claim": True,
        "compliance_concerns": "",
    }
    defaults.update(overrides)
    return defaults


def test_build_visual_obs_matches_via_fuzzy_section_label():
    task = {"section_labels": ["Dispensing Area SOP"]}
    image_analyses = [_image("Dispensing Area SOP.")]
    result = _build_visual_obs_for_task(task, image_analyses)
    assert "Line clearance photo" in result


def test_build_visual_obs_no_match_returns_placeholder():
    task = {"section_labels": ["Dispensing Area SOP"]}
    image_analyses = [_image("Unrelated Equipment Log")]
    result = _build_visual_obs_for_task(task, image_analyses)
    assert result == "No photographic evidence for this task."


def test_build_visual_obs_excludes_non_evidence_photos():
    task = {"section_labels": ["Dispensing Area SOP"]}
    image_analyses = [_image("Dispensing Area SOP", is_evidence_photo=False)]
    result = _build_visual_obs_for_task(task, image_analyses)
    assert result == "No photographic evidence for this task."


def test_build_visual_obs_flags_non_supporting_claims():
    task = {"section_labels": ["Dispensing Area SOP"]}
    image_analyses = [_image("Dispensing Area SOP", supports_written_claim=False)]
    result = _build_visual_obs_for_task(task, image_analyses)
    assert "Does not support written claim." in result


def test_build_visual_obs_includes_compliance_concerns():
    task = {"section_labels": ["Dispensing Area SOP"]}
    image_analyses = [_image("Dispensing Area SOP", compliance_concerns="Gloves not worn.")]
    result = _build_visual_obs_for_task(task, image_analyses)
    assert "Compliance concerns: Gloves not worn." in result


def test_build_visual_obs_does_not_conflate_distinct_numbered_stages():
    task = {"section_labels": ["Stage 1 Yield Table"]}
    image_analyses = [_image("Stage 2 Yield Table")]
    result = _build_visual_obs_for_task(task, image_analyses)
    assert result == "No photographic evidence for this task."
