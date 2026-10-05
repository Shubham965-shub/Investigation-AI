"""Pure-logic tests for the search_agent SQL filter builder — no DB required.
APP_EVENT_TYPE_TO_QE_TYPE translation, date-range resolution, and parameterised
WHERE-clause construction are all plain data transforms."""

from datetime import datetime

from src.agents.search_agent.api.services.filters import (
    SearchFilters,
    build_filter_clause,
    parse_date_range,
    resolve_qe_type_filter,
)


class TestResolveQeTypeFilter:
    def test_none_passes_through(self):
        assert resolve_qe_type_filter(None) is None

    def test_deviation_maps_to_itself(self):
        assert resolve_qe_type_filter("Deviation") == "Deviation"

    def test_oos_maps_to_db_native_value(self):
        assert resolve_qe_type_filter("OOS") == "Out Of Specification"

    def test_oot_maps_to_db_native_value(self):
        assert resolve_qe_type_filter("OOT") == "Out of Trend"

    def test_combined_oos_oot_maps_to_a_list(self):
        assert resolve_qe_type_filter("OOS/OOT") == ["Out Of Specification", "Out of Trend"]

    def test_market_complaint_maps_to_complaint(self):
        assert resolve_qe_type_filter("Market Complaint") == "Complaint"

    def test_unknown_value_passes_through_unchanged(self):
        assert resolve_qe_type_filter("Something Else") == "Something Else"


class TestParseDateRange:
    def test_all_and_legacy_all_time_return_none_none(self):
        assert parse_date_range("all") == (None, None)
        assert parse_date_range("all_time") == (None, None)

    def test_unknown_range_defaults_to_none_none(self):
        assert parse_date_range("not_a_real_range") == (None, None)

    def test_custom_range_parses_iso_strings(self):
        date_from, date_to = parse_date_range("custom", custom_from="2026-01-01", custom_to="2026-02-01")
        assert date_from == datetime.fromisoformat("2026-01-01")
        assert date_to == datetime.fromisoformat("2026-02-01")

    def test_custom_range_with_missing_bounds_returns_none_for_that_bound(self):
        date_from, date_to = parse_date_range("custom", custom_from="2026-01-01", custom_to=None)
        assert date_from == datetime.fromisoformat("2026-01-01")
        assert date_to is None

    def test_last_7_days_returns_a_7_day_window_ending_now(self):
        date_from, date_to = parse_date_range("last_7_days")
        assert (date_to - date_from).days == 7

    def test_last_2_years_returns_a_730_day_window(self):
        date_from, date_to = parse_date_range("last_2_years")
        assert (date_to - date_from).days == 730


class TestBuildFilterClause:
    def test_no_filters_produces_empty_clause(self):
        clause = build_filter_clause(SearchFilters())
        assert clause.sql == ""
        assert clause.params == []

    def test_single_qe_type_uses_equality(self):
        clause = build_filter_clause(SearchFilters(qe_type="Deviation"))
        assert '= $2' in clause.sql
        assert clause.params == ["Deviation"]

    def test_list_qe_type_uses_any(self):
        clause = build_filter_clause(SearchFilters(qe_type=["Out Of Specification", "Out of Trend"]))
        assert "= ANY($2)" in clause.sql
        assert clause.params == [["Out Of Specification", "Out of Trend"]]

    def test_exclude_id_is_cast_to_text_and_stringified(self):
        clause = build_filter_clause(SearchFilters(exclude_id=12345))
        assert clause.params == ["12345"]
        assert "::text !=" in clause.sql

    def test_date_range_appends_both_bounds_in_order(self):
        d_from = datetime(2026, 1, 1)
        d_to = datetime(2026, 2, 1)
        clause = build_filter_clause(SearchFilters(date_from=d_from, date_to=d_to))
        assert clause.params == [d_from, d_to]

    def test_locations_with_all_sentinel_skips_the_filter(self):
        clause = build_filter_clause(SearchFilters(locations=["All"]))
        assert clause.sql == ""
        assert clause.params == []

    def test_locations_with_all_sentinel_is_case_insensitive(self):
        clause = build_filter_clause(SearchFilters(locations=["ALL"]))
        assert clause.sql == ""

    def test_real_locations_are_applied(self):
        clause = build_filter_clause(SearchFilters(locations=["Site A", "Site B"]))
        assert clause.params == [["Site A", "Site B"]]

    def test_param_offset_shifts_starting_index(self):
        clause = build_filter_clause(SearchFilters(qe_type="Deviation"), param_offset=3)
        assert "$4" in clause.sql

    def test_next_param_index_tracks_appended_params(self):
        clause = build_filter_clause(SearchFilters(qe_type="Deviation", exclude_id=1))
        assert clause.next_param_index == 3  # offset(1) + qe_type($2) + exclude_id($3) -> next is $4... counted from params len

    def test_multiple_filters_combine_with_and(self):
        clause = build_filter_clause(
            SearchFilters(qe_type="Deviation", instruments=["HPLC"], materials=["Paracetamol"])
        )
        assert clause.sql.count(" AND ") == 3  # leading AND + 2 joins between 3 fragments
        assert len(clause.params) == 3

    def test_sfg_code_all_sentinel_skips_filter(self):
        clause = build_filter_clause(SearchFilters(sfg_code=["all"]))
        assert clause.sql == ""


class TestBuildFromClauseSharedBetweenKeywordAndSemanticSearch:
    def test_keyword_search_joins_details_table_when_configured(self, monkeypatch):
        from src.agents.search_agent.api.services import keyword_search as mod

        monkeypatch.setattr(mod.settings, "SEARCH_DETAILS_TABLE", "details_tbl")
        clause = mod._build_from_clause()
        assert "JOIN" in clause
        assert "details_tbl" in clause

    def test_keyword_search_uses_single_table_when_not_configured(self, monkeypatch):
        from src.agents.search_agent.api.services import keyword_search as mod

        monkeypatch.setattr(mod.settings, "SEARCH_DETAILS_TABLE", None)
        clause = mod._build_from_clause()
        assert "JOIN" not in clause

    def test_semantic_search_joins_details_table_when_configured(self, monkeypatch):
        from src.agents.search_agent.api.services import semantic_search as mod

        monkeypatch.setattr(mod.settings, "SEARCH_DETAILS_TABLE", "details_tbl")
        clause = mod._build_from_clause()
        assert "JOIN" in clause

    def test_semantic_search_uses_single_table_when_not_configured(self, monkeypatch):
        from src.agents.search_agent.api.services import semantic_search as mod

        monkeypatch.setattr(mod.settings, "SEARCH_DETAILS_TABLE", None)
        clause = mod._build_from_clause()
        assert "JOIN" not in clause
