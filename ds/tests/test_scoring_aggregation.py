"""Tests for the deterministic scoring aggregation + rubric resolution logic.
Per aggregation.py's own docstring: "Nothing here calls an LLM" — these are
plain data transforms over CheckpointVerdict -> SectionScore -> report."""

from src.agents.scoring.api.schemas import CheckpointVerdict
from src.agents.scoring.rubric.aggregation import (
    build_report_response,
    build_score_info,
    build_section_score,
)
from src.agents.scoring.rubric.rubric_config import (
    clamp_percentage,
    get_section,
    resolve_checkpoint,
)


class TestClampPercentage:
    def test_in_range_value_rounds_to_two_decimals(self):
        assert clamp_percentage(33.3333) == 33.33

    def test_negative_value_clamps_to_zero(self):
        assert clamp_percentage(-5.0) == 0.0

    def test_over_100_clamps_to_100(self):
        assert clamp_percentage(150.0) == 100.0


class TestGetSection:
    def test_known_sections_resolve(self):
        for key in ("task_report", "rc", "impact", "capa"):
            assert get_section(key).section == key

    def test_unknown_section_raises_keyerror(self):
        import pytest

        with pytest.raises(KeyError):
            get_section("not_a_real_section")

    def test_achievable_max_is_sum_of_checkpoint_maxima(self):
        spec = get_section("rc")
        assert spec.achievable_max == sum(cp.max_marks for cp in spec.checkpoints)


class TestResolveCheckpointBinary:
    def _binary_cp(self, allow_na=False):
        return get_section("task_report").checkpoints[0] if not allow_na else get_section("task_report").checkpoints[7]

    def test_yes_variants_award_full_marks(self):
        cp = self._binary_cp()
        for raw in ("Yes", "yes", "Y", "true", "pass"):
            verdict, marks, applicable = resolve_checkpoint(cp, raw)
            assert verdict == "Yes"
            assert marks == cp.max_marks
            assert applicable is True

    def test_no_awards_zero(self):
        cp = self._binary_cp()
        verdict, marks, applicable = resolve_checkpoint(cp, "No")
        assert verdict == "No"
        assert marks == 0.0
        assert applicable is True

    def test_blank_or_unknown_verdict_defaults_to_no(self):
        cp = self._binary_cp()
        for raw in ("", "   ", "maybe", "unsure"):
            verdict, marks, applicable = resolve_checkpoint(cp, raw)
            assert verdict == "No"
            assert marks == 0.0

    def test_na_without_allow_na_is_scored_as_unmet(self):
        cp = self._binary_cp(allow_na=False)
        assert cp.allow_na is False
        verdict, marks, applicable = resolve_checkpoint(cp, "NA", "not applicable here, equipment wasn't used")
        assert verdict == "No"
        assert marks == 0.0

    def test_na_with_allow_na_and_justified_rationale_is_full_marks(self):
        cp = self._binary_cp(allow_na=True)
        assert cp.allow_na is True
        verdict, marks, applicable = resolve_checkpoint(cp, "NA", "no listed factors were applicable to this failure mode")
        assert verdict == "NA"
        assert marks == cp.max_marks
        assert applicable is True

    def test_na_with_allow_na_but_bare_unjustified_rationale_is_scored_as_unmet(self):
        cp = self._binary_cp(allow_na=True)
        verdict, marks, applicable = resolve_checkpoint(cp, "NA", "NA")
        assert verdict == "No"
        assert marks == 0.0

        verdict2, marks2, _ = resolve_checkpoint(cp, "Not Applicable", "not applicable")
        assert verdict2 == "No"
        assert marks2 == 0.0


class TestResolveCheckpointClassification:
    def _rc_cp(self):
        return get_section("rc").checkpoints[0]

    def test_exact_tier_names_resolve_directly(self):
        cp = self._rc_cp()
        verdict, marks, applicable = resolve_checkpoint(cp, "assignable")
        assert verdict == "assignable"
        assert marks == 30.0
        assert applicable is True

        verdict, marks, _ = resolve_checkpoint(cp, "probable")
        assert verdict == "probable"
        assert marks == 20.0

        verdict, marks, _ = resolve_checkpoint(cp, "none")
        assert verdict == "none"
        assert marks == -5.0

    def test_decorated_verdict_resolves_via_prefix_match(self):
        cp = self._rc_cp()
        verdict, marks, _ = resolve_checkpoint(cp, "Assignable (proven through evidence)")
        assert verdict == "assignable"
        assert marks == 30.0

    def test_negated_verdict_does_not_false_positive_match_a_tier(self):
        cp = self._rc_cp()
        verdict, marks, _ = resolve_checkpoint(cp, "not assignable")
        assert verdict == "none"
        assert marks == -5.0

    def test_unrecognised_verdict_defaults_to_lowest_marks_tier(self):
        cp = self._rc_cp()
        verdict, marks, applicable = resolve_checkpoint(cp, "completely unrelated text")
        assert verdict == "none"  # lowest-marks tier
        assert marks == -5.0
        assert applicable is True


