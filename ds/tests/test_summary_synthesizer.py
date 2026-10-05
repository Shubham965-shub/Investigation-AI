"""Pure-logic tests for summary_synthesizer's data-shaping helpers (grouping,
payload building, id normalization, metrics) — none of these call the LLM."""

from types import SimpleNamespace

from src.agents.search_agent.api.services.summary_synthesizer import (
    build_category_payload,
    compute_event_metrics,
    group_by_site_and_category,
    normalize_ids,
)


def _rec(**kwargs):
    return SimpleNamespace(**kwargs)


class TestNormalizeIds:
    def test_all_integer_like_strings_normalize_to_ints(self):
        ids, use_text = normalize_ids(["1", "2", "3"])
        assert ids == [1, 2, 3]
        assert use_text is False

    def test_mixed_or_non_numeric_ids_fall_back_to_strings(self):
        ids, use_text = normalize_ids(["1", "abc"])
        assert ids == ["1", "abc"]
        assert use_text is True

    def test_empty_list(self):
        assert normalize_ids([]) == ([], False)


class TestGroupBySiteAndCategory:
    def test_groups_records_by_site_then_category(self):
        records = [
            _rec(site="Site A", root_cause_category="Equipment"),
            _rec(site="Site A", root_cause_category="Process"),
            _rec(site="Site B", root_cause_category="Equipment"),
        ]
        grouped = group_by_site_and_category(records)
        assert set(grouped.keys()) == {"Site A", "Site B"}
        assert set(grouped["Site A"].keys()) == {"Equipment", "Process"}
        assert len(grouped["Site B"]["Equipment"]) == 1

    def test_missing_site_falls_back_to_unknown_site(self):
        records = [_rec(root_cause_category="Equipment")]
        grouped = group_by_site_and_category(records)
        assert "Unknown Site" in grouped

    def test_missing_category_falls_back_to_uncategorized(self):
        records = [_rec(site="Site A")]
        grouped = group_by_site_and_category(records)
        assert "Uncategorized" in grouped["Site A"]


class TestBuildCategoryPayload:
    def test_skips_records_without_a_root_cause_summary(self):
        grouped = {
            "Site A": {
                "Equipment": [
                    _rec(deviation_id=1, root_cause_summary=None, age_bucket=None),
                    _rec(deviation_id=2, root_cause_summary="pump seal failed", age_bucket=None),
                ]
            }
        }
        payload = build_category_payload(grouped)
        assert len(payload) == 1
        items = payload[0]["categories"][0]["items"]
        assert len(items) == 1
        assert "2:" in items[0]

    def test_includes_age_bucket_label_when_present(self):
        grouped = {
            "Site A": {
                "Equipment": [_rec(deviation_id=5, root_cause_summary="failure", age_bucket="0_6_months")]
            }
        }
        payload = build_category_payload(grouped)
        item = payload[0]["categories"][0]["items"][0]
        assert item.startswith("[0_6_months]")
        assert "5" in item

    def test_category_with_no_usable_items_is_dropped(self):
        grouped = {"Site A": {"Equipment": [_rec(deviation_id=1, root_cause_summary=None, age_bucket=None)]}}
        payload = build_category_payload(grouped)
        assert payload == []

    def test_site_with_no_usable_categories_is_dropped_entirely(self):
        grouped = {
            "Site A": {"Equipment": [_rec(deviation_id=1, root_cause_summary=None, age_bucket=None)]},
            "Site B": {"Process": [_rec(deviation_id=2, root_cause_summary="real finding", age_bucket=None)]},
        }
        payload = build_category_payload(grouped)
        sites = [p["site"] for p in payload]
        assert sites == ["Site B"]

    def test_caps_sampled_items_at_15_per_category(self):
        grouped = {
            "Site A": {
                "Equipment": [
                    _rec(deviation_id=i, root_cause_summary=f"finding {i}", age_bucket=None) for i in range(30)
                ]
            }
        }
        payload = build_category_payload(grouped)
        assert len(payload[0]["categories"][0]["items"]) == 15


class TestComputeEventMetrics:
    def test_counts_total_and_per_site(self):
        records = [_rec(site="A"), _rec(site="A"), _rec(site="B")]
        total, per_site = compute_event_metrics(records)
        assert total == 3
        assert per_site == {"A": 2, "B": 1}

    def test_empty_records_returns_zero_total_and_empty_dict(self):
        assert compute_event_metrics([]) == (0, {})

    def test_missing_site_counted_as_unknown_site(self):
        total, per_site = compute_event_metrics([_rec()])
        assert per_site == {"Unknown Site": 1}
