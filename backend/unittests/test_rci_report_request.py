from backend.services.rci_report_request import build_rci_report_request


def test_accepted_rc_conclusion_defaults_when_no_report_uploaded():
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=[],
        task_critique_reports={},
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    assert payload["accepted_rc_conclusion"] == {
        "rc_conclusion_text": "",
        "overall_verdict": "accept",
        "review_comments": [],
    }
    assert payload["accepted_capa"] == {"capa_items": [], "overall_verdict": "accept", "review_comments": []}
    assert payload["uploaded_impact_assessment_text"] is None
    assert payload["uploaded_correction_remedial_text"] is None


def test_accepted_rc_conclusion_prefers_raw_text_over_summary():
    report = {
        "critiques": [
            {
                "category": "rc_impact",
                "summary": "thin summary",
                "rc_conclusion_text_raw": "the verbatim extracted conclusion",
                "recommendations": [],
            }
        ]
    }
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=[],
        task_critique_reports={},
        rc_capa_report=report,
        mc_confirmed=None,
        manual_entries={},
    )
    assert payload["accepted_rc_conclusion"]["rc_conclusion_text"] == "the verbatim extracted conclusion"


def test_accepted_rc_conclusion_falls_back_to_summary_when_raw_text_missing():
    report = {"critiques": [{"category": "rc_impact", "summary": "thin summary", "recommendations": []}]}
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=[],
        task_critique_reports={},
        rc_capa_report=report,
        mc_confirmed=None,
        manual_entries={},
    )
    assert payload["accepted_rc_conclusion"]["rc_conclusion_text"] == "thin summary"


def test_accepted_rc_conclusion_marks_accept_with_comments_when_any_recommendation_rejected():
    report = {
        "critiques": [
            {
                "category": "rc_impact",
                "summary": "",
                "recommendations": [
                    {"decision": "accepted", "description": "fine"},
                    {"decision": "rejected", "description": "needs more detail"},
                ],
            }
        ]
    }
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=[],
        task_critique_reports={},
        rc_capa_report=report,
        mc_confirmed=None,
        manual_entries={},
    )
    conclusion = payload["accepted_rc_conclusion"]
    assert conclusion["overall_verdict"] == "accept_with_comments"
    assert conclusion["review_comments"] == ["fine", "needs more detail"]


def test_accepted_capa_pulls_capa_items_and_text():
    report = {
        "critiques": [
            {
                "category": "capa",
                "summary": "fallback",
                "capa_text_raw": "full capa text",
                "capa_items": [{"description": "retrain staff"}],
                "recommendations": [],
            }
        ]
    }
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=[],
        task_critique_reports={},
        rc_capa_report=report,
        mc_confirmed=None,
        manual_entries={},
    )
    assert payload["accepted_capa"]["capa_items"] == [{"description": "retrain staff"}]
    assert payload["accepted_capa"]["capa_overall_text"] == "full capa text"


def test_uploaded_section_text_truncates_long_text():
    long_text = "x" * 9000
    report = {
        "critiques": [
            {"category": "rc_impact", "impact_assessment_text": long_text, "summary": "", "recommendations": []}
        ]
    }
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=[],
        task_critique_reports={},
        rc_capa_report=report,
        mc_confirmed=None,
        manual_entries={},
    )
    text = payload["uploaded_impact_assessment_text"]
    assert text.endswith("... [truncated for length]")
    assert len(text) < len(long_text)


def test_rci_plan_sections_payload_drops_unchecked_sections_and_tasks():
    sections = [
        {
            "title": "Section A",
            "correlation": "high",
            "is_checked": True,
            "tasks": [
                {"description": "keep me", "is_checked": True},
                {"description": "drop me", "is_checked": False},
            ],
        },
        {
            "title": "Section B (excluded)",
            "is_checked": False,
            "tasks": [{"description": "irrelevant", "is_checked": True}],
        },
    ]
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=sections,
        task_critique_reports={},
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    assert len(payload["rci_plan_sections"]) == 1
    section = payload["rci_plan_sections"][0]
    assert section["title"] == "Section A"
    assert section["tasks"] == [{"description": "keep me"}]