class TestBuildSectionScore:
    def test_full_marks_when_every_checkpoint_passes(self):
        spec = get_section("task_report")
        verdicts = [
            CheckpointVerdict(id=cp.id, verdict="Yes", rationale="met", evidence_quote="x")
            for cp in spec.checkpoints
        ]
        score = build_section_score("task_report", verdicts)
        assert score.percentage == 100.0
        assert score.marks_awarded == spec.achievable_max

    def test_missing_checkpoint_ids_default_to_not_met(self):
        score = build_section_score("task_report", [])
        assert score.marks_awarded == 0.0
        assert score.percentage == 0.0
        assert len(score.checkpoints) == len(get_section("task_report").checkpoints)
        assert all(c.verdict == "No" for c in score.checkpoints)

    def test_unknown_checkpoint_ids_in_input_are_ignored(self):
        verdicts = [CheckpointVerdict(id="not-a-real-id", verdict="Yes", rationale="x")]
        score = build_section_score("task_report", verdicts)
        assert score.marks_awarded == 0.0  # the bogus id contributed nothing

    def test_na_checkpoints_reduce_the_applicable_denominator(self):
        spec = get_section("task_report")
        na_checkpoint = next(cp for cp in spec.checkpoints if cp.allow_na)
        verdicts = [
            CheckpointVerdict(
                id=cp.id,
                verdict="NA" if cp.id == na_checkpoint.id else "Yes",
                rationale="documented and justified reasoning" if cp.id == na_checkpoint.id else "met",
            )
            for cp in spec.checkpoints
        ]
        score = build_section_score("task_report", verdicts)
        assert score.applicable_max == spec.achievable_max  # NA still counts as applicable (full marks)
        assert score.percentage == 100.0

    def test_rc_classification_can_go_negative_but_percentage_clamps_to_zero(self):
        score = build_section_score("rc", [CheckpointVerdict(id="1", verdict="none", rationale="no RC established")])
        assert score.marks_awarded == -5.0
        assert score.percentage == 0.0  # clamped


class TestBuildReportResponse:
    def test_only_detected_sections_appear_in_detected_sections_list(self):
        task_score = build_section_score("task_report", [])
        response = build_report_response({"task_report": task_score})
        assert response.detected_sections == ["task_report"]
        assert response.iq_score is None
        assert response.task_report_execution is not None

    def test_iq_group_aggregates_rc_impact_capa(self):
        rc_score = build_section_score("rc", [CheckpointVerdict(id="1", verdict="assignable", rationale="x")])
        impact_score = build_section_score("impact", [])
        capa_score = build_section_score("capa", [])
        response = build_report_response({"rc": rc_score, "impact": impact_score, "capa": capa_score})
        assert response.iq_score is not None
        assert set(response.detected_sections) == {"rc", "impact", "capa"}
        assert response.task_report_execution is None

    def test_overall_score_is_rounded_integer_of_overall_percentage(self):
        task_score = build_section_score(
            "task_report",
            [CheckpointVerdict(id=cp.id, verdict="Yes", rationale="x") for cp in get_section("task_report").checkpoints],
        )
        response = build_report_response({"task_report": task_score})
        assert response.score == 100
        assert response.overall_percentage == 100.0

    def test_empty_section_scores_produces_zero_score(self):
        response = build_report_response({})
        assert response.score == 0
        assert response.detected_sections == []
        assert response.task_report_execution is None
        assert response.iq_score is None


class TestBuildScoreInfo:
    def test_one_info_table_per_section_with_matching_row_count(self):
        spec = get_section("capa")
        score = build_section_score("capa", [])
        tables = build_score_info({"capa": score})
        assert len(tables) == 1
        assert tables[0].section == "capa"
        assert len(tables[0].rows) == len(spec.checkpoints)
