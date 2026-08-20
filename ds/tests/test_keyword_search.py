"""Unit tests for build_tsquery_format — pure function, no DB required.

Regression coverage for the tsquery syntax-error bug: real problem
statements from the QA DB contain batch numbers, percentages, brackets,
slash-separated codes, and dangling hyphens (e.g. "No.75500654,",
"F1/QA/004", "41.8%", "[SGC]", "1g-") that previously crashed
`to_tsquery('english', ...)` on every single realistic query.
"""

from src.agents.search_agent.api.services.keyword_search import build_tsquery_format
from src.utils.text import extract_search_terms, sanitize_for_tsquery


class TestBuildTsqueryFormat:
    def test_empty_input_returns_empty_string(self):
        assert build_tsquery_format("") == ""
        assert build_tsquery_format("   ") == ""

    def test_simple_words_joined_with_ampersand(self):
        assert build_tsquery_format("assay failure") == "assay & failure"

    def test_strips_batch_number_punctuation(self):
        result = build_tsquery_format("Batch No.75500654, failed")
        assert "," not in result
        assert "." not in result
        for term in result.split(" & "):
            assert term.isalnum()

    def test_strips_percentage_symbol(self):
        result = build_tsquery_format("result was 41.8% out of spec")
        for term in result.split(" & "):
            assert term.isalnum()

    def test_strips_brackets(self):
        result = build_tsquery_format("[SGC] coating defect")
        assert "[" not in result and "]" not in result

    def test_splits_slash_separated_codes(self):
        result = build_tsquery_format("ref F1/QA/004 deviation")
        for term in result.split(" & "):
            assert "/" not in term

    def test_no_dangling_hyphen_tokens(self):
        result = build_tsquery_format("dose 1g- variance")
        for term in result.split(" & "):
            assert not term.startswith("-") and not term.endswith("-")
            assert term.isalnum()

    def test_result_never_contains_empty_terms_from_pure_punctuation(self):
        assert build_tsquery_format("...,,,---%%%") == ""

    def test_max_terms_cap_applied_when_requested(self):
        result = build_tsquery_format("one two three four five six seven", max_terms=3)
        assert len(result.split(" & ")) == 3


class TestExtractSearchTerms:
    def test_dedup_case_insensitive_preserves_first_seen_casing(self):
        terms = extract_search_terms("HPLC hplc Assay assay", max_terms=10)
        assert terms == ["HPLC", "Assay"]

    def test_max_terms_cap(self):
        terms = extract_search_terms("one two three four five six seven", max_terms=5)
        assert len(terms) == 5

    def test_min_len_filters_short_tokens(self):
        terms = extract_search_terms("a an HPLC ok", min_len=3)
        assert terms == ["HPLC"]

    def test_empty_input_returns_empty_list(self):
        assert extract_search_terms("") == []


class TestSanitizeForTsquery:
    def test_produces_ampersand_joined_string(self):
        assert sanitize_for_tsquery("assay failure result") == "assay & failure & result"

    def test_caps_at_max_terms(self):
        result = sanitize_for_tsquery("one two three four five six seven eight", max_terms=5)
        assert len(result.split(" & ")) == 5

    def test_empty_input_returns_empty_string(self):
        assert sanitize_for_tsquery("") == ""