def test_rci_plan_sections_payload_defaults_missing_is_checked_to_true():
    sections = [{"title": "Section A", "tasks": [{"description": "task 1"}]}]
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=sections,
        task_critique_reports={},
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    assert len(payload["rci_plan_sections"]) == 1
    assert payload["rci_plan_sections"][0]["tasks"] == [{"description": "task 1"}]


def test_task_critique_payload_numbers_ticks_per_section_and_subtask():
    sections = [
        {
            "title": "Section A",
            "assignee": "Jane Doe",
            "is_checked": True,
            "tasks": [
                {"description": "task 1", "is_checked": True},
                {"description": "task 2", "is_checked": True},
            ],
        },
        {
            "title": "Section B",
            "is_checked": True,
            "tasks": [{"description": "task 1", "is_checked": True}],
        },
    ]
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=sections,
        task_critique_reports={},
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    items = payload["task_critique"]
    assert [i["tick"] for i in items] == ["1.1", "1.2", "2.1"]
    assert items[0]["responsible_person"] == "Jane Doe"
    assert items[2]["responsible_person"] == "Unassigned"


def test_task_critique_payload_skips_unchecked_sections():
    sections = [
        {"title": "A", "is_checked": False, "tasks": [{"description": "x", "is_checked": True}]},
    ]
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=sections,
        task_critique_reports={},
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    assert payload["task_critique"] == []


def test_task_critique_payload_prefers_task_findings_over_summary():
    sections = [{"title": "A", "is_checked": True, "tasks": [{"description": "x", "is_checked": True}]}]
    reports = {
        0: {
            "summary": "thin summary",
            "task_findings": [
                {"task_number": 1, "title": "Investigate seal", "objective": "find root cause", "findings": "seal worn", "inference": "replace seal"}
            ],
        }
    }
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=sections,
        task_critique_reports=reports,
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    critique_text = payload["task_critique"][0]["critique"]
    assert "Task 1: Investigate seal" in critique_text
    assert "Objective: find root cause" in critique_text
    assert "Findings: seal worn" in critique_text
    assert "Inference: replace seal" in critique_text


def test_task_critique_payload_falls_back_to_summary_when_no_task_findings():
    sections = [{"title": "A", "is_checked": True, "tasks": [{"description": "x", "is_checked": True}]}]
    reports = {0: {"summary": "thin summary", "task_findings": []}}
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=sections,
        task_critique_reports=reports,
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    assert payload["task_critique"][0]["critique"] == "thin summary"


def test_format_task_findings_keeps_whole_blocks_and_notes_omissions():
    sections = [{"title": "A", "is_checked": True, "tasks": [{"description": "x", "is_checked": True}]}]
    big_findings = [
        {"task_number": i, "title": f"Task {i}", "findings": "y" * 1000}
        for i in range(10)
    ]
    reports = {0: {"task_findings": big_findings}}
    payload = build_rci_report_request(
        record_id="1",
        event_type="Deviation",
        trackwise_fields={},
        rci_sections=sections,
        task_critique_reports=reports,
        rc_capa_report=None,
        mc_confirmed=None,
        manual_entries={},
    )
    critique_text = payload["task_critique"][0]["critique"]
    assert "additional task finding block(s) omitted for length" in critique_text


def test_build_rci_report_request_top_level_shape():
    payload = build_rci_report_request(
        record_id="504544",
        event_type="OOS",
        trackwise_fields={"title": "t"},
        rci_sections=[],
        task_critique_reports={},
        rc_capa_report=None,
        mc_confirmed=True,
        manual_entries={"process_flow": "Step 1 -> Step 2"},
    )
    assert payload["deviation_id"] == "504544"
    assert payload["event_type"] == "OOS"
    assert payload["trackwise_fields"] == {"title": "t"}
    assert payload["mc_confirmed"] is True
    assert payload["manual_entries"] == {"process_flow": "Step 1 -> Step 2"}
    assert payload["history_lookback_months"] == 24
