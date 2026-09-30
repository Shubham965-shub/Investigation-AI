from backend.db.critique_state import MAX_UPLOADS, compute_upload_state


def _report(*decisions, **overrides):
    report = {"is_gospel": False, "recommendations": [{"decision": d} for d in decisions]}
    report.update(overrides)
    return report


def test_no_upload_yet_is_pending_and_uploadable():
    state = compute_upload_state(None, 0)
    assert state["status"] == "pending"
    assert state["can_upload"] and not state["locked"]


def test_critique_pending_blocks_upload_without_locking():
    state = compute_upload_state(_report(critique_pending=True), 1)
    assert state["status"] == "processing"
    assert not state["can_upload"] and not state["locked"]


def test_gospel_report_locks():
    state = compute_upload_state(_report(is_gospel=True), 1)
    assert state["status"] == "complete" and state["locked"]


def test_max_uploads_locks_even_with_rejections():
    state = compute_upload_state(_report("rejected", "accepted"), MAX_UPLOADS)
    assert state["locked"] and not state["can_upload"]


def test_final_attempt_with_failed_critique_stays_locked():
    state = compute_upload_state(_report(critique_failed=True), MAX_UPLOADS)
    assert state["locked"]


def test_failed_critique_allows_reupload():
    state = compute_upload_state(_report(critique_failed=True), 1)
    assert state["status"] == "in_progress"
    assert state["can_upload"] and not state["locked"]


def test_no_recommendations_locks_as_complete():
    state = compute_upload_state(_report(), 1)
    assert state["status"] == "complete" and state["locked"]


def test_pending_decision_blocks_reupload():
    state = compute_upload_state(_report("accepted", "pending"), 1)
    assert state["status"] == "in_progress"
    assert not state["can_upload"] and not state["locked"]


def test_all_rejected_locks():
    state = compute_upload_state(_report("rejected", "rejected"), 1)
    assert state["status"] == "complete" and state["locked"]


def test_mixed_decisions_allow_reupload():
    state = compute_upload_state(_report("accepted", "rejected"), 2)
    assert state["can_upload"] and not state["locked"]


def test_all_accepted_allows_reupload():
    state = compute_upload_state(_report("accepted", "accepted"), 1)
    assert state["can_upload"] and not state["locked"]


def test_upload_count_is_passed_through():
    assert compute_upload_state(_report("accepted"), 2)["upload_count"] == 2
